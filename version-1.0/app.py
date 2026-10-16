from flask import Flask, jsonify, request, Response, session, redirect, send_from_directory
import sqlite3
import json
import paho.mqtt.client as mqtt
import threading
import time
import csv
import io
import os
import sys
import secrets
from datetime import datetime
from contextlib import contextmanager
import queue
import pytz
from functools import wraps

__version__ = '1.6.1'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

app = Flask(__name__)
# Request bodies are small JSON forms; anything bigger is refused before it is read.
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024
# MQTT payloads bigger than this are dropped (and counted), so a publisher cannot fill the disk.
MAX_PAYLOAD_BYTES = max(int(os.getenv('MQTT_MAX_PAYLOAD_BYTES', '65536') or 65536), 1024)
# Open live-update streams (browser tabs) at once; more get 503 instead of exhausting threads.
MAX_STREAMS = max(int(os.getenv('SENSEHIVE_MAX_STREAMS', '50') or 50), 1)
dropped_payloads = 0
# Own cookie name so it never clashes with other apps on the same host (e.g. Home Assistant ingress)
app.config['SESSION_COOKIE_NAME'] = 'sensehive_session'

try:
    from . import security
except ImportError:                          # run as app.py (Docker image, tests)
    import security
security.configure(app)                      # HttpOnly, SameSite, Secure, Path, session lifetime
login_limiter = security.LoginLimiter()

# Database path - check environment variable or use default
DB_PATH = os.getenv('DB_PATH', '/app/data/iot_dashboard.db')


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None or value.strip() == '':
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def env_int(name, default=0):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# SQLite WAL mode (disable with SQLITE_WAL=false, e.g. on network filesystems)
SQLITE_WAL = env_flag('SQLITE_WAL', True)

# Home Assistant ingress: requests from this proxy address are already authenticated by
# Home Assistant, so they skip the SenseHive login (set by the add-on to 172.30.32.2)
INGRESS_PROXY = os.getenv('SENSEHIVE_INGRESS_PROXY', '').strip()

# How often the retention job runs (seconds)
RETENTION_INTERVAL = max(env_int('RETENTION_INTERVAL', 3600), 60)

mqtt_client = None
mqtt_connected = False

# SSE: one queue per connected browser so every tab receives every message
sse_clients = set()
sse_lock = threading.Lock()


def publish_event(data):
    with sse_lock:
        clients = list(sse_clients)
    for q in clients:
        try:
            q.put_nowait(data)
        except queue.Full:
            pass


def table_name_for(topic):
    """The SQLite table of a topic, always used inside double quotes ("..."). A `"`
    is doubled (SQL's identifier escape), so no topic can end the identifier and
    add SQL of its own; topics without one map to the same names as before."""
    return topic.replace('/', '_').replace('#', 'wildcard').replace('+', 'plus').replace('"', '""')


MAX_TOPIC_LENGTH = 512


def topic_error(topic):
    """Why a topic cannot be added, or None. MQTT allows almost any character;
    SenseHive refuses the few that serve no real topic and only break things."""
    if len(topic) > MAX_TOPIC_LENGTH:
        return f'Topic is longer than {MAX_TOPIC_LENGTH} characters'
    if '"' in topic or any(ord(ch) < 32 or ord(ch) == 127 for ch in topic):
        return 'Topic cannot contain double quotes or control characters'
    return None


# Database helper
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
    if SQLITE_WAL:
        conn.execute('PRAGMA synchronous=NORMAL')
    try:
        yield conn
    finally:
        conn.close()


# Hash password (salted, slow; see security.py)
def hash_password(password):
    return security.hash_password(password)


# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def configure_secret_key():
    """Use SECRET_KEY from env, otherwise a random key persisted next to the database."""
    key = os.getenv('SECRET_KEY')
    if not key:
        key_file = os.path.join(os.path.dirname(DB_PATH), 'secret_key')
        try:
            with open(key_file, 'r') as f:
                key = f.read().strip()
        except OSError:
            key = None
        if not key:
            key = secrets.token_hex(32)
            try:
                fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)   # owner only
                with os.fdopen(fd, 'w') as f:
                    f.write(key)
            except OSError:
                pass
    app.config['SECRET_KEY'] = key


NODE_COLUMNS = (
    ('tag', "TEXT NOT NULL DEFAULT 'untagged'"),
    ('node_name', "TEXT NOT NULL DEFAULT 'default'"),
    ('lwt_topic', "TEXT NOT NULL DEFAULT ''"),
    ('lwt_online', "TEXT NOT NULL DEFAULT 'online'"),
    ('lwt_offline', "TEXT NOT NULL DEFAULT 'offline'"),
)

ACTIVE_WORDS = {'online', 'active', 'connected', 'up', 'alive', 'true', '1'}
INACTIVE_WORDS = {'offline', 'inactive', 'disconnected', 'down', 'dead', 'lost', 'false', '0'}


