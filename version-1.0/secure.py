"""Secure topics (ADR 0009): MQTT messages encrypted and signed per topic with a
key SenseHive issues, found by themselves under one topic root.

Protocol "sst1" (docs/SECURE-TOPICS.md). A device holds a key id (16 hex) and a
key (32 bytes, 64 hex). It publishes to any topic under the root (default
sensehive/secure/...) a JSON envelope:

  {"v": 1, "k": "<key id>", "t": <unix seconds>, "i": "<nonce, base64>",
   "c": "<ciphertext, base64>", "m": "<tag, base64>"}

  enc_key = HMAC-SHA256(key, "sst1 enc")      mac_key = HMAC-SHA256(key, "sst1 mac")
  c = AES-256-CTR(enc_key, nonce = 16 random bytes, the payload)
  m = first 16 bytes of HMAC-SHA256(mac_key, "sst1" 0 topic 0 key id 0 t 0 nonce c)

The tag covers the topic, the key id and the time, so a message cannot be moved
to another topic, changed, or replayed later (the time must be within 5
minutes and a nonce is accepted once). Only AES-CTR, HMAC and SHA-256 are
needed, so MicroPython, ESP32 (mbedTLS) and Node-RED can all publish.

Keys: a new key is pending for 24 hours. Its first valid message makes it
active and binds it to that topic. A pending key that receives nothing
expires; expired and revoked keys lose their secret and their id is never
issued again. Secrets are stored encrypted with the app's secret key and
shown once, when created; showing one again needs the password.
"""
import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

