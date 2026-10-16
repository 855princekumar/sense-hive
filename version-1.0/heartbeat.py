"""Heartbeat receiver: verifies the encrypted heartbeats that the MQTT
heartbeat agent (github.com/855princekumar/mqtt-heartbeat-service) publishes
on a public broker, keeps per-node state, and serves it read-only.

Off unless HEARTBEAT_MASTER_KEY is set. It uses its own MQTT connection (TLS
to the heartbeat broker), separate from the broker configured in the
dashboard, and its own tables, so nothing else in SenseHive changes.

Settings (environment)
    HEARTBEAT_MASTER_KEY    64 hex characters, the fleet master key (secret)
    HEARTBEAT_API_TOKEN     bearer token for GET /api/heartbeat/* (secret; at
                            least 32 characters). Without it only a signed-in
                            dashboard user can read the API.
    HEARTBEAT_BROKER        default broker.hivemq.com
    HEARTBEAT_PORT          default 8883
    HEARTBEAT_TLS           default true
    HEARTBEAT_STALE_SECONDS a node with no heartbeat for this long is "silent" (35)
    HEARTBEAT_KEEP_DAYS     per-minute presence and events kept for (30)
"""
import hmac
import os
import threading
import time

try:
    from . import heartbeat_protocol as hp
except ImportError:                     # run as app.py (Docker image, tests)
    import heartbeat_protocol as hp


def _flag(name, default):
    v = os.getenv(name)
    return default if v is None or not v.strip() else v.strip().lower() in ('1', 'true', 'yes', 'on')


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS hb_nodes (
        name TEXT PRIMARY KEY, status TEXT, session REAL, last_t REAL, last_seen REAL,
        since REAL, version TEXT, lwt_at REAL)''',
    '''CREATE TABLE IF NOT EXISTS hb_minutes (
        name TEXT NOT NULL, minute INTEGER NOT NULL, PRIMARY KEY (name, minute))''',
    '''CREATE TABLE IF NOT EXISTS hb_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, status TEXT NOT NULL, at REAL NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS hb_events_at ON hb_events (at)',
)


