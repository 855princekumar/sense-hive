"""Secure topics (ADR 0009): messages under the secure root are verified and
decrypted with a per-topic key and stored apart from open topics; keys are
pending for 24 hours, become active and bound to a topic on their first valid
message, expire or are revoked (their secret wiped, their id never reused);
nothing outside the root changes; the device examples speak the same protocol."""
import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from conftest import FakeMessage

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples' / 'secure-topics'


@pytest.fixture
def keys(client):
    def make(count=1, **extra):
        r = client.post('/api/secure/keys', json={'count': count, **extra})
        assert r.status_code == 200, r.get_json()
        return r.get_json()['keys']
    return make


def send(sh, topic, payload):
    sh.on_message(None, None, FakeMessage(topic, payload))


def topics(client, secure):
    return [n for n in client.get('/api/nodes').get_json() if bool(n['secure']) == secure]


# ---------------------------------------------------------------- protocol

def test_seal_and_open_round_trip_and_every_change_is_caught(sh):
    sec = sh.secure_module
    key, kid, topic = bytes(range(32)), '0123456789abcdef', 'sensehive/secure/a'
    env = sec.parse(sec.seal(key, kid, topic, b'{"t": 21}'), 65536)
    assert sec.open_sealed(key, topic, env) == b'{"t": 21}'
    for change in ({'ct': env['ct'][:-1] + bytes([env['ct'][-1] ^ 1])}, {'tag': bytes(16)}, {'t': env['t'] + 1},
                   {'nonce': bytes(16)}):
        with pytest.raises(sec.Invalid):
            sec.open_sealed(key, topic, dict(env, **change))
    with pytest.raises(sec.Invalid):
        sec.open_sealed(key, topic + '/other', env)                      # moved to another topic
    with pytest.raises(sec.Invalid):
        sec.open_sealed(bytes(32), topic, env)                           # another key


@pytest.mark.parametrize('payload', [
    b'', b'not json', b'[]', b'{"v": 2}', b'{"v":1,"k":"XYZ","t":1,"i":"","c":"","m":""}',
    b'{"v":1,"k":"0123456789abcdef","t":true,"i":"AAAAAAAAAAAAAAAAAAAAAA==","c":"","m":"AAAAAAAAAAAAAAAAAAAAAA=="}',
    b'{"v":1,"k":"0123456789abcdef","t":1,"i":"!!!","c":"","m":"AAAAAAAAAAAAAAAAAAAAAA=="}',
    b'{"v":1,"k":"0123456789abcdef","t":1,"i":"AAAA","c":"","m":"AAAAAAAAAAAAAAAAAAAAAA=="}',
    b'[' * 5000 + b']' * 5000,
])
def test_hostile_envelopes_are_refused_quietly(sh, payload):
    with pytest.raises(sh.secure_module.Invalid):
        sh.secure_module.parse(payload, 65536)


# ---------------------------------------------------------------- keys

def test_keys_are_generated_shown_once_and_never_listed_with_their_secret(client, keys):
    made = keys(3, label='pump')
    assert [k['label'] for k in made] == ['pump-1', 'pump-2', 'pump-3']
    assert all(len(k['key']) == 64 and len(k['kid']) == 16 for k in made)
    listed = client.get('/api/secure/keys').get_json()
    text = json.dumps(listed)
    assert all(k['key'] not in text for k in made) and 'secret' not in text
    assert {k['status'] for k in listed['keys']} == {'pending'}


@pytest.mark.parametrize('body', [{'count': 0}, {'count': 101}, {'count': 'x'}, {'count': True},
                                  {'count': 2, 'topic': 'sensehive/secure/a'}, {'count': 1, 'topic': 'elsewhere/a'},
                                  {'count': 1, 'topic': 'sensehive/secure/#'}, {'count': 1, 'topic': 'sensehive/secure'}])