VERSION = 1
SKEW = 300                     # seconds a message's time may differ from ours
REPLAY_WINDOW = 2 * SKEW + 60  # nonces are remembered at least as long as a message can be fresh
PENDING_HOURS = 24
MAX_PER_REQUEST = 100
MAX_LABEL = 64
KID_RE = re.compile(r'^[0-9a-f]{16}$')
STATUSES = ('pending', 'active', 'expired', 'revoked')
REASONS = ('format', 'unknown_key', 'inactive_key', 'wrong_topic', 'stale', 'replay', 'signature')

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS secure_keys (
        kid TEXT PRIMARY KEY, label TEXT NOT NULL DEFAULT '', topic TEXT NOT NULL DEFAULT '',
        secret TEXT, status TEXT NOT NULL, created_at REAL NOT NULL, created_by TEXT,
        expires_at REAL, activated_at REAL, last_used_at REAL, messages INTEGER NOT NULL DEFAULT 0,
        ended_at REAL)''',
    'CREATE INDEX IF NOT EXISTS secure_keys_status ON secure_keys (status)',
)


class Invalid(Exception):
    """A message that is not a valid sst1 envelope for us. `reason` is one of REASONS."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class SecureError(ValueError):
    """A request that cannot be carried out; `code` maps to a fixed text (MESSAGES)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


MESSAGES = {
    'count': f'Generate between 1 and {MAX_PER_REQUEST} keys at a time.',
    'topic_root': 'A key\'s topic must be under the secure topic root.',
    'topic_one': 'A topic can be set only when generating one key.',
    'topic_bad': 'That topic is not valid (no wildcards, quotes or control characters).',
    'topic_taken': 'That topic already has a key.',
    'not_found': 'No such key.',
    'no_secret': 'This key has no secret any more (expired or revoked).',
    'disabled': 'Secure topics are turned off on this server.',
}


def message_for(exc):
    return MESSAGES.get(getattr(exc, 'code', None), 'That request is not valid.')


# ---------------------------------------------------------------- protocol

def derive(key):
    return (hmac.new(key, b'sst1 enc', hashlib.sha256).digest(),
            hmac.new(key, b'sst1 mac', hashlib.sha256).digest())


def _mac_input(topic, kid, t, nonce, ct):
    return b'\x00'.join((b'sst1', topic.encode(), kid.encode(), str(int(t)).encode(), nonce)) + ct


def _ctr(enc_key, nonce, data):
    c = Cipher(algorithms.AES(enc_key), modes.CTR(nonce)).encryptor()
    return c.update(data) + c.finalize()


def seal(key, kid, topic, payload, t=None, nonce=None):
    """The JSON envelope (bytes) for `payload` (bytes or str) on `topic`. Used by
    tests and the Python example; devices implement the same steps."""
    if isinstance(payload, str):
        payload = payload.encode()
    enc_key, mac_key = derive(key)
    nonce = nonce or os.urandom(16)
    t = int(time.time() if t is None else t)
    ct = _ctr(enc_key, nonce, payload)
    tag = hmac.new(mac_key, _mac_input(topic, kid, t, nonce, ct), hashlib.sha256).digest()[:16]
    b64 = lambda b: base64.b64encode(b).decode()      # noqa: E731
    return json.dumps({'v': VERSION, 'k': kid, 't': t, 'i': b64(nonce), 'c': b64(ct), 'm': b64(tag)},
                      separators=(',', ':')).encode()


def parse(payload, max_bytes):
    """A checked envelope dict, or raises Invalid('format')."""
    try:
        if len(payload) > max_bytes:
            raise ValueError
        env = json.loads(payload)
        if not isinstance(env, dict) or env.get('v') != VERSION or not isinstance(env.get('k'), str) \
                or not KID_RE.match(env['k']) or not isinstance(env.get('t'), int) or isinstance(env.get('t'), bool):
            raise ValueError
        nonce = base64.b64decode(env['i'], validate=True)
        ct = base64.b64decode(env['c'], validate=True)
        tag = base64.b64decode(env['m'], validate=True)
        if len(nonce) != 16 or len(tag) != 16:
            raise ValueError
    except (ValueError, TypeError, KeyError, RecursionError, binascii.Error):
        raise Invalid('format') from None
    return {'k': env['k'], 't': env['t'], 'nonce': nonce, 'ct': ct, 'tag': tag}


def open_sealed(key, topic, env):
    """The payload bytes, or raises Invalid('signature')."""
    enc_key, mac_key = derive(key)
    want = hmac.new(mac_key, _mac_input(topic, env['k'], env['t'], env['nonce'], env['ct']), hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(want, env['tag']):
        raise Invalid('signature')
    return _ctr(enc_key, env['nonce'], env['ct'])


# ---------------------------------------------------------------- the service

def _clean_label(label):
    return re.sub(r'[<>\x00-\x1f\x7f]', '', str(label or '')).strip()[:MAX_LABEL]


class SecureTopics:
    def __init__(self, db, secret_key, clock=time.time):
        """`db` opens a sqlite3 connection (the app's get_db); `secret_key()` returns the app's secret."""
        self.db, self.secret_key, self.clock = db, secret_key, clock
        self.enabled = os.getenv('SENSEHIVE_SECURE_TOPICS', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
        root = (os.getenv('SENSEHIVE_SECURE_ROOT') or 'sensehive/secure').strip().strip('/')
        if not root or any(ch in root for ch in '#+"') or any(ord(ch) < 32 for ch in root):
            root = 'sensehive/secure'
        self.root = root
        self.lock = threading.Lock()
        self.seen = {}                                   # kid -> {nonce: time}
        self.accepted = 0
        self.rejected = dict.fromkeys(REASONS, 0)

    # -- storage
    def init_db(self):
        with self.db() as conn:
            for stmt in SCHEMA:
                conn.execute(stmt)
            conn.commit()

    def _fernet(self):
        digest = hashlib.sha256(b'sensehive secure keys\x00' + str(self.secret_key()).encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    def under_root(self, topic):
        return topic == self.root or topic.startswith(self.root + '/')

    def subscription(self):
        return self.root + '/#'

    def expire(self, now=None):
        """Pending keys past their 24 hours become expired and lose their secret."""
        now = self.clock() if now is None else now
        with self.db() as conn:
            n = conn.execute("UPDATE secure_keys SET status = 'expired', secret = NULL, ended_at = ? "
                             "WHERE status = 'pending' AND expires_at < ?", (now, now)).rowcount
            conn.commit()
        return n

    def generate(self, count, label='', topic='', user=None):
        """New keys: [{kid, key, label, topic, expires_at}]. The key is in the answer only."""
        if not self.enabled:
            raise SecureError('disabled')
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= MAX_PER_REQUEST:
            raise SecureError('count')
        topic = (topic or '').strip()
        if topic:
            if count != 1:
                raise SecureError('topic_one')
            if any(ch in topic for ch in '#+"') or any(ord(ch) < 32 or ord(ch) == 127 for ch in topic) or len(topic) > 512:
                raise SecureError('topic_bad')
            if not self.under_root(topic) or topic == self.root:
                raise SecureError('topic_root')
        label = _clean_label(label)
        now = self.clock()
        f = self._fernet()
        out = []
        with self.db() as conn:
            if topic and conn.execute("SELECT 1 FROM secure_keys WHERE topic = ? AND status IN ('pending', 'active')",
                                      (topic,)).fetchone():
                raise SecureError('topic_taken')
            for i in range(count):
                while True:                              # an id is never issued twice, also after expiry
                    kid = secrets.token_hex(8)
                    if not conn.execute('SELECT 1 FROM secure_keys WHERE kid = ?', (kid,)).fetchone():
                        break
                key = secrets.token_bytes(32)
                name = label if count == 1 or not label else f'{label}-{i + 1}'
                conn.execute('INSERT INTO secure_keys (kid, label, topic, secret, status, created_at, created_by, expires_at) '
                             "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
                             (kid, name, topic, f.encrypt(key).decode(), now, user, now + PENDING_HOURS * 3600))
                out.append({'kid': kid, 'key': key.hex(), 'label': name, 'topic': topic,
                            'expires_at': now + PENDING_HOURS * 3600})
            conn.commit()
        return out

    def keys(self, status=None):
        self.expire()
        q, args = 'SELECT kid, label, topic, status, created_at, created_by, expires_at, activated_at, ' \
                  'last_used_at, messages, ended_at FROM secure_keys', ()
        if status in STATUSES:
            q, args = q + ' WHERE status = ?', (status,)
        with self.db() as conn:
            return [dict(r) for r in conn.execute(q + ' ORDER BY created_at DESC LIMIT 5000', args)]

    def counts(self):
        with self.db() as conn:
            rows = conn.execute('SELECT status, COUNT(*) AS n FROM secure_keys GROUP BY status').fetchall()
        return {s: next((r['n'] for r in rows if r['status'] == s), 0) for s in STATUSES}

    def reveal(self, kid):
        with self.db() as conn:
            row = conn.execute('SELECT secret, status FROM secure_keys WHERE kid = ?', (kid,)).fetchone()
        if row is None:
            raise SecureError('not_found')
        if not row['secret'] or row['status'] not in ('pending', 'active'):
            raise SecureError('no_secret')
        return self._fernet().decrypt(row['secret'].encode()).hex()

    def revoke(self, kid):
        with self.db() as conn:
            n = conn.execute("UPDATE secure_keys SET status = 'revoked', secret = NULL, ended_at = ? "
                             "WHERE kid = ? AND status IN ('pending', 'active')", (self.clock(), kid)).rowcount
            conn.commit()
        if not n:
            raise SecureError('not_found')

    # -- messages
    def _reject(self, reason):
        self.rejected[reason] = self.rejected.get(reason, 0) + 1
        return None

    def handle(self, topic, payload, max_bytes):
        """One MQTT message under the root: (key row, payload bytes) when valid, else None.
        Invalid messages are dropped silently and counted: strangers get no feedback."""
        try:
            env = parse(payload, max_bytes)
        except Invalid as e:
            return self._reject(e.reason)
        now = self.clock()
        with self.db() as conn:
            row = conn.execute('SELECT * FROM secure_keys WHERE kid = ?', (env['k'],)).fetchone()
        if row is None:
            return self._reject('unknown_key')
        if row['status'] not in ('pending', 'active') or not row['secret'] or \
                (row['status'] == 'pending' and row['expires_at'] < now):
            return self._reject('inactive_key')
        if row['topic'] and row['topic'] != topic:
            return self._reject('wrong_topic')
        if abs(now - env['t']) > SKEW:
            return self._reject('stale')
        try:
            key = self._fernet().decrypt(row['secret'].encode())
        except InvalidToken:                             # the app's secret key changed
            return self._reject('inactive_key')
        try:
            data = open_sealed(key, topic, env)
        except Invalid as e:
            return self._reject(e.reason)
        with self.lock:
            seen = self.seen.setdefault(env['k'], {})
            for n, t in list(seen.items()):
                if now - t > REPLAY_WINDOW:
                    del seen[n]
            if env['nonce'] in seen or len(seen) > 20000:
                return self._reject('replay')
            seen[env['nonce']] = now
        with self.db() as conn:
            if row['status'] == 'pending':
                taken = conn.execute("SELECT 1 FROM secure_keys WHERE topic = ? AND kid != ? AND status IN ('pending', 'active')",
                                     (topic, env['k'])).fetchone()
                if taken:
                    return self._reject('wrong_topic')
                conn.execute("UPDATE secure_keys SET status = 'active', topic = ?, activated_at = ? WHERE kid = ?",
                             (topic, now, env['k']))
            conn.execute('UPDATE secure_keys SET last_used_at = ?, messages = messages + 1 WHERE kid = ?', (now, env['k']))
            conn.commit()
            row = conn.execute('SELECT * FROM secure_keys WHERE kid = ?', (env['k'],)).fetchone()
        self.accepted += 1
        return dict(row), data

    def status(self):
        return {'enabled': self.enabled, 'root': self.root, 'subscription': self.subscription(),
                'keys': self.counts(), 'accepted': self.accepted, 'rejected': dict(self.rejected),
                'pending_hours': PENDING_HOURS, 'skew_seconds': SKEW}


# ---------------------------------------------------------------- routes

def register(app, service, login_ok, check_password, limiter, client_ip, on_change):
    """Key management API (signed-in users). `check_password(password)` checks the
    signed-in user's password; `on_change()` refreshes the MQTT subscriptions."""
    from flask import jsonify, request, session

    def guard():
        if not login_ok():
            return jsonify({'error': 'Authentication required'}), 401
        return None

    def fail(e, code=400):
        return jsonify({'success': False, 'error': message_for(e)}), code

    @app.route('/api/secure/status')
    def secure_status():
        return guard() or jsonify(service.status())

    @app.route('/api/secure/keys', methods=['GET', 'POST'])
    def secure_keys():
        g = guard()
        if g:
            return g
        if request.method == 'GET':
            return jsonify({'keys': service.keys(request.args.get('status') or None), 'root': service.root})
        data = request.get_json(silent=True) or {}
        try:
            made = service.generate(data.get('count', 1), data.get('label', ''), data.get('topic', ''),
                                    session.get('username'))
        except SecureError as e:
            return fail(e)
        on_change()
        return jsonify({'success': True, 'root': service.root, 'keys': made})

    @app.route('/api/secure/keys/<kid>/reveal', methods=['POST'])
    def secure_reveal(kid):
        g = guard()
        if g:
            return g
        user, ip = session.get('username', ''), client_ip()
        if limiter.blocked(user, ip):
            return jsonify({'success': False, 'error': 'Too many failed attempts. Try again later.'}), 429
        password = (request.get_json(silent=True) or {}).get('password')
        if not isinstance(password, str) or not password or not check_password(password):
            limiter.failed(user, ip)
            return jsonify({'success': False, 'error': 'Password incorrect'}), 401
        if not KID_RE.match(kid or ''):
            return fail(SecureError('not_found'), 404)
        try:
            key = service.reveal(kid)
        except SecureError as e:
            return fail(e, 404 if e.code == 'not_found' else 400)
        app.logger.info('Secure key %s revealed by %s', kid, user)
        return jsonify({'success': True, 'kid': kid, 'key': key})

    @app.route('/api/secure/keys/<kid>/revoke', methods=['POST'])
    def secure_revoke(kid):
        g = guard()
        if g:
            return g
        if not KID_RE.match(kid or ''):
            return fail(SecureError('not_found'), 404)
        try:
            service.revoke(kid)
        except SecureError as e:
            return fail(e, 404)
        app.logger.info('Secure key %s revoked by %s', kid, session.get('username'))
        return jsonify({'success': True})
