from flask import Flask, jsonify, request, Response, session, redirect, url_for, send_from_directory
import sqlite3
import json
import paho.mqtt.client as mqtt
import threading
import time
import csv
import io
import os
import secrets
from datetime import datetime
from contextlib import contextmanager
import queue
import pytz
from functools import wraps
import hashlib

__version__ = '1.1.0'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')

app = Flask(__name__)

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
    return topic.replace('/', '_').replace('#', 'wildcard').replace('+', 'plus')


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


# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


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
                with open(key_file, 'w') as f:
                    f.write(key)
            except OSError:
                pass
    app.config['SECRET_KEY'] = key


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

        # Key/value app settings (retention etc.)
        c.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )''')

        # Insert default user if not exists
        c.execute('SELECT COUNT(*) FROM users')
        if c.fetchone()[0] == 0:
            default_password = hash_password('admin123')
            c.execute("INSERT INTO users (id, username, password) VALUES (1, 'admin', ?)", (default_password,))
            print("✅ Default user created: admin/admin123")

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

        # Retention defaults (0 = disabled); env values seed a fresh database
        for key, env_name in (('retention_days', 'RETENTION_DAYS'), ('retention_max_entries', 'RETENTION_MAX_ENTRIES')):
            c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
                      (key, str(max(env_int(env_name, 0), 0))))

        conn.commit()


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
                                  WHERE CAST(strftime('%s', timestamp) AS INTEGER) < ?''', (cutoff,))
                    deleted += max(c.rowcount, 0)
                if max_entries > 0:
                    c.execute(f'''DELETE FROM "{table_name}" WHERE id <= (
                                    SELECT id FROM "{table_name}" ORDER BY id DESC LIMIT 1 OFFSET ?)''',
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
        )''')
        conn.commit()
    return table_name


def new_mqtt_client():
    # paho-mqtt 2.x requires an explicit callback API version
    if hasattr(mqtt, 'CallbackAPIVersion'):
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    return mqtt.Client()


# MQTT callbacks - THESE RUN WITHOUT GUI/LOGIN!
def on_connect(client, userdata, flags, rc, properties=None):
    global mqtt_connected
    if rc == 0:
        print("✅ Connected to MQTT broker")
        mqtt_connected = True
        # Subscribe to all stored topics
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT topic FROM nodes')
            topics = c.fetchall()
            for row in topics:
                topic = row['topic']
                client.subscribe(topic)
                print(f"📡 Subscribed to: {topic}")
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
    try:
        topic = msg.topic
        payload_str = msg.payload.decode('utf-8', errors='replace')

        # Try to parse JSON
        try:
            payload = json.loads(payload_str)
        except ValueError:
            payload = {"value": payload_str}

        localized_time = get_localized_timestamp()

        with get_db() as conn:
            c = conn.cursor()
            # A message can match several subscriptions (exact topics and wildcards like sensors/#)
            subscriptions = [row['topic'] for row in c.execute('SELECT topic FROM nodes').fetchall()]
            matched = [sub for sub in subscriptions if mqtt.topic_matches_sub(sub, topic)]
            for sub in matched:
                c.execute(f'INSERT INTO "{table_name_for(sub)}" (timestamp, payload) VALUES (?, ?)',
                          (localized_time, json.dumps(payload)))
            conn.commit()

        if not matched:
            return

        print(f"📝 Logged data for {topic}: {json.dumps(payload)[:50]}...")

        # Push to SSE (only if someone is watching GUI)
        for sub in matched:
            publish_event({
                'topic': sub,
                'source_topic': topic,
                'payload': payload,
                'timestamp': localized_time
            })

    except Exception as e:
        print(f"❌ Error processing message: {e}")


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

# ============================================================================
# PUBLIC ENDPOINTS - NO LOGIN REQUIRED (for health checks and monitoring)
# ============================================================================

@app.route('/api/health')
def health():
    """Health check endpoint - NO AUTH REQUIRED"""
    return jsonify({
        'status': 'healthy',
        'mqtt_connected': mqtt_connected,
        'version': __version__,
        'timestamp': datetime.now().isoformat()
    })


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
        return redirect(url_for('login_page'))
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

    if not username or not password:
        return jsonify({'success': False, 'error': 'Username and password required'}), 400

    hashed = hash_password(password)

    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, hashed))
        user = c.fetchone()

        if user:
            session['logged_in'] = True
            session['username'] = username
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401


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
    current_hashed = hash_password(current_password)

    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, current_hashed))
        user = c.fetchone()

        if not user:
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
        return jsonify({'success': False, 'error': str(e)})


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
            c.execute('SELECT * FROM nodes ORDER BY created_at DESC')
            nodes = []
            for row in c.fetchall():
                node = dict(row)
                table_name = table_name_for(node['topic'])

                # Get last value
                try:
                    c.execute(f'SELECT payload, timestamp FROM "{table_name}" ORDER BY id DESC LIMIT 1')
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

        with get_db() as conn:
            c = conn.cursor()
            try:
                c.execute('INSERT INTO nodes (topic) VALUES (?)', (topic,))
                conn.commit()

                # Create table for this topic
                create_topic_table(topic)

                # Subscribe MQTT client
                if mqtt_client:
                    mqtt_client.subscribe(topic)

                return jsonify({'success': True})
            except sqlite3.IntegrityError:
                return jsonify({'success': False, 'error': 'Topic already exists'}), 400


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

        # Unsubscribe MQTT
        if mqtt_client:
            mqtt_client.unsubscribe(topic)

        # Drop table
        c.execute(f'DROP TABLE IF EXISTS "{table_name}"')

        # Delete node
        c.execute('DELETE FROM nodes WHERE id = ?', (node_id,))
        conn.commit()

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
            c.execute(f'SELECT payload, timestamp FROM "{table_name}" ORDER BY id DESC LIMIT 50')
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
            c.execute(f'SELECT timestamp, payload FROM "{table_name}" ORDER BY id DESC')
            rows = c.fetchall()

            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Timestamp', 'Payload'])

            for row in rows:
                writer.writerow([row['timestamp'], row['payload']])

            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename={topic.replace("/", "_")}.csv'}
            )
        except Exception as e:
            return jsonify({'error': str(e)}), 500


@app.route('/stream')
def stream():
    """SSE stream - REQUIRES LOGIN"""
    if 'logged_in' not in session:
        return Response("Unauthorized", status=401)

    client_queue = queue.Queue(maxsize=1000)
    with sse_lock:
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


def run(host='0.0.0.0', port=5000):
    print(f"🚀 Starting IoT Dashboard v{__version__}")
    print(f"📁 Database path: {DB_PATH}")
    print(f"🌐 Listening on: {host}:{port}")
    print("=" * 60)
    print("MQTT LOGGING: Runs 24/7 without GUI/Login")
    print("GUI ACCESS: Requires login (admin/admin123)")
    print("=" * 60)

    init_db()
    init_mqtt()

    # Start watchdog and retention threads
    threading.Thread(target=mqtt_watchdog, daemon=True).start()
    threading.Thread(target=retention_worker, daemon=True).start()

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    run(host=os.getenv('HOST', '0.0.0.0'), port=env_int('PORT', 5000))
