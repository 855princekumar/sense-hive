"""Heartbeat protocol v1: authenticated, encrypted heartbeats over a public MQTT
broker. The same file is used by the node agent, by SenseHive (the receiver)
and by EdgeShell (which provisions nodes); test vectors keep the copies equal.

Keys
    master       32 random bytes, held only by EdgeShell and SenseHive.
    kid          8 bytes = HMAC(master, "kid|" + node name). Names a node without
                 revealing it.
    node key     HMAC(master, "node|" + kid). Each node holds only its own, so a
                 node can never speak for another one.
    topic key    HMAC(master, "topic"). Lets nodes and the receiver compute the
                 current topic; it grants nothing else.

Topic        Changes every WINDOW seconds: two random-looking levels derived from
             the topic key and the window number, so nothing on the broker says
             what it is or which fleet it belongs to.

Message      version (1 byte) | kid (8) | nonce (12) | AES-256-GCM ciphertext.
             The version, kid and topic are authenticated data, so a message
             cannot be moved to another topic or node. The plaintext is
             {"n": node name, "k": kind, "t": unix time, "s": session, "q": seq,
             "v": agent version}; nothing else is ever sent (no addresses, no
             credentials, no metrics).

Kinds        "birth" when the agent connects, "hb" every interval, "lwt" (the
             broker publishes it if the agent disappears). A session is the
             connect time, so an old LWT can never mark a live node offline.
"""
import hashlib
import hmac
import json
import os
import time

VERSION = 1
WINDOW = 600                     # seconds per topic
MAX_SKEW = 120                   # seconds a heartbeat may be off from the receiver's clock
KINDS = ('birth', 'hb', 'lwt')
_HEADER = 1 + 8 + 12


class Invalid(Exception):
    """A message that is not authentic, not fresh or not well formed."""


def _mac(key, data):
    return hmac.new(key, data, hashlib.sha256).digest()


def kid_for(master, node):
    return _mac(master, b'kid|' + node.encode('utf-8'))[:8]


def node_key(master, kid):
    return _mac(master, b'node|' + kid)


def topic_key(master):
    return _mac(master, b'topic')


def window(now=None):
    return int((time.time() if now is None else now) // WINDOW)


def topic(tkey, win):
    h = _mac(tkey, b'win|%d' % win).hex()
    return f'{h[:6]}/{h[6:30]}'


def provision(master, node):
    """The settings one node needs (never the master key)."""
    kid = kid_for(master, node)
    return {'HB_NODE': node, 'HB_KID': kid.hex(), 'HB_NODE_KEY': node_key(master, kid).hex(),
            'HB_TOPIC_KEY': topic_key(master).hex()}


def _aesgcm(key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key)


def seal(nkey, kid, tpc, body):
    """Encrypt and authenticate `body` (a dict) for topic `tpc`."""
    nonce = os.urandom(12)
    header = bytes([VERSION]) + kid
    data = json.dumps(body, separators=(',', ':'), sort_keys=True).encode()
    return header + nonce + _aesgcm(nkey).encrypt(nonce, data, header + tpc.encode())


def open_message(master, tpc, raw):
    """Verify and decrypt a message from topic `tpc`. Returns the body dict;
    raises Invalid for anything not authentic or well formed. Freshness and
    ordering are checked by the receiver (Tracker)."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < _HEADER + 16 or len(raw) > 1024:
        raise Invalid('size')
    if raw[0] != VERSION:
        raise Invalid('version')
    kid, nonce = bytes(raw[1:9]), bytes(raw[9:21])
    try:
        data = _aesgcm(node_key(master, kid)).decrypt(nonce, bytes(raw[21:]), bytes(raw[:9]) + tpc.encode())
        body = json.loads(data)
    except Exception:
        raise Invalid('authentication') from None
    if not isinstance(body, dict) or body.get('k') not in KINDS or not isinstance(body.get('n'), str) \
            or not isinstance(body.get('t'), (int, float)) or not isinstance(body.get('s'), (int, float)):
        raise Invalid('fields')
    if not hmac.compare_digest(kid_for(master, body['n']), kid):
        raise Invalid('name')                   # the name inside must be the one the key belongs to
    return body


class Tracker:
    """Receiver-side state per node: rejects stale, replayed and out-of-order
    messages, and turns the accepted ones into online/offline state."""

    def __init__(self):
        self.nodes = {}

    def accept(self, body, now=None):
        """True when `body` is new and fresh; updates the node's state."""
        now = time.time() if now is None else now
        st = self.nodes.setdefault(body['n'], {'session': 0, 'last_t': 0, 'online': None,
                                               'last_seen': None, 'since': None, 'version': None})
        kind, t, session = body['k'], float(body['t']), float(body['s'])
        if kind == 'lwt':
            # Published by the broker later, so its time is the connect time:
            # it counts only for the session that is current.
            if session != st['session'] or st['online'] is False:
                return False
            st.update(online=False, since=now)
            return True
        if abs(now - t) > MAX_SKEW or session < st['session'] or t <= st['last_t']:
            return False
        if st['online'] is not True:
            st['since'] = now
        st.update(session=session, last_t=t, online=True, last_seen=now, version=body.get('v'))
        return True

    def status(self, name, now=None, stale_after=35):
        """'online', 'offline' (LWT received), 'silent' (no heartbeat for
        `stale_after` seconds, e.g. the broker or the internet is down) or None."""
        st = self.nodes.get(name)
        if not st:
            return None
        now = time.time() if now is None else now
        if st['online'] is False:
            return 'offline'
        if st['last_seen'] is None or now - st['last_seen'] > stale_after:
            return 'silent'
        return 'online'