def test_bad_key_requests_are_refused_with_a_fixed_text(client, body):
    r = client.post('/api/secure/keys', json=body)
    assert r.status_code == 400
    assert r.get_json()['error'] in __import__('secure').MESSAGES.values()      # a fixed text, never an exception's


def test_a_message_activates_and_binds_its_key_and_the_topic_appears(sh, client, keys):
    k = keys(label='pump-house')[0]
    topic = 'sensehive/secure/site-a/pump-1'
    send(sh, topic, sh.secure_module.seal(bytes.fromhex(k['key']), k['kid'], topic, '{"flow": 12.5}'))
    sec = topics(client, True)
    assert len(sec) == 1 and sec[0]['topic'] == topic and sec[0]['key_id'] == k['kid']
    assert sec[0]['node_name'] == 'pump-house' and sec[0]['tag'] == 'secure'
    assert sec[0]['last_value'] == {'flow': 12.5} and sec[0]['entry_count'] == 1
    row = next(x for x in client.get('/api/secure/keys').get_json()['keys'] if x['kid'] == k['kid'])
    assert row['status'] == 'active' and row['topic'] == topic and row['messages'] == 1
    other = 'sensehive/secure/site-a/pump-2'                       # the key is bound to its topic now
    send(sh, other, sh.secure_module.seal(bytes.fromhex(k['key']), k['kid'], other, '{"flow": 1}'))
    assert len(topics(client, True)) == 1 and sh.secure_topics.rejected['wrong_topic'] == 1
    hist = client.get(f"/api/nodes/{sec[0]['id']}/history").get_json()['history']
    assert hist[0]['payload'] == {'flow': 12.5}
    csv = client.get(f"/api/nodes/{sec[0]['id']}/export").get_data(as_text=True)
    assert 'flow' in csv


def test_replays_stale_messages_and_wrong_keys_are_dropped(sh, client, keys):
    k = keys()[0]
    key, topic = bytes.fromhex(k['key']), 'sensehive/secure/x'
    msg = sh.secure_module.seal(key, k['kid'], topic, '1')
    send(sh, topic, msg)
    send(sh, topic, msg)                                                  # the same message again
    send(sh, topic, sh.secure_module.seal(key, k['kid'], topic, '2', t=time.time() - 900))   # 15 minutes old
    send(sh, topic, sh.secure_module.seal(bytes(32), k['kid'], topic, '3'))                 # wrong key
    send(sh, topic, sh.secure_module.seal(key, 'ffffffffffffffff', topic, '4'))             # unknown id
    send(sh, topic, b'garbage')
    r = sh.secure_topics.rejected
    assert (r['replay'], r['stale'], r['signature'], r['unknown_key'], r['format']) == (1, 1, 1, 1, 1)
    assert topics(client, True)[0]['entry_count'] == 1


def test_unused_keys_expire_after_a_day_and_their_ids_are_never_reissued(sh, client, keys, monkeypatch):
    k = keys()[0]
    later = time.time() + 25 * 3600
    monkeypatch.setattr(sh.secure_topics, 'clock', lambda: later)
    assert sh.secure_topics.expire() == 1
    row = client.get('/api/secure/keys?status=expired').get_json()['keys'][0]
    assert row['kid'] == k['kid'] and row['status'] == 'expired'
    with sh.get_db() as conn:
        assert conn.execute('SELECT secret FROM secure_keys WHERE kid = ?', (k['kid'],)).fetchone()['secret'] is None
    topic = 'sensehive/secure/late'
    monkeypatch.setattr(sh.secure_topics, 'clock', time.time)
    send(sh, topic, sh.secure_module.seal(bytes.fromhex(k['key']), k['kid'], topic, '1'))
    assert not topics(client, True)                                      # an expired key opens nothing
    ids = iter([k['kid'], k['kid'], 'aaaaaaaaaaaaaaaa'])                 # a random id that was used before
    monkeypatch.setattr(sh.secure_module.secrets, 'token_hex', lambda n: next(ids))
    assert keys()[0]['kid'] == 'aaaaaaaaaaaaaaaa'