class Receiver:
    """One per process. `db` opens a sqlite3 connection (the app's get_db)."""

    def __init__(self, db, master=None, clock=time.time):
        key = master if master is not None else os.getenv('HEARTBEAT_MASTER_KEY', '').strip()
        self.master = bytes.fromhex(key) if isinstance(key, str) and key else key or None
        if self.master is not None and len(self.master) != 32:
            raise ValueError('HEARTBEAT_MASTER_KEY must be 64 hex characters (32 bytes)')
        self.db, self.clock = db, clock
        self.tracker = hp.Tracker()
        self.lock = threading.Lock()
        self.client, self.connected, self.windows = None, False, set()
        self.stale = _int('HEARTBEAT_STALE_SECONDS', 35)
        self.keep_days = max(_int('HEARTBEAT_KEEP_DAYS', 30), 1)
        self.rejected = 0

    @property
    def enabled(self):
        return self.master is not None

    # ------------------------------------------------------------------ storage
    def init_db(self):
        with self.db() as conn:
            for stmt in SCHEMA:
                conn.execute(stmt)
            conn.commit()
            for r in conn.execute('SELECT * FROM hb_nodes'):
                self.tracker.nodes[r['name']] = {
                    'session': r['session'] or 0, 'last_t': r['last_t'] or 0,
                    'online': {'online': True, 'offline': False}.get(r['status']),
                    'last_seen': r['last_seen'], 'since': r['since'], 'version': r['version']}

    def _save(self, name, status_changed):
        st = self.tracker.nodes[name]
        status = self.tracker.status(name, now=self.clock(), stale_after=self.stale)
        with self.db() as conn:
            conn.execute('INSERT OR REPLACE INTO hb_nodes (name, status, session, last_t, last_seen, since, version, lwt_at) '
                         'VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT lwt_at FROM hb_nodes WHERE name = ?))',
                         (name, status, st['session'], st['last_t'], st['last_seen'], st['since'], st['version'], name))
            if status == 'online':
                conn.execute('INSERT OR IGNORE INTO hb_minutes (name, minute) VALUES (?, ?)',
                             (name, int(self.clock() // 60)))
            if status == 'offline':
                conn.execute('UPDATE hb_nodes SET lwt_at = ? WHERE name = ?', (self.clock(), name))
            if status_changed:
                conn.execute('INSERT INTO hb_events (name, status, at) VALUES (?, ?, ?)', (name, status, self.clock()))
            conn.commit()

    # ------------------------------------------------------------------ messages
    def handle(self, topic, payload):
        """One MQTT message. Anything not authentic, fresh and for us is dropped
        silently (and counted): strangers on a public broker get no feedback."""
        try:
            body = hp.open_message(self.master, topic, payload)
        except hp.Invalid:
            self.rejected += 1
            return False
        with self.lock:
            before = self.tracker.status(body['n'], now=self.clock(), stale_after=self.stale)
            if not self.tracker.accept(body, now=self.clock()):
                self.rejected += 1
                return False
            after = self.tracker.status(body['n'], now=self.clock(), stale_after=self.stale)
            self._save(body['n'], before != after)
        return True

    # ------------------------------------------------------------------ MQTT
    def wanted_topics(self):
        w = hp.window(self.clock())
        tk = hp.topic_key(self.master)
        return {hp.topic(tk, x) for x in (w - 1, w, w + 1)}       # clock skew and late wills

    def resubscribe(self):
        if not self.client or not self.connected:
            return
        wanted = self.wanted_topics()
        for t in wanted - self.windows:
            self.client.subscribe(t, qos=1)
        for t in self.windows - wanted:
            self.client.unsubscribe(t)
        self.windows = wanted

    def start(self, client_factory):
        """Connect and keep the subscriptions current (daemon threads)."""
        if not self.enabled:
            return
        c = client_factory()
        if _flag('HEARTBEAT_TLS', True):
            c.tls_set()

        def on_connect(client, userdata, flags, rc, *rest):
            self.connected = (getattr(rc, 'value', rc) or 0) == 0
            self.windows = set()
            self.resubscribe()

        def on_disconnect(client, userdata, *args):
            self.connected = False

        c.on_connect, c.on_disconnect = on_connect, on_disconnect
        c.on_message = lambda client, userdata, msg: self.handle(msg.topic, msg.payload)
        c.reconnect_delay_set(min_delay=2, max_delay=60)
        self.client = c
        try:
            c.connect_async(os.getenv('HEARTBEAT_BROKER', 'broker.hivemq.com'), _int('HEARTBEAT_PORT', 8883), 30)
        except AttributeError:
            c.connect(os.getenv('HEARTBEAT_BROKER', 'broker.hivemq.com'), _int('HEARTBEAT_PORT', 8883), 30)
        c.loop_start()
        threading.Thread(target=self._housekeeping, daemon=True, name='heartbeat-housekeeping').start()

    def _housekeeping(self):
        last_prune = 0
        while True:
            time.sleep(20)
            try:
                self.resubscribe()
                self.refresh_silent()
                if time.time() - last_prune > 3600:
                    self.prune()
                    last_prune = time.time()
            except Exception as e:
                print(f'heartbeat housekeeping: {type(e).__name__}')

    def refresh_silent(self):
        """Record nodes that went silent (no heartbeat and no will)."""
        now = self.clock()
        with self.lock, self.db() as conn:
            for name in list(self.tracker.nodes):
                status = self.tracker.status(name, now=now, stale_after=self.stale)
                row = conn.execute('SELECT status FROM hb_nodes WHERE name = ?', (name,)).fetchone()
                if row and row['status'] != status:
                    conn.execute('UPDATE hb_nodes SET status = ? WHERE name = ?', (status, name))
                    conn.execute('INSERT INTO hb_events (name, status, at) VALUES (?, ?, ?)', (name, status, now))
            conn.commit()

    def prune(self):
        cutoff = self.clock() - self.keep_days * 86400
        with self.db() as conn:
            conn.execute('DELETE FROM hb_minutes WHERE minute < ?', (int(cutoff // 60),))
            conn.execute('DELETE FROM hb_events WHERE at < ?', (cutoff,))
            conn.commit()

    # ------------------------------------------------------------------ API data
    def nodes(self):
        now = self.clock()
        with self.db() as conn:
            rows = conn.execute('SELECT * FROM hb_nodes ORDER BY name').fetchall()
        out = []
        for r in rows:
            out.append({'name': r['name'],
                        'status': self.tracker.status(r['name'], now=now, stale_after=self.stale) or r['status'],
                        'last_seen': r['last_seen'], 'since': r['since'], 'lwt_at': r['lwt_at'],
                        'agent_version': r['version']})
        return out

    def minutes(self, since, until=None):
        until = until if until is not None else self.clock()
        with self.db() as conn:
            rows = conn.execute('SELECT name, minute FROM hb_minutes WHERE minute >= ? AND minute < ? ORDER BY name, minute',
                                (int(since // 60), int(until // 60) + 1)).fetchall()
        out = {}
        for r in rows:
            out.setdefault(r['name'], []).append(r['minute'] * 60)
        return out

    def events(self, since, limit=1000):
        with self.db() as conn:
            rows = conn.execute('SELECT id, name, status, at FROM hb_events WHERE at >= ? ORDER BY id LIMIT ?',
                                (since, limit)).fetchall()
        return [dict(r) for r in rows]

    def token_ok(self, header):
        token = os.getenv('HEARTBEAT_API_TOKEN', '')
        if len(token) < 32 or not header or not header.startswith('Bearer '):
            return False
        return hmac.compare_digest(header[7:].strip().encode(), token.encode())


def register(app, get_db, login_ok, client_factory):
    """Add the read-only API to the Flask app and return the receiver."""
    from flask import jsonify, request

    rx = Receiver(get_db)

    def allowed():
        return rx.token_ok(request.headers.get('Authorization', '')) or login_ok()

    def number(name, default):
        try:
            return float(request.args.get(name, default))
        except (TypeError, ValueError):
            return default

    @app.route('/api/heartbeat/status')
    def heartbeat_status():
        if not allowed():
            return jsonify({'error': 'Authentication required'}), 401
        return jsonify({'enabled': rx.enabled, 'connected': rx.connected, 'rejected': rx.rejected,
                        'nodes': len(rx.tracker.nodes)})

    @app.route('/api/heartbeat/nodes')
    def heartbeat_nodes():
        if not allowed():
            return jsonify({'error': 'Authentication required'}), 401
        return jsonify({'enabled': rx.enabled, 'connected': rx.connected, 'nodes': rx.nodes() if rx.enabled else []})

    @app.route('/api/heartbeat/minutes')
    def heartbeat_minutes():
        """Minutes (unix seconds) in which each node sent a verified heartbeat."""
        if not allowed():
            return jsonify({'error': 'Authentication required'}), 401
        since = max(number('since', rx.clock() - 3600), rx.clock() - rx.keep_days * 86400)
        return jsonify({'since': since, 'minutes': rx.minutes(since) if rx.enabled else {}})

    @app.route('/api/heartbeat/events')
    def heartbeat_events():
        if not allowed():
            return jsonify({'error': 'Authentication required'}), 401
        return jsonify({'events': rx.events(number('since', 0), limit=1000) if rx.enabled else []})

    return rx
