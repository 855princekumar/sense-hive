"""Heartbeat receiver: verifies the encrypted heartbeats that the MQTT
heartbeat agent (github.com/855princekumar/mqtt-heartbeat-service) publishes
on a public broker, keeps per-node state, and serves it read-only.

Off unless HEARTBEAT_MASTER_KEY is set. It uses its own MQTT connection (TLS
to the heartbeat broker), separate from the broker configured in the
dashboard, and its own tables, so nothing else in SenseHive changes.

Settings (environment)
    HEARTBEAT_MASTER_KEY    64 hex characters, the fleet master key (secret), or
                            "auto": a random key made once and kept next to the
                            database (heartbeat_master_key, owner only)
    HEARTBEAT_API_TOKEN     bearer token for GET /api/heartbeat/* (secret; at
                            least 32 characters). Without it only a signed-in
                            dashboard user can read the API.
    HEARTBEAT_BROKER        default broker.hivemq.com
    HEARTBEAT_PORT          default 8883
    HEARTBEAT_TLS           default true
    HEARTBEAT_BROKER_USERNAME / HEARTBEAT_BROKER_PASSWORD
                            SenseHive's own login on the heartbeat broker (secret)
    HEARTBEAT_NODE_BROKER   host[:port] nodes use for the same broker, written into join
                            tokens, when it differs from HEARTBEAT_BROKER (e.g. SenseHive
                            reaches it by a Docker name, nodes by a public name)
    HEARTBEAT_STALE_SECONDS a node with no heartbeat for this long is "silent" (35)
    HEARTBEAT_KEEP_DAYS     per-minute presence and events kept for (30)
    HEARTBEAT_BEATS_HOURS   every verified heartbeat kept for (48; 0 keeps none)
    HEARTBEAT_MIN_SPACING   seconds a node must leave between heartbeats (2);
                            faster ones are dropped, so a stolen node key cannot
                            flood the history
"""
import base64
import csv
import hashlib
import hmac
import json
import re
import secrets
import io
import math
import os
import threading
import time

try:
    from . import heartbeat_protocol as hp
except ImportError:                     # run as app.py (Docker image, tests)
    import heartbeat_protocol as hp


NODE_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$')
JOIN_PREFIX = 'hbj1.'
JOIN_BULK_MAX = 500


def master_from_env(key_file=None):
    """HEARTBEAT_MASTER_KEY as hex, '' when off. "auto" reads (or makes, once)
    a random key in `key_file`, so every SenseHive has its own fleet."""
    key = os.getenv('HEARTBEAT_MASTER_KEY', '').strip()
    if key.lower() != 'auto':
        return key
    if not key_file:
        raise ValueError('HEARTBEAT_MASTER_KEY=auto needs a data folder')
    try:
        with open(key_file) as f:
            saved = f.read().strip()
        if re.fullmatch(r'[0-9a-fA-F]{64}', saved):
            return saved
    except OSError:
        pass
    saved = secrets.token_hex(32)
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)        # owner only
    with os.fdopen(fd, 'w') as f:
        f.write(saved)
    return saved


def fleet_id(topic_key):
    """A short public name for a fleet: nodes and SenseHive show the same one
    when they share a master key. Reveals nothing about the keys."""
    return hashlib.sha256(b'fleet id|' + topic_key).hexdigest()[:12]