def test_revoke_and_reveal_need_the_right_things(sh, client, keys):
    k = keys()[0]
    bad = client.post(f"/api/secure/keys/{k['kid']}/reveal", json={'password': 'wrong'})
    assert bad.status_code == 401
    ok = client.post(f"/api/secure/keys/{k['kid']}/reveal", json={'password': 'admin123'})
    assert ok.status_code == 200 and ok.get_json()['key'] == k['key']
    assert client.post('/api/secure/keys/not-an-id/reveal', json={'password': 'admin123'}).status_code == 404
    assert client.post(f"/api/secure/keys/{k['kid']}/revoke").get_json()['success']
    assert client.post(f"/api/secure/keys/{k['kid']}/reveal", json={'password': 'admin123'}).status_code == 400
    topic = 'sensehive/secure/r'
    send(sh, topic, sh.secure_module.seal(bytes.fromhex(k['key']), k['kid'], topic, '1'))
    assert not topics(client, True) and sh.secure_topics.rejected['inactive_key'] == 1
    for _ in range(25):                                                  # guessing the password is locked out
        client.post(f"/api/secure/keys/{keys()[0]['kid']}/reveal", json={'password': 'nope'})
    assert client.post(f"/api/secure/keys/{k['kid']}/reveal", json={'password': 'admin123'}).status_code == 429


def test_the_api_needs_a_sign_in(sh):
    c = sh.app.test_client()
    for method, path in (('get', '/api/secure/status'), ('get', '/api/secure/keys'), ('post', '/api/secure/keys'),
                         ('post', '/api/secure/keys/0123456789abcdef/reveal'),
                         ('post', '/api/secure/keys/0123456789abcdef/revoke')):
        assert getattr(c, method)(path, json={}).status_code == 401, path


# ---------------------------------------------------------------- isolation

def test_secure_and_open_topics_never_mix(sh, client, keys, add_topic):
    everything = add_topic('#')                                          # an open topic that matches everything
    k = keys()[0]
    topic = 'sensehive/secure/iso'
    send(sh, topic, sh.secure_module.seal(bytes.fromhex(k['key']), k['kid'], topic, '{"secret": 1}'))
    send(sh, 'plain/temp', '{"t": 20}')
    opened = next(n for n in client.get('/api/nodes').get_json() if n['id'] == everything['id'])
    assert opened['entry_count'] == 1 and opened['last_value'] == {'t': 20}   # the secure message is not in '#'
    assert [n['topic'] for n in topics(client, True)] == [topic]
    r = client.post('/api/nodes', json={'topic': 'sensehive/secure/manual', 'tag': 't', 'node_name': 'n'})
    assert r.status_code == 400 and 'secure topic root' in r.get_json()['error']
    sh.mqtt_client.subscribed.clear()
    sh.sync_subscriptions(reset=True)
    assert 'sensehive/secure/#' in sh.mqtt_client.subscribed and topic not in sh.mqtt_client.subscribed
    stats = client.get('/api/stats').get_json()
    assert stats['secure_topic_count'] == 1 and stats['topic_count'] == 2


def test_a_secure_device_names_its_status_topic_and_shows_on_and_off(sh, client, keys):
    k = keys(label='power-node')[0]
    topic = 'sensehive/secure/espnode-1/powerbeacon'
    body = {'status': 'ON', 'sensehive_lwt': 'espnode-1/status'}
    send(sh, topic, sh.secure_module.seal(bytes.fromhex(k['key']), k['kid'], topic, json.dumps(body)))
    node = topics(client, True)[0]
    assert node['lwt_topic'] == 'espnode-1/status' and node['status'] == 'unknown'
    assert 'espnode-1/status' in sh.mqtt_client.subscribed and topic not in sh.mqtt_client.subscribed
    send(sh, 'espnode-1/status', '{"node_id":"espnode-1","status":"ON"}')
    assert topics(client, True)[0]['status'] == 'active'
    send(sh, 'espnode-1/status', '{"node_id":"espnode-1","status":"OFF","reason":"lwt"}')
    assert topics(client, True)[0]['status'] == 'inactive'
    assert topics(client, True)[0]['entry_count'] == 1              # status messages are not secure data
    body['sensehive_lwt'] = 'elsewhere/status'                       # set once, never moved by a message
    send(sh, topic, sh.secure_module.seal(bytes.fromhex(k['key']), k['kid'], topic, json.dumps(body)))
    assert topics(client, True)[0]['lwt_topic'] == 'espnode-1/status'


