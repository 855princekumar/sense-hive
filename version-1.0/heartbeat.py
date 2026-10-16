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
    HEARTBEAT_BEATS_HOURS   every verified heartbeat kept for (48; 0 keeps none)
    HEARTBEAT_MIN_SPACING   seconds a node must leave between heartbeats (2);
                            faster ones are dropped, so a stolen node key cannot
                            flood the history
"""
import csv
import hmac
import io
import math
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
        self.beats_hours = min(max(_int('HEARTBEAT_BEATS_HOURS', 48), 0), 24 * 31)
        self.min_spacing = max(_int('HEARTBEAT_MIN_SPACING', 2), 0)
        self.rejected = 0
        self.flooded = 0
        self.last_rx = {}

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

    def _save(self, name, status_changed, body=None):
        st = self.tracker.nodes[name]
        now = self.clock()
        status = self.tracker.status(name, now=now, stale_after=self.stale)
        with self.db() as conn:
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
            conn.execute('DELETE FROM hb_beats WHERE t < ?', (self.clock() - self.beats_hours * 3600,))
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

    def node_names(self):
        with self.db() as conn:
            return [r['name'] for r in conn.execute('SELECT name FROM hb_nodes ORDER BY name')]

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
            gaps = [b[0] - a[0] for a, b in zip(beats, beats[1:]) if b[1] != KINDS['lwt']]
            typical = sorted(gaps)[len(gaps) // 2] if gaps else None
            limit = max(2.5 * typical, typical + 5) if typical else None
            breaks = []
            for a, b in zip(beats, beats[1:]):
                if limit and b[0] - a[0] > limit:
                    breaks.append({'from': a[0], 'to': b[0], 'seconds': round(b[0] - a[0], 1)})
            if beats and limit and now - beats[-1][0] > limit:
                breaks.append({'from': beats[-1][0], 'to': None, 'seconds': round(now - beats[-1][0], 1)})
            lags = [b[2] for b in beats if b[2] is not None]
            out.update(kind='beats', points=[[round(t, 3), k, lag] for t, k, lag in beats],
                       interval=round(typical, 1) if typical else None, breaks=breaks,
                       received=sum(1 for b in beats if b[1] != KINDS['lwt']),
                       lag_ms=round(1000 * sorted(lags)[len(lags) // 2]) if lags else None,
                       longest_break=max((b['seconds'] for b in breaks), default=0))
        else:
            minutes = set(self.minutes(since, now).get(name, []))
            first = int(since // 3600) * 3600
            buckets = []
            for h in range(first, int(now) + 1, 3600):
                total = len([m for m in range(h, h + 3600, 60) if since <= m <= now])
                up = len([m for m in range(h, h + 3600, 60) if m in minutes])
                buckets.append([h, up, total])
            out.update(kind='hours', points=buckets)
        mins = self.minutes(since, now).get(name, [])
        total = max(int(span // 60), 1)
        out['uptime'] = round(100.0 * min(len(mins), total) / total, 2)
        return out

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


def register(app, get_db, login_ok, client_factory):
    """Add the read-only API to the Flask app and return the receiver."""
    from flask import jsonify, request

    from flask import Response

    rx = Receiver(get_db)
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