def classify_lwt(payload_str, online='online', offline='offline'):
    """Map an LWT / birth payload to 'active', 'inactive' or 'unknown'."""
    text = payload_str.strip().strip('"').strip().lower()
    if online and text == online.strip().lower():
        return 'active'
    if offline and text == offline.strip().lower():
        return 'inactive'
    try:
        obj = json.loads(payload_str)
    except ValueError:
        obj = None
    if isinstance(obj, dict):
        for key in ('status', 'state', 'online', 'connected'):
            if key in obj:
                return classify_lwt(json.dumps(obj[key]) if not isinstance(obj[key], str) else obj[key], online, offline)
    if text in ACTIVE_WORDS:
        return 'active'
    if text in INACTIVE_WORDS:
        return 'inactive'
    return 'unknown'


def topic_status(node, lwt_rows):
    """'active' / 'inactive' / 'unknown' (LWT set, nothing received yet) / 'untracked' (no LWT topic)."""
    if not node.get('lwt_topic'):
        return 'untracked', None
    row = lwt_rows.get(node['lwt_topic'])
    if not row:
        return 'unknown', None
    return row['status'], row['updated_at']


def summarize_status(nodes):
    """Aggregate topic and node (group) status counts from enriched node dicts."""
    topics = {'active': 0, 'inactive': 0, 'unknown': 0, 'untracked': 0}
    groups = {}
    for node in nodes:
        topics[node['status']] = topics.get(node['status'], 0) + 1
        groups.setdefault(node['node_name'], []).append(node['status'])

    node_counts = {'active': 0, 'inactive': 0, 'unknown': 0}
    node_list = []
    for name, statuses in sorted(groups.items()):
        if 'active' in statuses:
            state = 'active'
        elif 'inactive' in statuses and all(s in ('inactive', 'untracked') for s in statuses):
            state = 'inactive'
        else:
            state = 'unknown'
        node_counts[state] += 1
        node_list.append({'node_name': name, 'status': state, 'topic_count': len(statuses)})

    return {'topics': topics, 'nodes': node_counts, 'node_list': node_list}


def topic_stats(c, topic):
    """Entry count and approximate on-disk size (bytes) of a topic's table."""
    try:
        row = c.execute(f'''SELECT COUNT(*) AS entries,
                                   COALESCE(SUM(LENGTH(CAST(payload AS BLOB)) + LENGTH(timestamp) + 12), 0) AS size
                            FROM "{table_name_for(topic)}"''').fetchone()  # nosec B608 - identifier from table_name_for(), values bound
        return row['entries'], row['size']
    except sqlite3.OperationalError:
        return 0, 0


def db_file_size():
    total = 0
    for suffix in ('', '-wal', '-shm'):
        try:
            total += os.path.getsize(DB_PATH + suffix)
        except OSError:
            pass
    return total


def load_lwt_rows(c):
    return {row['topic']: dict(row) for row in c.execute('SELECT * FROM lwt_status').fetchall()}


def add_column_if_missing(c, table, column, ddl):
    columns = [row[1] for row in c.execute(f'PRAGMA table_info("{table}")')]
    if column not in columns:
        c.execute(f'ALTER TABLE "{table}" ADD COLUMN {column} {ddl}')
        return True
    return False