@pytest.mark.parametrize('lwt', ['a/#', 'a/+/b', 'sensehive/secure/x', '', '   ', 5, None, ['a']])
def test_a_bad_status_topic_is_ignored(sh, client, keys, lwt):
    k = keys()[0]
    topic = 'sensehive/secure/bad-lwt'
    send(sh, topic, sh.secure_module.seal(bytes.fromhex(k['key']), k['kid'], topic, json.dumps({'sensehive_lwt': lwt})))
    assert topics(client, True)[0]['lwt_topic'] == ''


def test_a_custom_root_and_turning_it_off(make_app):
    sh = make_app(SENSEHIVE_SECURE_ROOT='plant/enc/')
    assert sh.secure_topics.root == 'plant/enc' and sh.secure_topics.subscription() == 'plant/enc/#'
    sh = make_app(SENSEHIVE_SECURE_ROOT='bad/#')
    assert sh.secure_topics.root == 'sensehive/secure'
    off = make_app(SENSEHIVE_SECURE_TOPICS='false')
    off.sync_subscriptions(reset=True)
    assert 'sensehive/secure/#' not in off.mqtt_client.subscribed


# ---------------------------------------------------------------- the device examples

def load(path, name, extra=None):
    for mod, obj in (extra or {}).items():
        sys.modules[mod] = obj
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_python_example_is_accepted(sh, client, keys):
    ex = load(EXAMPLES / 'python' / 'secure_publish.py', 'sh_example_python')
    k = keys()[0]
    topic = 'sensehive/secure/py'
    send(sh, topic, ex.seal(bytes.fromhex(k['key']), k['kid'], topic, b'{"from": "python"}'))
    assert topics(client, True)[0]['last_value'] == {'from': 'python'}


def test_the_micropython_example_is_accepted(sh, client, keys):
    """Run the MicroPython code on CPython with a stand-in for its cryptolib (AES-CTR)."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    class aes:
        def __init__(self, key, mode, counter):
            assert mode == 6
            self.c = Cipher(algorithms.AES(key), modes.CTR(counter)).encryptor()

        def encrypt(self, data):
            return self.c.update(data)
    ex = load(EXAMPLES / 'micropython' / 'sensehive_secure.py', 'sh_example_micropython',
              {'cryptolib': types.SimpleNamespace(aes=aes)})
    k = keys()[0]
    topic = 'sensehive/secure/mpy'
    send(sh, topic, ex.seal(bytes.fromhex(k['key']), k['kid'], topic, b'{"from": "micropython"}'))
    assert topics(client, True)[0]['last_value'] == {'from': 'micropython'}


@pytest.mark.skipif(not shutil.which('node') and not os.getenv('CI'), reason='Node.js is not installed')
def test_the_node_example_is_accepted(sh, client, keys):
    k = keys()[0]
    topic = 'sensehive/secure/node'
    out = subprocess.run(['node', str(EXAMPLES / 'node' / 'sensehive-secure.js'), k['key'], k['kid'], topic,
                          '{"from": "node"}'], capture_output=True, check=True, timeout=30).stdout
    assert json.loads(out)['k'] == k['kid'] and base64.b64decode(json.loads(out)['m'])
    send(sh, topic, out)
    assert topics(client, True)[0]['last_value'] == {'from': 'node'}
