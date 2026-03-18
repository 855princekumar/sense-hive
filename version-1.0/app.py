from flask import Flask, render_template_string, jsonify, request, Response, session, redirect, url_for
import sqlite3
import json
import paho.mqtt.client as mqtt
import threading
import time
import csv
import io
import os
from datetime import datetime
from contextlib import contextmanager
import queue
import pytz
from functools import wraps
import hashlib

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'iot-dashboard-secret-key-change-in-production')

# Database path - check environment variable or use default
DB_PATH = os.getenv('DB_PATH', '/app/data/iot_dashboard.db')
DB_DIR = os.path.dirname(DB_PATH)

# Create data directory if it doesn't exist
os.makedirs(DB_DIR, exist_ok=True)

sse_queue = queue.Queue()
mqtt_client = None
mqtt_connected = False

# Database helper
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10.0)
    conn.row_factory = sqlite3.Row
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

# Initialize database
def init_db():
    with get_db() as conn:
        c = conn.cursor()
        
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
        
        # Insert default user if not exists
        c.execute('SELECT COUNT(*) FROM users')
        if c.fetchone()[0] == 0:
            default_password = hash_password('admin123')
            c.execute('INSERT INTO users (id, username, password) VALUES (1, "admin", ?)', (default_password,))
            print("✅ Default user created: admin/admin123")
        
        # Check if broker config exists
        c.execute('SELECT COUNT(*) FROM broker_config')
        if c.fetchone()[0] == 0:
            # Use environment variables for default broker or fallback to HiveMQ
            default_host = os.getenv('DEFAULT_BROKER_HOST', 'broker.hivemq.com')
            default_port = int(os.getenv('DEFAULT_BROKER_PORT', '1883'))
            default_username = os.getenv('DEFAULT_BROKER_USERNAME', '')
            default_password = os.getenv('DEFAULT_BROKER_PASSWORD', '')
            default_timezone = os.getenv('DEFAULT_TIMEZONE', 'UTC')
            
            c.execute('''INSERT INTO broker_config (id, host, port, username, password, timezone) 
                        VALUES (1, ?, ?, ?, ?, ?)''',
                     (default_host, default_port, default_username, default_password, default_timezone))
            print(f"✅ Initialized with default broker: {default_host}:{default_port}")
        else:
            # Add timezone column if it doesn't exist (for existing databases)
            try:
                c.execute('SELECT timezone FROM broker_config LIMIT 1')
            except sqlite3.OperationalError:
                c.execute('ALTER TABLE broker_config ADD COLUMN timezone TEXT DEFAULT "UTC"')
                print("✅ Added timezone column to existing database")
        
        conn.commit()

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
    except:
        return datetime.now(pytz.UTC).isoformat()

# Create table for topic data
def create_topic_table(topic):
    table_name = topic.replace('/', '_').replace('#', 'wildcard').replace('+', 'plus')
    with get_db() as conn:
        c = conn.cursor()
        c.execute(f'''CREATE TABLE IF NOT EXISTS "{table_name}" (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payload TEXT NOT NULL
        )''')
        conn.commit()
    return table_name

# MQTT callbacks - THESE RUN WITHOUT GUI/LOGIN!
def on_connect(client, userdata, flags, rc):
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

def on_disconnect(client, userdata, rc):
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
        payload_str = msg.payload.decode('utf-8')
        
        # Try to parse JSON
        try:
            payload = json.loads(payload_str)
        except:
            payload = {"value": payload_str}
        
        # Store in database with localized timestamp
        table_name = topic.replace('/', '_').replace('#', 'wildcard').replace('+', 'plus')
        localized_time = get_localized_timestamp()
        
        with get_db() as conn:
            c = conn.cursor()
            c.execute(f'INSERT INTO "{table_name}" (timestamp, payload) VALUES (?, ?)', 
                     (localized_time, json.dumps(payload)))
            conn.commit()
        
        print(f"📝 Logged data for {topic}: {json.dumps(payload)[:50]}...")
        
        # Push to SSE (only if someone is watching GUI)
        sse_queue.put({
            'topic': topic,
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
    
    mqtt_client = mqtt.Client()
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
            except:
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
    with open('templates/index.html', 'r') as f:
        return render_template_string(f.read())

@app.route('/login')
def login_page():
    """Login page"""
    with open('templates/login.html', 'r') as f:
        return render_template_string(f.read())

@app.route('/api/login', methods=['POST'])
def login():
    """Login endpoint"""
    data = request.json
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
    data = request.json
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
        data = request.json
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
    data = request.json
    test_client = mqtt.Client()
    
    if data.get('username'):
        test_client.username_pw_set(data['username'], data.get('password', ''))
    
    try:
        test_client.connect(data['host'], data['port'], 10)
        test_client.disconnect()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

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
                table_name = node['topic'].replace('/', '_').replace('#', 'wildcard').replace('+', 'plus')
                
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
                except:
                    node['last_value'] = None
                    node['last_updated'] = None
                
                nodes.append(node)
            
            return jsonify(nodes)
    
    else:  # POST
        data = request.json
        topic = data['topic']
        
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
        table_name = topic.replace('/', '_').replace('#', 'wildcard').replace('+', 'plus')
        
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
        table_name = topic.replace('/', '_').replace('#', 'wildcard').replace('+', 'plus')
        
        try:
            c.execute(f'SELECT payload, timestamp FROM "{table_name}" ORDER BY id DESC LIMIT 50')
            history = []
            for row in c.fetchall():
                history.append({
                    'payload': json.loads(row['payload']),
                    'timestamp': row['timestamp']
                })
            
            return jsonify({'topic': topic, 'history': history})
        except:
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
        table_name = topic.replace('/', '_').replace('#', 'wildcard').replace('+', 'plus')
        
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
    
    def event_stream():
        while True:
            try:
                data = sse_queue.get(timeout=30)
                yield f"data: {json.dumps(data)}\n\n"
            except queue.Empty:
                yield f": keepalive\n\n"
    
    return Response(event_stream(), mimetype='text/event-stream')

if __name__ == '__main__':
    print("🚀 Starting IoT Dashboard")
    print(f"📁 Database path: {DB_PATH}")
    print(f"🌐 Listening on: 0.0.0.0:5000")
    print("=" * 60)
    print("MQTT LOGGING: Runs 24/7 without GUI/Login")
    print("GUI ACCESS: Requires login (admin/admin123)")
    print("=" * 60)
    
    init_db()
    init_mqtt()
    
    # Start watchdog thread
    threading.Thread(target=mqtt_watchdog, daemon=True).start()
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)