# Initialize database
def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    configure_secret_key()

    with get_db() as conn:
        c = conn.cursor()

        # WAL improves concurrent read/write performance under continuous ingestion
        mode = 'wal' if SQLITE_WAL else 'delete'
        c.execute(f'PRAGMA journal_mode={mode}')

        # User accounts table
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )''')

        # Broker config table with timezone
        c.execute('''CREATE TABLE IF NOT EXISTS broker_config (
            id INTEGER PRIMARY KEY,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            username TEXT,
            password TEXT,
            timezone TEXT DEFAULT 'UTC'
        )''')

        # Nodes table
        c.execute('''CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Tagging, node grouping and LWT columns (migrates v1.0 databases in place)
        for column, ddl in NODE_COLUMNS:
            add_column_if_missing(c, 'nodes', column, ddl)

        # Last known LWT state per LWT topic
        c.execute('''CREATE TABLE IF NOT EXISTS lwt_status (
            topic TEXT PRIMARY KEY,
            payload TEXT,
            status TEXT,
            updated_at TEXT
        )''')

        # Key/value app settings (retention etc.)
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')

        # Insert default user if not exists
        c.execute('SELECT COUNT(*) FROM users')
        if c.fetchone()[0] == 0:
            # SENSEHIVE_ADMIN_PASSWORD sets the first password of a new database
            # (never printed); otherwise the documented default, to be changed.
            initial = os.getenv('SENSEHIVE_ADMIN_PASSWORD') or 'admin123'
            c.execute("INSERT INTO users (id, username, password) VALUES (1, 'admin', ?)", (hash_password(initial),))
            shown = '<SENSEHIVE_ADMIN_PASSWORD>' if os.getenv('SENSEHIVE_ADMIN_PASSWORD') else 'admin123'
            print("✅ Default user created: admin/" + shown)

        # Use environment variables for default broker or fallback to HiveMQ
        default_host = os.getenv('DEFAULT_BROKER_HOST', 'broker.hivemq.com')
        default_port = env_int('DEFAULT_BROKER_PORT', 1883)
        default_username = os.getenv('DEFAULT_BROKER_USERNAME', '')
        default_password = os.getenv('DEFAULT_BROKER_PASSWORD', '')
        default_timezone = os.getenv('DEFAULT_TIMEZONE', 'UTC')

        # Check if broker config exists
        c.execute('SELECT COUNT(*) FROM broker_config')
        if c.fetchone()[0] == 0:
            c.execute('''INSERT INTO broker_config (id, host, port, username, password, timezone)
                        VALUES (1, ?, ?, ?, ?, ?)''',
                      (default_host, default_port, default_username, default_password, default_timezone))
            print(f"✅ Initialized with default broker: {default_host}:{default_port}")
        else:
            # Add timezone column if it doesn't exist (for existing databases)
            if add_column_if_missing(c, 'broker_config', 'timezone', "TEXT DEFAULT 'UTC'"):
                print("✅ Added timezone column to existing database")

            # SENSEHIVE_FORCE_BROKER=true applies the DEFAULT_BROKER_* values on every start
            # (used by the CLI --broker flag and the Home Assistant add-on)
            if env_flag('SENSEHIVE_FORCE_BROKER'):
                c.execute('''UPDATE broker_config SET host=?, port=?, username=?, password=? WHERE id=1''',
                          (default_host, default_port, default_username, default_password))
                if os.getenv('DEFAULT_TIMEZONE'):
                    c.execute('UPDATE broker_config SET timezone=? WHERE id=1', (default_timezone,))
                print(f"✅ Broker set from environment: {default_host}:{default_port}")

        # SENSEHIVE_TIMEZONE (CLI --timezone) always overrides the stored timezone
        if os.getenv('SENSEHIVE_TIMEZONE'):
            c.execute('UPDATE broker_config SET timezone=? WHERE id=1', (os.getenv('SENSEHIVE_TIMEZONE'),))

        # Retention defaults (0 = disabled); env values seed a fresh database
        for key, env_name in (('retention_days', 'RETENTION_DAYS'), ('retention_max_entries', 'RETENTION_MAX_ENTRIES')):
            c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                      (key, str(max(env_int(env_name, 0), 0))))

        conn.commit()
    heartbeat_receiver.init_db()


def get_setting_int(key, default=0):
    with get_db() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
    try:
        return int(row['value']) if row else default
    except (TypeError, ValueError):
        return default


def get_retention_settings():
    return {
        'retention_days': get_setting_int('retention_days'),
        'retention_max_entries': get_setting_int('retention_max_entries'),
    }


def apply_retention():
    """Delete old rows per topic table. Returns the number of rows removed."""
    settings = get_retention_settings()
    days = settings['retention_days']
    max_entries = settings['retention_max_entries']
    if days <= 0 and max_entries <= 0:
        return 0

    deleted = 0
    with get_db() as conn:
        c = conn.cursor()
        topics = [row['topic'] for row in c.execute('SELECT topic FROM nodes').fetchall()]
        for topic in topics:
            table_name = table_name_for(topic)
            try:
                if days > 0:
                    cutoff = int(time.time()) - days * 86400
                    c.execute(f'''DELETE FROM "{table_name}"
                                  WHERE CAST(strftime('%s', timestamp) AS INTEGER) < ?''', (cutoff,))  # nosec B608 - identifier from table_name_for(), values bound
                    deleted += max(c.rowcount, 0)
                if max_entries > 0:
                    c.execute(f'''DELETE FROM "{table_name}" WHERE id <= (
                                    SELECT id FROM "{table_name}" ORDER BY id DESC LIMIT 1 OFFSET ?)''',  # nosec B608 - identifier from table_name_for(), values bound
                              (max_entries,))
                    deleted += max(c.rowcount, 0)
            except sqlite3.OperationalError as e:
                print(f"⚠️ Retention skipped for {topic}: {e}")
        conn.commit()
        if deleted and SQLITE_WAL:
            c.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    if deleted:
        print(f"🧹 Retention removed {deleted} old entries")
    return deleted


def retention_worker():
    while True:
        time.sleep(RETENTION_INTERVAL)
        try:
            apply_retention()
        except Exception as e:
            print(f"❌ Retention job failed: {e}")


# Get current timezone
def get_timezone():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT timezone FROM broker_config WHERE id = 1')
        result = c.fetchone()
        return result['timezone'] if result else 'UTC'


