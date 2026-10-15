"""Heartbeat receiver: verified heartbeats become per-node state, strangers'
messages are dropped, and the read-only API needs a token or a login."""
import os
import time

import pytest

import heartbeat_protocol as hp

MASTER = os.urandom(32)
TOKEN = 'x' * 40

# Same values as in mqtt-heartbeat-service/tests/test_protocol.py: the copies
# of heartbeat_protocol.py must agree, or nodes and receiver cannot talk.
VECTORS = {
    'kid': 'ebb13644074fabc3',
    'topic_3000000': '3abd08/4a0e86dbcd37698b1225a11a',
}


def test_the_protocol_copy_matches_the_agent():
    m = bytes(range(32))
    assert hp.kid_for(m, 'pi-01').hex() == VECTORS['kid']
    assert hp.topic(hp.topic_key(m), 3_000_000) == VECTORS['topic_3000000']


def sealed(node='pi-01', kind='hb', t=None, s=None, master=MASTER):
    t = time.time() if t is None else t
    s = t - 30 if s is None else s
    kid = hp.kid_for(master, node)
    tpc = hp.topic(hp.topic_key(master), hp.window(t))
    return tpc, hp.seal(hp.node_key(master, kid), kid, tpc, {'n': node, 'k': kind, 't': t, 's': s, 'q': 1, 'v': '1.1.0'})


@pytest.fixture
def hive(make_app):
    return make_app(HEARTBEAT_MASTER_KEY=MASTER.hex(), HEARTBEAT_API_TOKEN=TOKEN)


def api(hive, path, token=TOKEN):
    c = hive.app.test_client()
    return c.get(path, headers={'Authorization': f'Bearer {token}'} if token else {})


def test_off_without_a_master_key_and_nothing_else_changes(make_app):
    sh = make_app()
    assert not sh.heartbeat_receiver.enabled
    c = sh.app.test_client()
    c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    assert c.get('/api/heartbeat/nodes').get_json() == {'enabled': False, 'connected': False, 'nodes': []}
    assert c.get('/api/health').status_code == 200


def test_verified_heartbeats_become_node_state(hive):
    rx = hive.heartbeat_receiver
    birth = time.time() - 30
    assert rx.handle(*sealed(kind='birth', t=birth, s=birth))
    assert rx.handle(*sealed(t=time.time(), s=birth))
    nodes = api(hive, '/api/heartbeat/nodes').get_json()['nodes']
    assert [(n['name'], n['status'], n['agent_version']) for n in nodes] == [('pi-01', 'online', '1.1.0')]
    minutes = api(hive, '/api/heartbeat/minutes?since=0').get_json()['minutes']
    assert len(minutes['pi-01']) >= 1


def test_the_last_will_marks_a_node_offline_and_is_recorded(hive):
    rx = hive.heartbeat_receiver
    s = time.time() - 20
    rx.handle(*sealed(kind='birth', t=s, s=s))
    assert rx.handle(*sealed(kind='lwt', t=s, s=s))
    node = api(hive, '/api/heartbeat/nodes').get_json()['nodes'][0]
    assert node['status'] == 'offline' and node['lwt_at']
    events = api(hive, '/api/heartbeat/events?since=0').get_json()['events']
    assert [e['status'] for e in events] == ['online', 'offline']


@pytest.mark.parametrize('bad', [
    lambda: ('a/b', b'junk'),
    lambda: sealed(master=os.urandom(32)),                       # another fleet or a guessed key
    lambda: sealed(t=time.time() - 3600, s=time.time() - 3700),   # a recording replayed later
])
def test_strangers_on_the_broker_cannot_inject(hive, bad):
    rx = hive.heartbeat_receiver
    assert not rx.handle(*bad())
    assert api(hive, '/api/heartbeat/nodes').get_json()['nodes'] == []
    assert rx.rejected == 1


def test_the_state_survives_a_restart(make_app, tmp_path):
    db = tmp_path / 'persist.db'
    first = make_app(db_file=db, HEARTBEAT_MASTER_KEY=MASTER.hex(), HEARTBEAT_API_TOKEN=TOKEN)
    t = time.time()
    first.heartbeat_receiver.handle(*sealed(kind='birth', t=t, s=t))
    second = make_app(db_file=db, HEARTBEAT_MASTER_KEY=MASTER.hex(), HEARTBEAT_API_TOKEN=TOKEN)
    assert not second.heartbeat_receiver.handle(*sealed(kind='birth', t=t, s=t))   # replay after restart
    assert [n['name'] for n in api(second, '/api/heartbeat/nodes').get_json()['nodes']] == ['pi-01']


@pytest.mark.parametrize('path', ['/api/heartbeat/nodes', '/api/heartbeat/minutes', '/api/heartbeat/events',
                                  '/api/heartbeat/status'])
def test_the_api_needs_the_token_or_a_login(hive, path):
    assert api(hive, path, token=None).status_code == 401
    assert api(hive, path, token='wrong' * 10).status_code == 401
    assert api(hive, path).status_code == 200
    c = hive.app.test_client()
    c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    assert c.get(path).status_code == 200


def test_a_short_token_is_never_accepted(make_app):
    sh = make_app(HEARTBEAT_MASTER_KEY=MASTER.hex(), HEARTBEAT_API_TOKEN='short')
    assert api(sh, '/api/heartbeat/nodes', token='short').status_code == 401


def test_the_api_is_read_only(hive):
    c = hive.app.test_client()
    h = {'Authorization': f'Bearer {TOKEN}'}
    for path in ('/api/heartbeat/nodes', '/api/heartbeat/minutes', '/api/heartbeat/events'):
        assert c.post(path, headers=h).status_code == 405
        assert c.delete(path, headers=h).status_code == 405


def test_the_heartbeats_page_needs_a_login(hive):
    c = hive.app.test_client()
    assert c.get('/heartbeats').status_code == 302
    c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    assert b'Heartbeats' in c.get('/heartbeats').data


def test_old_presence_is_pruned(hive):
    rx = hive.heartbeat_receiver
    t = time.time()
    rx.handle(*sealed(kind='birth', t=t, s=t))
    with rx.db() as conn:
        conn.execute('INSERT INTO hb_minutes (name, minute) VALUES (?, ?)', ('pi-01', int((t - 90 * 86400) // 60)))
        conn.commit()
    rx.prune()
    with rx.db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM hb_minutes WHERE minute < ?', (int((t - 31 * 86400) // 60),)).fetchone()[0] == 0


def test_a_wrong_size_master_key_is_refused():
    import heartbeat
    with pytest.raises(ValueError):
        heartbeat.Receiver(lambda: None, master='abcd')
