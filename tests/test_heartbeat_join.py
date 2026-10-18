"""Adding a heartbeat node without EdgeShell: a join token from SenseHive, pasted
into the agent's setup.py on the node. And isolation: every SenseHive has its
own fleet, so nodes of one never appear in another."""
import base64
import hashlib
import importlib.util
import json
import os
import stat
import time
from pathlib import Path

import pytest

import heartbeat_protocol as hp

AGENT_DIR = os.getenv('AGENT_DIR')          # a clone of mqtt-heartbeat-service: checks its setup.py too


def decode(token):
    """The token format, written down independently of SenseHive's encoder."""
    assert token.startswith('hbj1.')
    raw = token[5:]
    body = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
    check = body.pop('c')
    assert check == hashlib.sha256(json.dumps(body, separators=(',', ':'), sort_keys=True).encode()).hexdigest()[:8]
    return body


def login(sh):
    c = sh.app.test_client()
    assert c.post('/api/login', json={'username': 'admin', 'password': 'admin123'}).status_code == 200
    return c


def heartbeat(master, node, kind='hb', t=None):
    """What an agent installed from `master`'s join token sends."""
    t = time.time() if t is None else t
    kid = hp.kid_for(master, node)
    tpc = hp.topic(hp.topic_key(master), hp.window(t))
    return tpc, hp.seal(hp.node_key(master, kid), kid, tpc, {'n': node, 'k': kind, 't': t, 's': t - 30, 'q': 1, 'v': '1.1.0'})


def heartbeat_from_token(token, kind='hb', t=None):
    """The same, built only from what the token carries (as the node has it)."""
    b = decode(token)
    t = time.time() if t is None else t
    tpc = hp.topic(bytes.fromhex(b['tk']), hp.window(t))
    return tpc, hp.seal(bytes.fromhex(b['nk']), bytes.fromhex(b['kid']), tpc,
                        {'n': b['node'], 'k': kind, 't': t, 's': t - 30, 'q': 1, 'v': '1.1.0'})


def test_a_join_token_holds_one_nodes_keys_and_the_broker_never_the_master_key(make_app):
    master = os.urandom(32)
    sh = make_app(HEARTBEAT_MASTER_KEY=master.hex(), HEARTBEAT_BROKER='mqtt.example.com', HEARTBEAT_PORT='8883')
    c = login(sh)
    r = c.post('/api/heartbeat/join', json={'node': 'pi-node-01'})
    assert r.status_code == 200
    data = r.get_json()
    body = decode(data['token'])
    want = hp.provision(master, 'pi-node-01')
    assert body == {'v': 1, 'node': 'pi-node-01', 'kid': want['HB_KID'], 'nk': want['HB_NODE_KEY'],
                    'tk': want['HB_TOPIC_KEY'], 'broker': 'mqtt.example.com', 'port': 8883, 'tls': True}
    assert master.hex() not in data['token'] and master.hex() not in json.dumps(body)
    assert data['fleet'] == sh.heartbeat_module.fleet_id(hp.topic_key(master)) and len(data['fleet']) == 12
    assert data['known'] is False
    # a node set up from the token is accepted by this SenseHive
    rx = sh.heartbeat_receiver
    assert rx.handle(*heartbeat_from_token(data['token'], kind='birth'))
    assert [n['name'] for n in rx.nodes()] == ['pi-node-01']
    assert c.post('/api/heartbeat/join', json={'node': 'pi-node-01'}).get_json()['known'] is True


def test_nodes_can_reach_the_broker_by_another_name(make_app):
    sh = make_app(HEARTBEAT_MASTER_KEY=os.urandom(32).hex(), HEARTBEAT_BROKER='mosquitto', HEARTBEAT_PORT='1883',
                  HEARTBEAT_TLS='false', HEARTBEAT_NODE_BROKER='mqtt.example.com:18883')
    b = decode(login(sh).post('/api/heartbeat/join', json={'node': 'pi'}).get_json()['token'])
    assert (b['broker'], b['port'], b['tls']) == ('mqtt.example.com', 18883, False)
    for bad in ('a b', 'x:0', 'x:99999', 'x:y', ';rm'):
        sh = make_app(HEARTBEAT_MASTER_KEY=os.urandom(32).hex(), HEARTBEAT_BROKER='mosquitto', HEARTBEAT_NODE_BROKER=bad)
        assert decode(login(sh).post('/api/heartbeat/join', json={'node': 'pi'}).get_json()['token'])['broker'] == 'mosquitto'