# Get timestamp in user's timezone
def get_localized_timestamp():
    tz_name = get_timezone()
    try:
        tz = pytz.timezone(tz_name)
        return datetime.now(tz).isoformat()
    except Exception:
        return datetime.now(pytz.UTC).isoformat()


# Create table for topic data
def create_topic_table(topic):
    table_name = table_name_for(topic)
    with get_db() as conn:
        c = conn.cursor()
        c.execute(f'''CREATE TABLE IF NOT EXISTS "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payload TEXT NOT NULL
        )''')  # nosec B608 - identifier from table_name_for(), values bound
        conn.commit()
    return table_name


def new_mqtt_client():
    # paho-mqtt 2.x requires an explicit callback API version
    if hasattr(mqtt, 'CallbackAPIVersion'):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    return mqtt.Client()


subscribed_topics = set()
subscription_lock = threading.Lock()


def sync_subscriptions(client=None, reset=False):
    """Subscribe to every data topic and LWT topic, unsubscribing from removed ones."""
    global subscribed_topics
    client = client or mqtt_client
    if not client:
        return
    with get_db() as conn:
        rows = conn.execute('SELECT topic, lwt_topic FROM nodes').fetchall()
    wanted = {row['topic'] for row in rows} | {row['lwt_topic'] for row in rows if row['lwt_topic']}
    with subscription_lock:
        current = set() if reset else subscribed_topics
        for topic in sorted(wanted - current):
            client.subscribe(topic)
            print(f"📡 Subscribed to: {topic}")
        for topic in sorted(current - wanted):
            client.unsubscribe(topic)
            print(f"🔕 Unsubscribed from: {topic}")
        subscribed_topics = wanted


# MQTT callbacks - THESE RUN WITHOUT GUI/LOGIN!
def on_connect(client, userdata, flags, rc, properties=None):
    global mqtt_connected
    if rc == 0:
        print("✅ Connected to MQTT broker")
        mqtt_connected = True
        # Subscribe to all stored topics and their LWT topics
        sync_subscriptions(client, reset=True)
    else:
        print(f"❌ MQTT connection failed: {rc}")
        mqtt_connected = False


def on_disconnect(client, userdata, *args):
    global mqtt_connected
    mqtt_connected = False
    print("⚠️ Disconnected from MQTT broker")


def on_message(client, userdata, msg):
    """
    MQTT message handler - RUNS AUTOMATICALLY WITHOUT GUI/LOGIN
    This is the core data logging function
    """
    global dropped_payloads
    try:
        topic = msg.topic
        if len(msg.payload) > MAX_PAYLOAD_BYTES:
            dropped_payloads += 1
            print(f"⚠️ Dropped a {len(msg.payload)}-byte message on {log_safe(topic, 120)} (limit {MAX_PAYLOAD_BYTES})")
            return
        payload_str = msg.payload.decode('utf-8', errors='replace')

        # Try to parse JSON (deeply nested input is kept as text, not parsed)
        try:
            payload = json.loads(payload_str)
        except (ValueError, RecursionError):
            payload = {"value": payload_str}

        localized_time = get_localized_timestamp()

        lwt_updates = {}
        with get_db() as conn:
            c = conn.cursor()
            rows = c.execute('SELECT topic, lwt_topic, lwt_online, lwt_offline FROM nodes').fetchall()

            # A message can match several subscriptions (exact topics and wildcards like sensors/#)
            matched = sorted({row['topic'] for row in rows if mqtt.topic_matches_sub(row['topic'], topic)})
            for sub in matched:
                c.execute(f'INSERT INTO "{table_name_for(sub)}" (timestamp, payload) VALUES (?, ?)',  # nosec B608 - identifier from table_name_for(), values bound
                          (localized_time, json.dumps(payload)))

            # LWT / birth messages update device status
            for row in rows:
                lwt_topic = row['lwt_topic']
                if lwt_topic and lwt_topic not in lwt_updates and mqtt.topic_matches_sub(lwt_topic, topic):
                    state = classify_lwt(payload_str, row['lwt_online'], row['lwt_offline'])
                    lwt_updates[lwt_topic] = state
                    c.execute('INSERT OR REPLACE INTO lwt_status (topic, payload, status, updated_at) VALUES (?, ?, ?, ?)',
                              (lwt_topic, payload_str[:500], state, localized_time))
            conn.commit()

        for lwt_topic, state in lwt_updates.items():
            print(f"💡 LWT {log_safe(lwt_topic, 120)}: {state}")
            publish_event({'type': 'lwt', 'lwt_topic': lwt_topic, 'status': state, 'timestamp': localized_time})

        if not matched:
            return

        print(f"📝 Logged data for {log_safe(topic, 120)}: {log_safe(json.dumps(payload), 50)}...")

        # Push to SSE (only if someone is watching GUI)
        for sub in matched:
            publish_event({
                'topic': sub,
                'source_topic': topic,
                'payload': payload,
                'timestamp': localized_time
            })

    except Exception as e:
        print(f"❌ Error processing message: {type(e).__name__}")