def join_token(master, node, broker, port, tls):
    """Everything one node needs, as one line to paste into the agent's setup.py:
    its name and keys (never the master key) and the broker SenseHive listens on."""
    p = hp.provision(master, node)
    body = {'v': 1, 'node': node, 'kid': p['HB_KID'], 'nk': p['HB_NODE_KEY'], 'tk': p['HB_TOPIC_KEY'],
            'broker': broker, 'port': port, 'tls': tls}
    text = json.dumps(body, separators=(',', ':'), sort_keys=True)
    body['c'] = hashlib.sha256(text.encode()).hexdigest()[:8]                 # catches a cut or mistyped paste
    raw = json.dumps(body, separators=(',', ':'), sort_keys=True).encode()
    return JOIN_PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip('=')


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
    'CREATE INDEX IF NOT EXISTS hb_events_name_at ON hb_events (name, at)',
    # Every verified message: node (hb_nodes rowid), receive time, kind (0 birth,
    # 1 heartbeat, 2 last will) and the delay from the node's clock to ours.
    '''CREATE TABLE IF NOT EXISTS hb_beats (
        node INTEGER NOT NULL, t REAL NOT NULL, kind INTEGER NOT NULL, lag REAL,
        PRIMARY KEY (node, t)) WITHOUT ROWID''',
    'CREATE INDEX IF NOT EXISTS hb_beats_t ON hb_beats (t)',
)

KINDS = {'birth': 0, 'hb': 1, 'lwt': 2}
KIND_NAMES = {v: k for k, v in KINDS.items()}
RANGES = {'1m': 60, '1h': 3600, '1d': 86400, '7d': 7 * 86400, '30d': 30 * 86400}
CSV_KINDS = ('beats', 'minutes', 'events')
AGENT_INTERVAL = 10                     # the agent's default heartbeat interval, in seconds


def break_limit(typical):
    """A gap longer than this is a break: 2.5 heartbeat intervals, and at least 5 s more than one.
    With fewer than two heartbeats to measure, the agent's default interval is assumed."""
    step = typical or AGENT_INTERVAL
    return max(2.5 * step, step + 5)


def csv_cell(value):
    """A CSV cell a spreadsheet never runs as a formula (=, +, -, @, tab, CR).
    Plain numbers such as -12.5 stay numbers."""
    text = '' if value is None else str(value)
    if text[:1] in ('-', '+'):
        try:
            float(text)
            return text
        except ValueError:
            pass
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def iso(t):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t)) if t is not None else ''