def test_bulk_tokens_one_per_node_for_a_csv(make_app):
    master = os.urandom(32)
    c = login(make_app(HEARTBEAT_MASTER_KEY=master.hex()))
    names = [f'pi-{i:03d}' for i in range(1, 101)]
    r = c.post('/api/heartbeat/join', json={'nodes': names})
    assert r.status_code == 200
    tokens = r.get_json()['tokens']
    assert [t['node'] for t in tokens] == names and len({t['token'] for t in tokens}) == 100
    for t in tokens[:5] + tokens[-5:]:
        body = decode(t['token'])
        assert body['node'] == t['node'] and body['nk'] == hp.provision(master, t['node'])['HB_NODE_KEY']
        assert master.hex() not in t['token']


@pytest.mark.parametrize('nodes, why', [
    ([], 'Give 1 to 500'), (['a'] * 501, 'Give 1 to 500'), ('pi-1', 'Give 1 to 500'),
    (['ok', 'bad name'], 'Not valid: bad name'), (['ok', 5], 'Not valid'), (['a', 'a'], 'listed twice'),
])
def test_bulk_tokens_refuse_a_bad_list(make_app, nodes, why):
    c = login(make_app(HEARTBEAT_MASTER_KEY=os.urandom(32).hex()))
    r = c.post('/api/heartbeat/join', json={'nodes': nodes})
    assert r.status_code == 400 and why in r.get_json()['error']


def test_sensehive_logs_in_to_its_heartbeat_broker(make_app):
    sh = make_app(HEARTBEAT_MASTER_KEY=os.urandom(32).hex(), HEARTBEAT_BROKER_USERNAME='hive',
                  HEARTBEAT_BROKER_PASSWORD='s3cret')
    seen = {}

    class Client:
        def tls_set(self):
            seen['tls'] = True

        def username_pw_set(self, user, password):
            seen['login'] = (user, password)

        def reconnect_delay_set(self, **k):
            pass

        def connect_async(self, *a):
            seen['broker'] = a

        def loop_start(self):
            pass
    sh.heartbeat_receiver.start(Client)
    assert seen['login'] == ('hive', 's3cret') and seen['tls'] is True


@pytest.mark.parametrize('node', ['', ' ', '-x', 'a' * 64, 'a b', 'a/b', 'ä', None, 5, ['x']])
def test_bad_node_names_are_refused(make_app, node):
    c = login(make_app(HEARTBEAT_MASTER_KEY=os.urandom(32).hex()))
    r = c.post('/api/heartbeat/join', json={'node': node})
    assert r.status_code == 400 and 'node name' in r.get_json()['error']


def test_join_needs_a_sign_in_never_the_read_only_token(make_app):
    sh = make_app(HEARTBEAT_MASTER_KEY=os.urandom(32).hex(), HEARTBEAT_API_TOKEN='t' * 40)
    c = sh.app.test_client()
    for method in (c.get, c.post):
        bearer = {'Authorization': 'Bearer ' + 't' * 40}
        assert method('/api/heartbeat/join', json={'node': 'x'}, headers=bearer).status_code == 401


def test_join_explains_when_the_receiver_is_off(make_app):
    c = login(make_app())
    assert c.get('/api/heartbeat/join').get_json()['enabled'] is False
    r = c.post('/api/heartbeat/join', json={'node': 'pi'})
    assert r.status_code == 409 and 'HEARTBEAT_MASTER_KEY' in r.get_json()['error']


def test_auto_makes_one_private_fleet_key_per_install_and_keeps_it(make_app, tmp_path):
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    master_a = make_app(db_file=tmp_path / 'a' / 'sh.db', HEARTBEAT_MASTER_KEY='auto').heartbeat_receiver.master
    key_file = tmp_path / 'a' / 'heartbeat_master_key'
    assert master_a == bytes.fromhex(key_file.read_text().strip())
    if os.name == 'posix':
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    again = make_app(db_file=tmp_path / 'a' / 'sh.db', HEARTBEAT_MASTER_KEY='auto').heartbeat_receiver.master
    assert again == master_a                                                     # kept across restarts
    master_b = make_app(db_file=tmp_path / 'b' / 'sh.db', HEARTBEAT_MASTER_KEY='AUTO').heartbeat_receiver.master
    assert master_b != master_a and len(master_b) == 32                         # every install its own fleet