# Initialize MQTT client
def init_mqtt():
    global mqtt_client

    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM broker_config WHERE id = 1')
        config = c.fetchone()

    if not config:
        return

    mqtt_client = new_mqtt_client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message

    if config['username']:
        mqtt_client.username_pw_set(config['username'], config['password'])

    try:
        mqtt_client.connect(config['host'], config['port'], 60)
        mqtt_client.loop_start()
        print(f"🔌 Connecting to MQTT broker: {config['host']}:{config['port']}")
    except Exception as e:
        print(f"❌ Failed to connect to MQTT broker: {e}")


# Watchdog for MQTT reconnection - RUNS 24/7
def mqtt_watchdog():
    while True:
        time.sleep(10)
        if mqtt_client and not mqtt_connected:
            print("🔄 Attempting to reconnect MQTT...")
            try:
                mqtt_client.reconnect()
            except Exception:
                pass

# Every script comes from SenseHive itself (version-1.0/static, built ahead of
# time, no CDN): the policy refuses any other script, so a compromised
# third-party host could never run code here (SenseHive can share an origin
# with EdgeShell behind its gate).
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
       "frame-ancestors 'self'")


@app.after_request
def security_headers(resp):
    resp.headers.setdefault('Content-Security-Policy', CSP)
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=(), payment=(), usb=()')
    resp.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
    resp.headers.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
    return resp


@app.before_request
def refuse_cross_site_changes():
    """CSRF: a page on another site cannot make a signed-in browser change
    anything here (see security.cross_site)."""
    if security.cross_site(request):
        return jsonify({'error': 'Cross-site request refused'}), 403


@app.before_request
def ingress_auto_login():
    if INGRESS_PROXY and request.remote_addr == INGRESS_PROXY and 'logged_in' not in session:
        with get_db() as conn:
            user = conn.execute('SELECT username FROM users ORDER BY id LIMIT 1').fetchone()
        if user:
            session['logged_in'] = True
            session['username'] = user['username']

# ============================================================================
# PUBLIC ENDPOINTS - NO LOGIN REQUIRED (for health checks and monitoring)
# ============================================================================

@app.route('/api/health')
def health():
    """Health check endpoint - NO AUTH REQUIRED"""
    out = {'status': 'healthy', 'mqtt_connected': mqtt_connected, 'timestamp': datetime.now().isoformat()}
    # The exact version helps an attacker pick an exploit: shown only to users and tools that signed in.
    if 'logged_in' in session or heartbeat_receiver.token_ok(request.headers.get('Authorization', '')):
        out['version'] = __version__
    return jsonify(out)


@app.route('/api/status')
def status():
    """Status endpoint - NO AUTH REQUIRED (for monitoring)"""
    return jsonify({'connected': mqtt_connected})

# ============================================================================
# PROTECTED ENDPOINTS - LOGIN REQUIRED (for GUI functionality)
# ============================================================================

@app.route('/')
def index():
    """Main dashboard - REQUIRES LOGIN"""
    if 'logged_in' not in session:
        return redirect('login')
    return send_from_directory(TEMPLATE_DIR, 'index.html')


@app.route('/login')
def login_page():
    """Login page"""
    return send_from_directory(TEMPLATE_DIR, 'login.html')


@app.route('/api/login', methods=['POST'])
def login():
    """Login endpoint"""
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')

    if not username or not password or not isinstance(username, str) or not isinstance(password, str):
        return jsonify({'success': False, 'error': 'Username and password required'}), 400
    username = username[:64]
    ip = security.client_ip(request)
    if login_limiter.blocked(username, ip):
        return jsonify({'success': False, 'error': 'Too many failed sign-ins. Try again later.'}), 429

    with get_db() as conn:
        c = conn.cursor()
        user = c.execute('SELECT username, password FROM users WHERE username = ?', (username,)).fetchone()
        if user is None:
            security.burn_time(password)
        ok = user is not None and security.verify_password(user['password'], password)
        if ok and security.needs_rehash(user['password']):
            c.execute('UPDATE users SET password = ? WHERE username = ?', (hash_password(password), username))
            conn.commit()

    if not ok:
        login_limiter.failed(username, ip)
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    login_limiter.succeeded(username)
    session.clear()                              # a new session on sign-in (no fixation)
    session.permanent = True
    session['logged_in'] = True
    session['username'] = username
    return jsonify({'success': True})