class Receiver:
    """One per process. `db` opens a sqlite3 connection (the app's get_db)."""

    def __init__(self, db, master=None, clock=time.time, key_file=None):
        key = master if master is not None else master_from_env(key_file)
        self.master = bytes.fromhex(key) if isinstance(key, str) and key else key or None
        if self.master is not None and len(self.master) != 32:
            raise ValueError('HEARTBEAT_MASTER_KEY must be 64 hex characters (32 bytes)')
        self.db, self.clock = db, clock
        self.tracker = hp.Tracker()
        self.lock = threading.Lock()
        self.client, self.connected, self.windows = None, False, set()
        self.stale = _int('HEARTBEAT_STALE_SECONDS', 35)
        self.keep_days = max(_int('HEARTBEAT_KEEP_DAYS', 30), 1)
        self.beats_hours = min(max(_int('HEARTBEAT_BEATS_HOURS', 48), 0), 24 * 31)
        self.min_spacing = max(_int('HEARTBEAT_MIN_SPACING', 2), 0)
        self.bin_days = max(_int('HEARTBEAT_BIN_DAYS', 30), 1)     # the recycle bin keeps nodes this long
        self.rejected = 0
        self.flooded = 0
        self.last_rx = {}

    @property
    def enabled(self):
        return self.master is not None

    def broker(self):
        """The broker as nodes reach it: host, port, TLS (what a join token carries)."""
        host = os.getenv('HEARTBEAT_BROKER', 'broker.hivemq.com').strip() or 'broker.hivemq.com'
        port = _int('HEARTBEAT_PORT', 8883)
        node = os.getenv('HEARTBEAT_NODE_BROKER', '').strip()
        if node:
            name, _, num = node.partition(':')
            if re.fullmatch(r'[A-Za-z0-9.-]{1,253}', name) and (not num or (num.isdigit() and 0 < int(num) < 65536)):
                host, port = name, int(num) if num else port
        return host, port, _flag('HEARTBEAT_TLS', True)

    def fleet(self):
        return fleet_id(hp.topic_key(self.master)) if self.enabled else ''

    def join(self, node):
        host, port, tls = self.broker()
        return join_token(self.master, node, host, port, tls)

    # ------------------------------------------------------------------ storage
    def init_db(self):
        with self.db() as conn:
            for stmt in SCHEMA:
                conn.execute(stmt)
            cols = {r[1] for r in conn.execute('PRAGMA table_info(hb_nodes)')}
            for col in ('binned_at', 'came_back_at'):          # the recycle bin (1.7)
                if col not in cols:
                    conn.execute(f'ALTER TABLE hb_nodes ADD COLUMN {col} REAL')
            conn.commit()
            for r in conn.execute('SELECT * FROM hb_nodes'):
                self.tracker.nodes[r['name']] = {
                    'session': r['session'] or 0, 'last_t': r['last_t'] or 0,
                    'online': {'online': True, 'offline': False}.get(r['status']),
                    'last_seen': r['last_seen'], 'since': r['since'], 'version': r['version']}

    def _save(self, name, status_changed, body=None):
        st = self.tracker.nodes[name]
        now = self.clock()
        status = self.tracker.status(name, now=now, stale_after=self.stale)
        with self.db() as conn:
            binned = conn.execute('SELECT binned_at FROM hb_nodes WHERE name = ?', (name,)).fetchone()
            if binned and binned['binned_at']:
                # in the recycle bin: verified, not stored; note that it came back
                if body is not None and body['k'] != 'lwt':
                    conn.execute('UPDATE hb_nodes SET came_back_at = ?, last_seen = ? WHERE name = ?',
                                 (now, st['last_seen'], name))
                    conn.commit()
                return
            # an UPSERT keeps the row (and its rowid, which hb_beats refers to)
            conn.execute('INSERT INTO hb_nodes (name, status, session, last_t, last_seen, since, version) '
                         'VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(name) DO UPDATE SET status = excluded.status, '
                         'session = excluded.session, last_t = excluded.last_t, last_seen = excluded.last_seen, '
                         'since = excluded.since, version = excluded.version',
                         (name, status, st['session'], st['last_t'], st['last_seen'], st['since'], st['version']))
            if body is not None and self.beats_hours:
                node = conn.execute('SELECT rowid FROM hb_nodes WHERE name = ?', (name,)).fetchone()[0]
                lag = round(now - float(body['t']), 3) if body['k'] != 'lwt' else None
                conn.execute('INSERT OR IGNORE INTO hb_beats (node, t, kind, lag) VALUES (?, ?, ?, ?)',
                             (node, now, KINDS.get(body['k'], 1), lag))
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
            now = self.clock()
            # Authentic but too fast: only a holder of this node's key can do that
            # (a stolen key); drop it so nobody can flood the history or the CPU.
            if body['k'] == 'hb' and now - self.last_rx.get(body['n'], 0) < self.min_spacing:
                self.flooded += 1
                return False
            before = self.tracker.status(body['n'], now=now, stale_after=self.stale)
            if not self.tracker.accept(body, now=now):
                self.rejected += 1
                return False
            if body['k'] == 'hb':                   # spacing is measured between heartbeats only
                self.last_rx[body['n']] = now
            after = self.tracker.status(body['n'], now=now, stale_after=self.stale)
            self._save(body['n'], before != after, body)
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
        user = os.getenv('HEARTBEAT_BROKER_USERNAME', '').strip()
        if user:
            c.username_pw_set(user, os.getenv('HEARTBEAT_BROKER_PASSWORD', ''))

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
                row = conn.execute('SELECT status, binned_at FROM hb_nodes WHERE name = ?', (name,)).fetchone()
                if row and row['status'] != status and not row['binned_at']:
                    conn.execute('UPDATE hb_nodes SET status = ? WHERE name = ?', (status, name))
                    conn.execute('INSERT INTO hb_events (name, status, at) VALUES (?, ?, ?)', (name, status, now))
            conn.commit()

    def prune(self):
        cutoff = self.clock() - self.keep_days * 86400
        with self.db() as conn:
            conn.execute('DELETE FROM hb_minutes WHERE minute < ?', (int(cutoff // 60),))
            conn.execute('DELETE FROM hb_events WHERE at < ?', (cutoff,))
            conn.execute('DELETE FROM hb_beats WHERE t < ?', (self.clock() - self.beats_hours * 3600,))
            conn.commit()
        old = [r['name'] for r in self._binned_rows() if r['binned_at'] < self.clock() - self.bin_days * 86400]
        if old:
            self.delete_forever(old)

    # ------------------------------------------------------------------ recycle bin
    def _binned_rows(self):
        with self.db() as conn:
            return conn.execute('SELECT * FROM hb_nodes WHERE binned_at IS NOT NULL ORDER BY binned_at DESC').fetchall()

    def bin(self, names):
        """Move nodes to the recycle bin: hidden everywhere, still verified, nothing stored."""
        now = self.clock()
        with self.db() as conn:
            n = sum(conn.execute('UPDATE hb_nodes SET binned_at = ?, came_back_at = NULL WHERE name = ? AND binned_at IS NULL',
                                 (now, name)).rowcount for name in names)
            conn.commit()
        return n

    def restore(self, names):
        with self.db() as conn:
            n = sum(conn.execute('UPDATE hb_nodes SET binned_at = NULL, came_back_at = NULL WHERE name = ? '
                                 'AND binned_at IS NOT NULL', (name,)).rowcount for name in names)
            conn.commit()
        return n

    def delete_forever(self, names):
        """Only nodes in the bin: their heartbeats, minutes, events and the node itself."""
        gone = 0
        with self.db() as conn:
            for name in names:
                row = conn.execute('SELECT rowid FROM hb_nodes WHERE name = ? AND binned_at IS NOT NULL', (name,)).fetchone()
                if not row:
                    continue
                conn.execute('DELETE FROM hb_beats WHERE node = ?', (row[0],))
                conn.execute('DELETE FROM hb_minutes WHERE name = ?', (name,))
                conn.execute('DELETE FROM hb_events WHERE name = ?', (name,))
                conn.execute('DELETE FROM hb_nodes WHERE rowid = ?', (row[0],))
                self.tracker.nodes.pop(name, None)
                self.last_rx.pop(name, None)
                gone += 1
            conn.commit()
        return gone

    def binned(self):
        now = self.clock()
        return [{'name': r['name'], 'binned_at': r['binned_at'], 'came_back_at': r['came_back_at'],
                 'last_seen': r['last_seen'], 'agent_version': r['version'],
                 'days_left': max(0, round(self.bin_days - (now - r['binned_at']) / 86400, 1))}
                for r in self._binned_rows()]

    # ------------------------------------------------------------------ API data
    def nodes(self):
        now = self.clock()
        with self.db() as conn:
            rows = conn.execute('SELECT * FROM hb_nodes WHERE binned_at IS NULL ORDER BY name').fetchall()
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

    def node_names(self):
        with self.db() as conn:
            return [r['name'] for r in conn.execute('SELECT name FROM hb_nodes WHERE binned_at IS NULL ORDER BY name')]

    def beats(self, name, since, until):
        with self.db() as conn:
            rows = conn.execute('SELECT b.t, b.kind, b.lag FROM hb_beats b JOIN hb_nodes n ON n.rowid = b.node '
                                'WHERE n.name = ? AND b.t >= ? AND b.t <= ? ORDER BY b.t LIMIT 200000',
                                (name, since, until)).fetchall()
        return [(r['t'], r['kind'], r['lag']) for r in rows]

    def node_events(self, name, since, until):
        with self.db() as conn:
            before = conn.execute('SELECT status, at FROM hb_events WHERE name = ? AND at < ? ORDER BY at DESC LIMIT 1',
                                  (name, since)).fetchone()
            rows = conn.execute('SELECT status, at FROM hb_events WHERE name = ? AND at >= ? AND at <= ? ORDER BY at',
                                (name, since, until)).fetchall()
        return ([dict(before)] if before else []) + [dict(r) for r in rows]

    def history(self, name, rng, now=None):
        """Chart data and figures for one node over a range ('1m' to '30d')."""
        now = self.clock() if now is None else now
        span = RANGES[rng]
        since = now - span
        out = {'node': name, 'range': rng, 'since': since, 'until': now,
               'events': self.node_events(name, since, now)}
        detailed = span <= 86400 and self.beats_hours * 3600 >= min(span, 3600)
        if detailed:
            beats = self.beats(name, since, now)
            # breaks are measured between heartbeats; a last will inside an outage does not split it
            alive = [b[0] for b in beats if b[1] != KINDS['lwt']]
            gaps = [b - a for a, b in zip(alive, alive[1:])]
            typical = sorted(gaps)[len(gaps) // 2] if gaps else None
            limit = break_limit(typical)
            breaks = []
            for a, b in zip(alive, alive[1:]):
                if b - a > limit:
                    br = {'from': a, 'to': b, 'seconds': round(b - a, 1)}
                    lwt = next((t for t, k, _ in beats if k == KINDS['lwt'] and a < t < b), None)
                    if lwt:
                        br['lwt_at'] = lwt
                    breaks.append(br)
            current = self.current_break(name, alive[-1] if alive else None, limit, now)
            if current:
                breaks.append(current)
            lags = [b[2] for b in beats if b[2] is not None]
            out.update(kind='beats', points=[[round(t, 3), k, lag] for t, k, lag in beats],
                       interval=round(typical, 1) if typical else None, breaks=breaks,
                       received=sum(1 for b in beats if b[1] != KINDS['lwt']),
                       lag_ms=round(1000 * sorted(lags)[len(lags) // 2]) if lags else None,
                       longest_break=max((b['seconds'] for b in breaks), default=0), current_break=current)
        else:
            minutes = set(self.minutes(since, now).get(name, []))
            first = int(since // 3600) * 3600
            buckets = []
            for h in range(first, int(now) + 1, 3600):
                total = len([m for m in range(h, h + 3600, 60) if since <= m <= now])
                up = len([m for m in range(h, h + 3600, 60) if m in minutes])
                buckets.append([h, up, total])
            out.update(kind='hours', points=buckets,
                       current_break=self.current_break(name, None, break_limit(None), now))
        mins = self.minutes(since, now).get(name, [])
        total = max(int(span // 60), 1)
        out['uptime'] = round(100.0 * min(len(mins), total) / total, 2)
        return out

    def current_break(self, name, last_beat, limit, now):
        """The outage still going on, or None. It starts at the node's last heartbeat,
        which may be older than the chart's range (or older than the kept heartbeats)."""
        status = self.tracker.status(name, now=now, stale_after=self.stale)
        with self.db() as conn:
            row = conn.execute('SELECT status, last_seen, lwt_at FROM hb_nodes WHERE name = ?', (name,)).fetchone()
        if row is None:
            return None
        status = status or row['status']
        known = [t for t in (last_beat, row['last_seen']) if t is not None]
        last = max(known) if known else row['lwt_at']    # only a last will was ever heard
        if last is None or status == 'online' or (status is None and now - last <= limit):
            return None
        br = {'from': last, 'to': None, 'seconds': round(now - last, 1), 'status': status or 'silent'}
        if row['lwt_at'] and row['lwt_at'] >= last and status == 'offline':
            br['lwt_at'] = row['lwt_at']
        return br

    def export_csv(self, names, since, until, what):
        """CSV text for some nodes: every heartbeat, the online minutes, or the status changes."""
        buf = io.StringIO()
        w = csv.writer(buf)
        if what == 'beats':
            w.writerow(['node', 'time_utc', 'unix_time', 'kind', 'delay_ms'])
            for name in names:
                for t, k, lag in self.beats(name, since, until):
                    w.writerow([csv_cell(name), iso(t), f'{t:.3f}', KIND_NAMES.get(k, ''),
                                '' if lag is None else round(lag * 1000)])
        elif what == 'minutes':
            w.writerow(['node', 'minute_utc', 'unix_time'])
            mins = self.minutes(since, until)
            for name in names:
                for m in mins.get(name, []):
                    w.writerow([csv_cell(name), iso(m), m])
        else:
            w.writerow(['node', 'time_utc', 'unix_time', 'status'])
            for name in names:
                for e in self.node_events(name, since, until):
                    if e['at'] >= since:
                        w.writerow([csv_cell(name), iso(e['at']), f"{e['at']:.3f}", csv_cell(e['status'])])
        return buf.getvalue()

    def token_ok(self, header):
        token = os.getenv('HEARTBEAT_API_TOKEN', '')
        if len(token) < 32 or not header or not header.startswith('Bearer '):
            return False
        return hmac.compare_digest(header[7:].strip().encode(), token.encode())


def register(app, get_db, login_ok, client_factory, data_dir=None):
    """Add the read-only API to the Flask app and return the receiver."""
    from flask import jsonify, request

    from flask import Response

    rx = Receiver(get_db, key_file=os.path.join(data_dir, 'heartbeat_master_key') if data_dir else None)
    bad_tokens = {}                     # client address -> failure times (lockout)
    bad_lock = threading.Lock()

    def client():
        try:
            from security import client_ip
        except ImportError:             # packaged as sensehive.*
            from .security import client_ip
        return client_ip(request)

    def allowed():
        header = request.headers.get('Authorization', '')
        if login_ok() and not header:
            return True
        if not header:
            return False
        now, ip = time.time(), client()
        with bad_lock:
            recent = [t for t in bad_tokens.get(ip, []) if now - t < 900]
            if len(recent) >= 20:                     # 20 wrong tokens in 15 minutes: refused for a while
                bad_tokens[ip] = recent
                return False
            if rx.token_ok(header):
                return True
            recent.append(now)
            bad_tokens[ip] = recent
            if len(bad_tokens) > 10000:               # bounded memory under a spray from many addresses
                bad_tokens.clear()
        return login_ok()

    def number(name, default):
        try:
            v = float(request.args.get(name, default))
        except (TypeError, ValueError):
            return default
        return v if math.isfinite(v) else default

    def names_param():
        known = rx.node_names()
        raw = request.args.get('nodes', '')
        if raw in ('', 'all'):
            return known
        wanted = [n for n in raw.split(',') if n]
        return [n for n in known if n in set(wanted)]

    @app.route('/api/heartbeat/status')
    def heartbeat_status():
        if not allowed():
            return jsonify({'error': 'Authentication required'}), 401
        return jsonify({'enabled': rx.enabled, 'connected': rx.connected, 'rejected': rx.rejected,
                        'flooded': rx.flooded, 'nodes': len(rx.tracker.nodes)})

    @app.route('/api/heartbeat/join', methods=['GET', 'POST'])
    def heartbeat_join():
        """A join token for one node (signed-in users only, never the read-only
        token): pasted into the agent's setup.py on the node. GET: is it possible."""
        if not login_ok():
            return jsonify({'error': 'Authentication required'}), 401
        host, port, tls = rx.broker()
        info = {'enabled': rx.enabled, 'fleet': rx.fleet(), 'broker': host, 'port': port, 'tls': tls,
                'agent': 'https://github.com/855princekumar/mqtt-heartbeat-service'}
        if request.method == 'GET':
            return jsonify(info)
        if not rx.enabled:
            return jsonify({'success': False, 'error': 'The heartbeat receiver is off: set HEARTBEAT_MASTER_KEY '
                                                       '(or HEARTBEAT_MASTER_KEY=auto) and restart SenseHive.'}), 409
        data = request.get_json(silent=True) or {}
        bad_name = ('A node name is 1 to 63 letters, digits, dots, dashes or underscores, starting with a '
                    'letter or digit.')
        if 'nodes' in data:                                   # many at once, for a CSV
            nodes = data['nodes']
            if not isinstance(nodes, list) or not 1 <= len(nodes) <= JOIN_BULK_MAX:
                return jsonify({'success': False, 'error': f'Give 1 to {JOIN_BULK_MAX} node names.'}), 400
            names = [n.strip() if isinstance(n, str) else '' for n in nodes]
            bad = [n for n in names if not NODE_NAME.match(n)]
            if bad:
                return jsonify({'success': False, 'error': f'{bad_name} Not valid: {", ".join(bad[:5])[:200]}'}), 400
            if len(set(names)) != len(names):
                return jsonify({'success': False, 'error': 'A node name is listed twice.'}), 400
            known = set(rx.node_names()) | {n['name'] for n in rx.binned()}
            return jsonify({'success': True, 'tokens': [{'node': n, 'token': rx.join(n), 'known': n in known}
                                                        for n in names], **info})
        node = data.get('node')
        if not isinstance(node, str) or not NODE_NAME.match(node.strip()):
            return jsonify({'success': False, 'error': bad_name}), 400
        node = node.strip()
        known = node in rx.node_names() or any(n['name'] == node for n in rx.binned())
        return jsonify({'success': True, 'node': node, 'token': rx.join(node), 'known': known, **info})

    @app.route('/api/heartbeat/bin', methods=['GET', 'POST'])
    def heartbeat_bin():
        """The recycle bin: signed-in users only (never the read-only token)."""
        if not login_ok():
            return jsonify({'error': 'Authentication required'}), 401
        if request.method == 'GET':
            return jsonify({'nodes': rx.binned(), 'days': rx.bin_days})
        data = request.get_json(silent=True) or {}
        names = data.get('names')
        if not isinstance(names, list) or not names or len(names) > 5000 or \
                not all(isinstance(n, str) and 0 < len(n) <= 200 for n in names):
            return jsonify({'success': False, 'error': 'names must be a list of node names'}), 400
        action = data.get('action')
        if action == 'bin':
            n = rx.bin(names)
        elif action == 'restore':
            n = rx.restore(names)
        elif action == 'delete':
            n = rx.delete_forever(names)
        else:
            return jsonify({'success': False, 'error': 'action must be bin, restore or delete'}), 400
        return jsonify({'success': True, 'changed': n})

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

    @app.route('/api/heartbeat/history')
    def heartbeat_history():
        """One node's heartbeats, breaks and uptime over 1m, 1h, 1d, 7d or 30d."""
        if not allowed():
            return jsonify({'error': 'Authentication required'}), 401
        name, rng = request.args.get('node', ''), request.args.get('range', '1h')
        if rng not in RANGES:
            return jsonify({'error': 'range must be one of ' + ', '.join(RANGES)}), 400
        if not rx.enabled or name not in rx.node_names():
            return jsonify({'error': 'Unknown node'}), 404
        return jsonify(rx.history(name, rng))

    @app.route('/api/heartbeat/export.csv')
    def heartbeat_export():
        """CSV of beats, minutes or events for nodes=a,b (or all) between since and until."""
        if not allowed():
            return jsonify({'error': 'Authentication required'}), 401
        what = request.args.get('what', 'beats')
        if what not in CSV_KINDS:
            return jsonify({'error': 'what must be one of ' + ', '.join(CSV_KINDS)}), 400
        now = rx.clock()
        until = min(number('until', now), now)
        since = max(number('since', now - 86400), now - rx.keep_days * 86400)
        names = names_param() if rx.enabled else []
        if not names:
            return jsonify({'error': 'No matching nodes'}), 404
        body = rx.export_csv(names, since, until, what)
        stamp = time.strftime('%Y%m%d-%H%M', time.gmtime(now))
        label = names[0] if len(names) == 1 else f'{len(names)}-nodes'
        safe = ''.join(ch if ch.isalnum() or ch in '-_.' else '_' for ch in label)[:60]
        return Response(body, mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename=heartbeats-{what}-{safe}-{stamp}.csv',
            'Cache-Control': 'no-store'})

    return rx