def receiver(sh, path, master):
    """A receiver with its own database: one SenseHive install."""
    import sqlite3

    def db():
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn
    rx = sh.heartbeat_module.Receiver(db, master=master)
    rx.init_db()
    return rx


def test_two_sensehives_never_see_each_others_nodes(make_app, tmp_path):
    """Company A and company B use the same public broker, each with its own SenseHive."""
    sh = make_app()
    rx_a, rx_b = receiver(sh, tmp_path / 'a.db', os.urandom(32)), receiver(sh, tmp_path / 'b.db', os.urandom(32))
    token_a = sh.heartbeat_module.join_token(rx_a.master, 'plant-a-pi', 'broker.hivemq.com', 8883, True)
    token_b = sh.heartbeat_module.join_token(rx_b.master, 'plant-b-pi', 'broker.hivemq.com', 8883, True)
    assert sh.heartbeat_module.fleet_id(hp.topic_key(rx_a.master)) != sh.heartbeat_module.fleet_id(hp.topic_key(rx_b.master))
    msg_a, msg_b = heartbeat_from_token(token_a, 'birth'), heartbeat_from_token(token_b, 'birth')
    # different fleets listen on different topics: B is not even subscribed to A's
    assert msg_a[0] not in rx_b.wanted_topics() and msg_b[0] not in rx_a.wanted_topics()
    # and a message delivered anyway (a wildcard, a stranger copying it) is refused
    assert rx_a.handle(*msg_a) and rx_b.handle(*msg_b)
    assert not rx_b.handle(*msg_a) and not rx_a.handle(*msg_b)
    assert [n['name'] for n in rx_a.nodes()] == ['plant-a-pi'] and [n['name'] for n in rx_b.nodes()] == ['plant-b-pi']
    # the same node name in both companies stays two different, separate nodes
    same_a = heartbeat(rx_a.master, 'gateway')
    assert rx_a.handle(*same_a) and not rx_b.handle(*same_a)
    assert 'gateway' not in [n['name'] for n in rx_b.nodes()] and rx_b.rejected >= 2


def test_a_token_with_a_name_changed_by_hand_is_refused_by_sensehive(make_app):
    sh = make_app(HEARTBEAT_MASTER_KEY=os.urandom(32).hex())
    token = login(sh).post('/api/heartbeat/join', json={'node': 'pi-1'}).get_json()['token']
    b = decode(token)
    t = time.time()
    tpc = hp.topic(bytes.fromhex(b['tk']), hp.window(t))
    forged = hp.seal(bytes.fromhex(b['nk']), bytes.fromhex(b['kid']), tpc,
                     {'n': 'someone-else', 'k': 'birth', 't': t, 's': t, 'q': 1, 'v': '1.1.0'})
    assert not sh.heartbeat_receiver.handle(tpc, forged)                    # a node key speaks for one name only
    assert sh.heartbeat_receiver.nodes() == []


@pytest.mark.skipif(not AGENT_DIR or not (Path(AGENT_DIR) / 'setup.py').is_file(),
                    reason='set AGENT_DIR to a clone of mqtt-heartbeat-service (1.1.1 or newer)')
def test_the_agents_setup_py_reads_our_tokens(make_app):
    spec = importlib.util.spec_from_file_location('agent_setup', Path(AGENT_DIR) / 'setup.py')
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    sh = make_app(HEARTBEAT_MASTER_KEY=os.urandom(32).hex(), HEARTBEAT_BROKER='10.0.0.5', HEARTBEAT_PORT='1883',
                  HEARTBEAT_TLS='false')
    data = login(sh).post('/api/heartbeat/join', json={'node': 'edge-07'}).get_json()
    t = setup.read_token(data['token'][:40] + '\n  ' + data['token'][40:])          # a wrapped paste still works
    assert (t['node'], t['broker'], t['port'], t['tls']) == ('edge-07', '10.0.0.5', 1883, False)
    assert setup.fleet_id(t['tk']) == data['fleet']
    env = dict(line.split('=', 1) for line in setup.agent_env(t).splitlines())
    assert env == hp.provision(sh.heartbeat_receiver.master, 'edge-07')
    with pytest.raises(setup.BadToken):
        setup.read_token(data['token'][:-3])