@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout endpoint"""
    session.clear()
    return jsonify({'success': True})


@app.route('/api/change-password', methods=['POST'])
@login_required
def change_password():
    """Change password - REQUIRES LOGIN"""
    data = request.get_json(silent=True) or {}
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({'success': False, 'error': 'Both passwords required'}), 400

    username = session.get('username')
    if not isinstance(new_password, str) or len(new_password) < 8:
        return jsonify({'success': False, 'error': 'The new password needs at least 8 characters'}), 400
    ip = security.client_ip(request)
    if login_limiter.blocked(username, ip):
        return jsonify({'success': False, 'error': 'Too many failed attempts. Try again later.'}), 429

    with get_db() as conn:
        c = conn.cursor()
        user = c.execute('SELECT password FROM users WHERE username = ?', (username,)).fetchone()

        if not user or not security.verify_password(user['password'], current_password):
            login_limiter.failed(username, ip)
            return jsonify({'success': False, 'error': 'Current password incorrect'}), 401

        new_hashed = hash_password(new_password)
        c.execute('UPDATE users SET password = ? WHERE username = ?', (new_hashed, username))
        conn.commit()

        return jsonify({'success': True})


@app.route('/api/timezones')
@login_required
def timezones():
    """Get timezones - REQUIRES LOGIN"""
    all_timezones = pytz.all_timezones
    return jsonify({'timezones': all_timezones})


@app.route('/api/broker', methods=['GET', 'POST'])
@login_required
def broker():
    """Broker config - REQUIRES LOGIN"""
    if request.method == 'GET':
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT host, port, username, password, timezone FROM broker_config WHERE id = 1')
            config = c.fetchone()
            return jsonify(dict(config) if config else {})

    else:  # POST
        data = request.get_json(silent=True) or {}
        if not data.get('host') or not data.get('port'):
            return jsonify({'success': False, 'error': 'Host and port required'}), 400
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''UPDATE broker_config
                        SET host=?, port=?, username=?, password=?, timezone=?
                        WHERE id=1''',
                      (data['host'], data['port'], data.get('username', ''),
                       data.get('password', ''), data.get('timezone', 'UTC')))
            conn.commit()

        # Restart MQTT connection
        if mqtt_client:
            mqtt_client.disconnect()
            mqtt_client.loop_stop()

        threading.Thread(target=lambda: (time.sleep(1), init_mqtt()), daemon=True).start()

        return jsonify({'success': True})


@app.route('/api/broker/test', methods=['POST'])
@login_required
def test_broker():
    """Test broker connection - REQUIRES LOGIN"""
    data = request.get_json(silent=True) or {}
    test_client = new_mqtt_client()

    if data.get('username'):
        test_client.username_pw_set(data['username'], data.get('password', ''))

    try:
        test_client.connect(data['host'], int(data['port']), 10)
        test_client.disconnect()
        return jsonify({'success': True})
    except Exception as e:
        app.logger.warning('Broker test to %s:%s failed: %s', log_safe(data.get('host')), log_safe(data.get('port')),
                           log_safe(repr(e)))
        return jsonify({'success': False, 'error': broker_error_text(e)})


def csv_cell(value):
    """A CSV cell a spreadsheet never runs as a formula (a leading =, +, -, @, tab or CR is escaped).
    Plain numbers such as -12.5 stay numbers."""
    text = '' if value is None else str(value)
    if text[:1] in ('-', '+'):
        try:
            float(text)
            return text
        except ValueError:
            pass
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def log_safe(value, limit=200):
    """A value fit for one log line: no line breaks or other control characters
    (no forged log entries), and not too long."""
    text = str(value).replace('\r', ' ').replace('\n', ' ')
    return ''.join(ch if ch.isprintable() else '?' for ch in text)[:limit]


def broker_error_text(error):
    """A fixed, user-facing reason for a failed broker connection (never the
    exception text itself; the details go to the server log)."""
    import socket
    if isinstance(error, ConnectionRefusedError):
        return 'Connection refused: nothing is listening on that host and port'
    if isinstance(error, socket.gaierror):
        return 'Host name not found'
    if isinstance(error, (socket.timeout, TimeoutError)):
        return 'Timed out: the broker did not answer'
    if isinstance(error, OSError):
        return 'Network error: the broker could not be reached'
    if isinstance(error, ValueError):
        return 'Invalid host or port'
    return 'Could not connect to the broker'


@app.route('/api/settings/retention', methods=['GET', 'POST'])
@login_required
def retention_settings():
    """Data retention settings (0 = disabled) - REQUIRES LOGIN"""
    if request.method == 'GET':
        return jsonify(get_retention_settings())

    data = request.get_json(silent=True) or {}
    values = {}
    for key in ('retention_days', 'retention_max_entries'):
        try:
            values[key] = int(data.get(key, 0) or 0)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'error': f'{key} must be a whole number'}), 400
        if values[key] < 0:
            return jsonify({'success': False, 'error': f'{key} cannot be negative'}), 400

    with get_db() as conn:
        for key, value in values.items():
            conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
        conn.commit()

    return jsonify({'success': True, **values})


@app.route('/api/retention/run', methods=['POST'])
@login_required
def run_retention():
    """Apply the retention policy now - REQUIRES LOGIN"""
    deleted = apply_retention()
    return jsonify({'success': True, 'deleted': deleted})


@app.route('/api/nodes', methods=['GET', 'POST'])
@login_required
def nodes():
    """Node management - REQUIRES LOGIN"""
    if request.method == 'GET':
        with get_db() as conn:
            c = conn.cursor()
            lwt_rows = load_lwt_rows(c)
            c.execute('SELECT * FROM nodes ORDER BY created_at DESC')
            nodes = []
            for row in c.fetchall():
                node = dict(row)
                table_name = table_name_for(node['topic'])

                # Per-topic stats and LWT status
                node['entry_count'], node['approx_size_bytes'] = topic_stats(c, node['topic'])
                node['status'], node['status_updated'] = topic_status(node, lwt_rows)

                # Get last value
                try:
                    c.execute(f'SELECT payload, timestamp FROM "{table_name}" ORDER BY id DESC LIMIT 1')  # nosec B608 - identifier from table_name_for(), values bound
                    last = c.fetchone()
                    if last:
                        node['last_value'] = json.loads(last['payload'])
                        node['last_updated'] = last['timestamp']
                    else:
                        node['last_value'] = None
                        node['last_updated'] = None
                except Exception:
                    node['last_value'] = None
                    node['last_updated'] = None

                nodes.append(node)

            return jsonify(nodes)

    else:  # POST
        data = request.get_json(silent=True) or {}
        topic = (data.get('topic') or '').strip()
        if not topic:
            return jsonify({'success': False, 'error': 'Topic is required'}), 400
        error = topic_error(topic)
        if error:
            return jsonify({'success': False, 'error': error}), 400
        fields, error = node_fields_from(data)
        if error:
            return jsonify({'success': False, 'error': error}), 400

        with get_db() as conn:
            c = conn.cursor()
            try:
                c.execute('''INSERT INTO nodes (topic, tag, node_name, lwt_topic, lwt_online, lwt_offline)
                             VALUES (?, ?, ?, ?, ?, ?)''',
                          (topic, fields['tag'], fields['node_name'], fields['lwt_topic'],
                           fields['lwt_online'], fields['lwt_offline']))
                conn.commit()
            except sqlite3.IntegrityError:
                return jsonify({'success': False, 'error': 'Topic already exists'}), 400

        # Create table for this topic
        create_topic_table(topic)

        # Subscribe MQTT client
        sync_subscriptions()

        return jsonify({'success': True})


def node_fields_from(data):
    """Validate tag / node / LWT fields. Tag and Node ID are mandatory."""
    fields = {
        'tag': (data.get('tag') or '').strip(),
        'node_name': (data.get('node_name') or '').strip(),
        'lwt_topic': (data.get('lwt_topic') or '').strip(),
        'lwt_online': (data.get('lwt_online') or 'online').strip() or 'online',
        'lwt_offline': (data.get('lwt_offline') or 'offline').strip() or 'offline',
    }
    if not fields['tag']:
        return None, 'Tag is required'
    if not fields['node_name']:
        return None, 'Node ID is required'
    return fields, None


@app.route('/api/nodes/<int:node_id>', methods=['PUT'])
@login_required
def update_node(node_id):
    """Update tag, node grouping and LWT settings of a topic - REQUIRES LOGIN"""
    fields, error = node_fields_from(request.get_json(silent=True) or {})
    if error:
        return jsonify({'success': False, 'error': error}), 400

    with get_db() as conn:
        c = conn.cursor()
        c.execute('''UPDATE nodes SET tag=?, node_name=?, lwt_topic=?, lwt_online=?, lwt_offline=?
                     WHERE id=?''',
                  (fields['tag'], fields['node_name'], fields['lwt_topic'],
                   fields['lwt_online'], fields['lwt_offline'], node_id))
        if c.rowcount == 0:
            return jsonify({'error': 'Node not found'}), 404
        conn.commit()

    sync_subscriptions()
    return jsonify({'success': True})


@app.route('/api/stats')
@login_required
def stats():
    """Dashboard-wide stats: LWT status counts, node groups and DB size - REQUIRES LOGIN"""
    with get_db() as conn:
        c = conn.cursor()
        lwt_rows = load_lwt_rows(c)
        nodes = []
        for row in c.execute('SELECT * FROM nodes').fetchall():
            node = dict(row)
            node['status'], _ = topic_status(node, lwt_rows)
            nodes.append(node)
        tags = sorted({node['tag'] for node in nodes})

    summary = summarize_status(nodes)
    return jsonify({
        'topic_count': len(nodes),
        'topics': summary['topics'],
        'nodes': summary['nodes'],
        'node_list': summary['node_list'],
        'tags': tags,
        'db_size_bytes': db_file_size(),
        **get_retention_settings(),
    })


@app.route('/api/nodes/<int:node_id>', methods=['DELETE'])
@login_required
def delete_node(node_id):
    """Delete node - REQUIRES LOGIN"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT topic FROM nodes WHERE id = ?', (node_id,))
        node = c.fetchone()

        if not node:
            return jsonify({'error': 'Node not found'}), 404

        topic = node['topic']
        table_name = table_name_for(topic)

        # Drop table
        c.execute(f'DROP TABLE IF EXISTS "{table_name}"')  # nosec B608 - identifier from table_name_for(), values bound

        # Delete node
        c.execute('DELETE FROM nodes WHERE id = ?', (node_id,))
        conn.commit()

    # Unsubscribe MQTT (topics still used by other nodes stay subscribed)
    sync_subscriptions()

    return jsonify({'success': True})


@app.route('/api/nodes/<int:node_id>/history')
@login_required
def node_history(node_id):
    """Node history - REQUIRES LOGIN"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT topic FROM nodes WHERE id = ?', (node_id,))
        node = c.fetchone()

        if not node:
            return jsonify({'error': 'Node not found'}), 404

        topic = node['topic']
        table_name = table_name_for(topic)

        try:
            c.execute(f'SELECT payload, timestamp FROM "{table_name}" ORDER BY id DESC LIMIT 50')  # nosec B608 - identifier from table_name_for(), values bound
            history = []
            for row in c.fetchall():
                history.append({
                    'payload': json.loads(row['payload']),
                    'timestamp': row['timestamp']
                })

            return jsonify({'topic': topic, 'history': history})
        except Exception:
            return jsonify({'topic': topic, 'history': []})


@app.route('/api/nodes/<int:node_id>/export')
@login_required
def export_node(node_id):
    """Export node data - REQUIRES LOGIN"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT topic FROM nodes WHERE id = ?', (node_id,))
        node = c.fetchone()

        if not node:
            return jsonify({'error': 'Node not found'}), 404

        topic = node['topic']
        table_name = table_name_for(topic)

        try:
            c.execute(f'SELECT timestamp, payload FROM "{table_name}" ORDER BY id DESC')  # nosec B608 - identifier from table_name_for(), values bound
            rows = c.fetchall()

            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Timestamp', 'Payload'])

            for row in rows:
                writer.writerow([csv_cell(row['timestamp']), csv_cell(row['payload'])])

            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename={topic.replace("/", "_")}.csv'}
            )
        except Exception:
            app.logger.exception('CSV export of node %s failed', log_safe(node_id))
            return jsonify({'error': 'Export failed; see the server log'}), 500


# ============================================================================
# HEARTBEATS - verified MQTT heartbeats from edge nodes (off unless
# HEARTBEAT_MASTER_KEY is set). Read-only API for EdgeShell; see heartbeat.py.
# ============================================================================
try:
    from . import heartbeat as heartbeat_module
except ImportError:                          # run as app.py (Docker image, tests)
    import heartbeat as heartbeat_module

heartbeat_receiver = heartbeat_module.register(app, get_db, lambda: 'logged_in' in session,
                                               lambda: new_mqtt_client())  # noqa: PLW0108 - looked up at call time


@app.route('/heartbeats')
def heartbeats_page():
    """Heartbeat status of every node - REQUIRES LOGIN"""
    if 'logged_in' not in session:
        return redirect('login')
    return redirect('./?view=heartbeats')            # part of the dashboard since 1.5


@app.route('/stream')
def stream():
    """SSE stream - REQUIRES LOGIN"""
    if 'logged_in' not in session:
        return Response("Unauthorized", status=401)

    client_queue = queue.Queue(maxsize=1000)
    with sse_lock:
        if len(sse_clients) >= MAX_STREAMS:
            return Response("Too many open live views", status=503)
        sse_clients.add(client_queue)

    def event_stream():
        try:
            while True:
                try:
                    data = client_queue.get(timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with sse_lock:
                sse_clients.discard(client_queue)

    return Response(event_stream(), mimetype='text/event-stream')


def run(host='0.0.0.0', port=5000):  # nosec B104 - a server: listens on all interfaces by design
    # Emoji log lines must not crash on non-UTF-8 consoles (e.g. Windows cp1252)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass

    print(f"🚀 Starting IoT Dashboard v{__version__}")
    print(f"📁 Database path: {DB_PATH}")
    print(f"🌐 Listening on: {host}:{port}")
    print("=" * 60)
    print("MQTT LOGGING: Runs 24/7 without GUI/Login")
    print("GUI ACCESS: Requires login (change the admin password after the first sign-in)")
    print("=" * 60)

    init_db()
    init_mqtt()
    heartbeat_receiver.start(new_mqtt_client)
    if heartbeat_receiver.enabled:
        print("💓 Heartbeat receiver on: verified heartbeats from edge nodes")

    # Start watchdog and retention threads
    threading.Thread(target=mqtt_watchdog, daemon=True).start()
    threading.Thread(target=retention_worker, daemon=True).start()

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    run(host=os.getenv('HOST', '0.0.0.0'), port=env_int('PORT', 5000))  # nosec B104 - set HOST to narrow it
