import os
import queue
import shutil
import sqlite3

import pytest

from conftest import FIXTURES


# ---------------------------------------------------------------- auth & public endpoints

def test_public_endpoints_need_no_login(sh):
    c = sh.app.test_client()
    health = c.get('/api/health').get_json()
    assert health['status'] == 'healthy'
    assert 'version' not in health                       # no version fingerprint for strangers
    assert c.get('/api/status').get_json() == {'connected': False}
    c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    assert c.get('/api/health').get_json()['version'] == sh.__version__


@pytest.mark.parametrize('method,path', [
    ('get', '/api/nodes'), ('post', '/api/nodes'), ('get', '/api/broker'), ('get', '/api/stats'),
    ('get', '/api/timezones'), ('get', '/api/settings/retention'), ('post', '/api/retention/run'),
    ('get', '/api/nodes/1/history'), ('get', '/api/nodes/1/export'), ('delete', '/api/nodes/1'),
    ('put', '/api/nodes/1'), ('post', '/api/change-password'), ('post', '/api/broker/test'),
])
def test_protected_endpoints_require_login(sh, method, path):
    res = getattr(sh.app.test_client(), method)(path, json={})
    assert res.status_code == 401


def test_dashboard_redirects_to_login(sh):
    res = sh.app.test_client().get('/')
    assert res.status_code == 302
    assert res.headers['Location'].endswith('login')
    assert sh.app.test_client().get('/stream').status_code == 401


def test_login_logout_and_bad_credentials(sh):
    c = sh.app.test_client()
    assert c.post('/api/login', json={'username': 'admin', 'password': 'nope'}).status_code == 401
    assert c.post('/api/login', json={}).status_code == 400
    assert c.post('/api/login', data='not json').status_code == 400
    assert c.post('/api/login', json={'username': 'admin', 'password': 'admin123'}).status_code == 200
    assert c.get('/api/nodes').status_code == 200
    c.post('/api/logout')
    assert c.get('/api/nodes').status_code == 401


def test_change_password(client, sh):
    assert client.post('/api/change-password', json={'current_password': 'wrong', 'new_password': 'x' * 8}).status_code == 401
    changed = client.post('/api/change-password', json={'current_password': 'admin123', 'new_password': 'secret99'})
    assert changed.get_json()['success']
    fresh = sh.app.test_client()
    assert fresh.post('/api/login', json={'username': 'admin', 'password': 'admin123'}).status_code == 401
    assert fresh.post('/api/login', json={'username': 'admin', 'password': 'secret99'}).status_code == 200


def test_templates_served_from_any_working_directory(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    page = client.get('/')
    assert page.status_code == 200 and b'SenseHive' in page.data
    assert client.get('/login').status_code == 200


def source(*parts):
    with open(os.path.join(os.path.dirname(__file__), '..', *parts), encoding='utf-8') as fh:
        return fh.read()


def test_frontend_uses_relative_urls_for_ingress():
    pages = [('version-1.0', 'templates', n) for n in ('index.html', 'login.html')]
    code = [('frontend', n) for n in ('dashboard.jsx', 'login.jsx', 'heartbeats.jsx')]
    for parts in pages + code:
        text = source(*parts)
        for absolute in ("fetch('/", 'fetch(`/', "EventSource('/", "href = '/login'", 'href="/', 'src="/', "href='/"):
            assert absolute not in text, f'{parts[-1]} contains absolute URL {absolute!r}'


def test_frontend_wraps_long_and_nested_payloads():
    """Regression guard for issue #3 (payload overflow)."""
    css = source('frontend', 'input.css')
    jsx = source('frontend', 'dashboard.jsx')
    assert 'overflow-wrap: anywhere' in css and 'white-space: pre-wrap' in css
    assert 'Array.isArray(value)' in jsx
    assert 'min-width: 0' in css


# ---------------------------------------------------------------- database setup & migration

def test_fresh_database_defaults(sh):
    with sh.get_db() as conn:
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        cfg = dict(conn.execute('SELECT host, port, timezone FROM broker_config').fetchone())
        cols = {r[1] for r in conn.execute('PRAGMA table_info(nodes)')}
    assert cfg == {'host': 'broker.hivemq.com', 'port': 1883, 'timezone': 'UTC'}
    assert {'tag', 'node_name', 'lwt_topic', 'lwt_online', 'lwt_offline'} <= cols
    assert sh.get_retention_settings() == {'retention_days': 0, 'retention_max_entries': 0}


def test_wal_can_be_disabled(make_app):
    sh = make_app(SQLITE_WAL='false')
    with sh.get_db() as conn:
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'delete'


def test_env_defaults_seed_new_database(make_app):
    sh = make_app(DEFAULT_BROKER_HOST='mqtt.local', DEFAULT_BROKER_PORT='1884', DEFAULT_TIMEZONE='Asia/Kolkata',
                  RETENTION_DAYS='30', RETENTION_MAX_ENTRIES='1000')
    with sh.get_db() as conn:
        cfg = dict(conn.execute('SELECT host, port, timezone FROM broker_config').fetchone())
    assert cfg == {'host': 'mqtt.local', 'port': 1884, 'timezone': 'Asia/Kolkata'}
    assert sh.get_retention_settings() == {'retention_days': 30, 'retention_max_entries': 1000}


def test_force_broker_overrides_existing_config(make_app, tmp_path):
    db = tmp_path / 'force.db'
    make_app(db_file=db)
    sh = make_app(db_file=db, DEFAULT_BROKER_HOST='core-mosquitto', DEFAULT_BROKER_USERNAME='addons',
                  SENSEHIVE_FORCE_BROKER='true', SENSEHIVE_TIMEZONE='Europe/Berlin')
    with sh.get_db() as conn:
        cfg = dict(conn.execute('SELECT host, username, timezone FROM broker_config').fetchone())
    assert cfg == {'host': 'core-mosquitto', 'username': 'addons', 'timezone': 'Europe/Berlin'}


def test_secret_key_persisted_next_to_database(make_app, tmp_path):
    db = tmp_path / 'k.db'
    first = make_app(db_file=db).app.config['SECRET_KEY']
    assert first and (tmp_path / 'secret_key').exists()
    assert make_app(db_file=db).app.config['SECRET_KEY'] == first
    assert make_app(db_file=db, SECRET_KEY='from-env').app.config['SECRET_KEY'] == 'from-env'


def test_legacy_v1_0_database_is_migrated(make_app, tmp_path):
    db = tmp_path / 'legacy.db'
    shutil.copy(FIXTURES / 'legacy_v1_0.db', db)
    with sqlite3.connect(db) as conn:
        before = conn.execute('SELECT COUNT(*) FROM "sewersense_manhole_node-1_telemetry"').fetchone()[0]

    sh = make_app(db_file=db)
    c = sh.app.test_client()
    assert c.post('/api/login', json={'username': 'admin', 'password': 'admin123'}).status_code == 200
    nodes = c.get('/api/nodes').get_json()
    assert len(nodes) == 1
    node = nodes[0]
    assert node['topic'] == 'sewersense/manhole/node-1/telemetry'
    assert node['tag'] == 'untagged' and node['node_name'] == 'default'
    assert node['entry_count'] == before > 0
    assert node['approx_size_bytes'] > 0
    assert node['status'] == 'untracked'
    assert node['last_value']['node_id'] == 'node-1'


# ---------------------------------------------------------------- topics (nodes) API

def test_add_topic_requires_topic_tag_and_node(client):
    assert client.post('/api/nodes', json={'tag': 't', 'node_name': 'n'}).get_json()['error'] == 'Topic is required'
    assert client.post('/api/nodes', json={'topic': 'a/b', 'node_name': 'n'}).get_json()['error'] == 'Tag is required'
    assert client.post('/api/nodes', json={'topic': 'a/b', 'tag': 't'}).get_json()['error'] == 'Node ID is required'
    assert client.post('/api/nodes', json={'topic': 'a/b', 'tag': ' ', 'node_name': 'n'}).status_code == 400


def test_add_duplicate_topic_rejected(client, add_topic):
    add_topic('a/b')
    res = client.post('/api/nodes', json={'topic': 'a/b', 'tag': 't', 'node_name': 'n'})
    assert res.status_code == 400 and res.get_json()['error'] == 'Topic already exists'


def test_add_topic_subscribes_data_and_lwt_topics(sh, add_topic):
    add_topic('dev1/temp', lwt_topic='dev1/status')
    assert set(sh.mqtt_client.subscribed) == {'dev1/temp', 'dev1/status'}


def test_update_topic_changes_grouping_and_resubscribes(sh, client, add_topic):
    node = add_topic('dev1/temp', lwt_topic='dev1/status')
    res = client.put(f"/api/nodes/{node['id']}", json={'tag': 'env', 'node_name': 'greenhouse', 'lwt_topic': 'gh/lwt'})
    assert res.status_code == 200
    updated = client.get('/api/nodes').get_json()[0]
    assert (updated['tag'], updated['node_name'], updated['lwt_topic']) == ('env', 'greenhouse', 'gh/lwt')
    assert 'gh/lwt' in sh.mqtt_client.subscribed and 'dev1/status' in sh.mqtt_client.unsubscribed
    assert client.put('/api/nodes/999', json={'tag': 'a', 'node_name': 'b'}).status_code == 404
    assert client.put(f"/api/nodes/{node['id']}", json={'tag': '', 'node_name': 'b'}).status_code == 400


def test_delete_topic_drops_table_and_unsubscribes(sh, client, add_topic, publish):
    node = add_topic('del/me')
    publish('del/me', {'v': 1})
    assert client.delete(f"/api/nodes/{node['id']}").get_json()['success']
    assert 'del/me' in sh.mqtt_client.unsubscribed
    assert client.get('/api/nodes').get_json() == []
    with sh.get_db() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='del_me'").fetchone() is None
    assert client.delete(f"/api/nodes/{node['id']}").status_code == 404


# ---------------------------------------------------------------- MQTT message logging

def test_json_and_plain_payloads_are_logged(client, add_topic, publish):
    node = add_topic('sensors/temp')
    publish('sensors/temp', {'temperature': 21.5})
    publish('sensors/temp', 'plain text')
    publish('sensors/temp', '23.4')
    history = client.get(f"/api/nodes/{node['id']}/history").get_json()['history']
    assert [h['payload'] for h in history] == [23.4, {'value': 'plain text'}, {'temperature': 21.5}]


def test_nested_and_array_payloads_round_trip(client, add_topic, publish):
    """Payloads from issue #3 must be stored and returned unchanged."""
    node = add_topic('diun/updates')
    payload = [{'last_login': '2026-03-25T10:49:05-04:00', 'name': 'x'}, {'last_login': 'No logins', 'name': 'y'}]
    publish('diun/updates', payload)
    nested = {'digest': 'sha256:' + 'a' * 64, 'metadata': {'ctn_id': 'b' * 64, 'ctn_state': 'running'}}
    publish('diun/updates', nested)
    history = client.get(f"/api/nodes/{node['id']}/history").get_json()['history']
    assert history[0]['payload'] == nested and history[1]['payload'] == payload


def test_wildcard_subscription_logs_matching_messages(client, add_topic, publish):
    wild = add_topic('home/+/temp')
    multi = add_topic('home/#')
    publish('home/kitchen/temp', {'t': 20})
    publish('home/garage/door', 'open')
    assert len(client.get(f"/api/nodes/{wild['id']}/history").get_json()['history']) == 1
    assert len(client.get(f"/api/nodes/{multi['id']}/history").get_json()['history']) == 2


def test_unknown_topic_and_invalid_utf8_do_not_crash(client, add_topic, publish):
    node = add_topic('bin/data')
    publish('not/subscribed', {'x': 1})
    publish('bin/data', b'\xff\xfe raw')
    history = client.get(f"/api/nodes/{node['id']}/history").get_json()['history']
    assert len(history) == 1 and 'raw' in history[0]['payload']['value']


def test_history_is_limited_to_latest_50(client, add_topic, publish):
    node = add_topic('many/msgs')
    for i in range(60):
        publish('many/msgs', {'i': i})
    history = client.get(f"/api/nodes/{node['id']}/history").get_json()['history']
    assert len(history) == 50 and history[0]['payload'] == {'i': 59}


def test_export_csv(client, add_topic, publish):
    node = add_topic('exp/topic')
    publish('exp/topic', {'a': 1})
    res = client.get(f"/api/nodes/{node['id']}/export")
    assert res.mimetype == 'text/csv'
    lines = res.data.decode().strip().splitlines()
    assert lines[0] == 'Timestamp,Payload' and len(lines) == 2
    assert 'exp_topic.csv' in res.headers['Content-Disposition']


def test_timestamps_use_configured_timezone(make_app):
    sh = make_app(DEFAULT_TIMEZONE='Asia/Kolkata')
    assert sh.get_localized_timestamp().endswith('+05:30')


def test_sse_events_reach_every_connected_client(sh, add_topic, publish):
    add_topic('live/topic')
    queues = [queue.Queue(), queue.Queue()]
    sh.sse_clients.update(queues)
    try:
        publish('live/topic', {'v': 1})
        for q in queues:
            event = q.get_nowait()
            assert event['topic'] == 'live/topic' and event['payload'] == {'v': 1}
    finally:
        sh.sse_clients.difference_update(queues)


# ---------------------------------------------------------------- stats, LWT & grouping

@pytest.mark.parametrize('payload,expected', [
    ('online', 'active'), ('offline', 'inactive'), ('Online', 'active'), ('"offline"', 'inactive'),
    ('1', 'active'), ('0', 'inactive'), ('true', 'active'), ('connected', 'active'), ('lost', 'inactive'),
    ('{"status": "online"}', 'active'), ('{"state": "offline"}', 'inactive'), ('{"online": false}', 'inactive'),
    ('garbage', 'unknown'),
])
def test_classify_lwt_defaults(sh, payload, expected):
    assert sh.classify_lwt(payload) == expected


def test_classify_lwt_custom_payloads(sh):
    assert sh.classify_lwt('ALIVE_NOW', 'alive_now', 'gone') == 'active'
    assert sh.classify_lwt('gone', 'alive_now', 'gone') == 'inactive'


def test_topic_stats_count_and_size(client, add_topic, publish):
    add_topic('stats/topic')
    for i in range(5):
        publish('stats/topic', {'i': i, 'pad': 'x' * 100})
    node = client.get('/api/nodes').get_json()[0]
    assert node['entry_count'] == 5
    assert node['approx_size_bytes'] > 500


def test_lwt_status_and_node_aggregation(sh, client, add_topic, publish):
    add_topic('dev1/temp', tag='env', node_name='dev1', lwt_topic='dev1/status')
    add_topic('dev1/hum', tag='env', node_name='dev1', lwt_topic='dev1/status')
    add_topic('dev2/temp', tag='env', node_name='dev2', lwt_topic='dev2/status')
    add_topic('dev3/temp', tag='misc', node_name='dev3')

    stats = client.get('/api/stats').get_json()
    assert stats['topics'] == {'active': 0, 'inactive': 0, 'unknown': 3, 'untracked': 1}

    q = queue.Queue()
    sh.sse_clients.add(q)
    try:
        publish('dev1/status', 'online')
        publish('dev2/status', 'offline')
        events = [q.get_nowait() for _ in range(2)]
    finally:
        sh.sse_clients.discard(q)
    assert {(e['lwt_topic'], e['status']) for e in events} == {('dev1/status', 'active'), ('dev2/status', 'inactive')}

    nodes = {n['topic']: n for n in client.get('/api/nodes').get_json()}
    assert nodes['dev1/temp']['status'] == nodes['dev1/hum']['status'] == 'active'
    assert nodes['dev2/temp']['status'] == 'inactive'
    assert nodes['dev3/temp']['status'] == 'untracked'

    stats = client.get('/api/stats').get_json()
    assert stats['topics'] == {'active': 2, 'inactive': 1, 'unknown': 0, 'untracked': 1}
    assert stats['nodes'] == {'active': 1, 'inactive': 1, 'unknown': 1}
    assert {n['node_name']: (n['status'], n['topic_count']) for n in stats['node_list']} == {
        'dev1': ('active', 2), 'dev2': ('inactive', 1), 'dev3': ('unknown', 1)}
    assert stats['tags'] == ['env', 'misc']
    assert stats['topic_count'] == 4 and stats['db_size_bytes'] > 0


def test_lwt_status_survives_restart(make_app, tmp_path):
    db = tmp_path / 'lwt.db'
    sh = make_app(db_file=db)
    c = sh.app.test_client()
    c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    c.post('/api/nodes', json={'topic': 'a/data', 'tag': 't', 'node_name': 'a', 'lwt_topic': 'a/lwt'})
    from conftest import FakeMessage
    sh.on_message(None, None, FakeMessage('a/lwt', 'offline'))

    sh = make_app(db_file=db)
    c = sh.app.test_client()
    c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    assert c.get('/api/nodes').get_json()[0]['status'] == 'inactive'


# ---------------------------------------------------------------- retention (issue #1)

def _insert(sh, topic, timestamp, payload='{"v": 1}'):
    with sh.get_db() as conn:
        conn.execute(f'INSERT INTO "{sh.table_name_for(topic)}" (timestamp, payload) VALUES (?, ?)', (timestamp, payload))
        conn.commit()


def _count(sh, topic):
    with sh.get_db() as conn:
        return conn.execute(f'SELECT COUNT(*) FROM "{sh.table_name_for(topic)}"').fetchone()[0]


def test_retention_disabled_by_default(sh, add_topic):
    add_topic('r/t')
    _insert(sh, 'r/t', '2001-01-01T00:00:00+00:00')
    assert sh.apply_retention() == 0 and _count(sh, 'r/t') == 1


def test_retention_by_age_handles_timezone_offsets(sh, client, add_topic, publish):
    add_topic('r/age')
    _insert(sh, 'r/age', '2001-01-01T00:00:00.123456-04:00')
    _insert(sh, 'r/age', '2001-01-02 10:00:00')
    publish('r/age', {'fresh': True})
    assert client.post('/api/settings/retention', json={'retention_days': 7, 'retention_max_entries': 0}).status_code == 200
    assert client.post('/api/retention/run').get_json()['deleted'] == 2
    assert _count(sh, 'r/age') == 1


def test_retention_by_entry_count_keeps_newest(sh, client, add_topic, publish):
    node = add_topic('r/max')
    for i in range(10):
        publish('r/max', {'i': i})
    client.post('/api/settings/retention', json={'retention_days': 0, 'retention_max_entries': 3})
    assert sh.apply_retention() == 7
    history = client.get(f"/api/nodes/{node['id']}/history").get_json()['history']
    assert [h['payload']['i'] for h in history] == [9, 8, 7]


def test_retention_settings_validation(client):
    assert client.post('/api/settings/retention', json={'retention_days': -1}).status_code == 400
    assert client.post('/api/settings/retention', json={'retention_days': 'abc'}).status_code == 400
    assert client.post('/api/settings/retention', json={'retention_days': '14'}).get_json()['retention_days'] == 14
    assert client.get('/api/settings/retention').get_json() == {'retention_days': 14, 'retention_max_entries': 0}


# ---------------------------------------------------------------- broker settings

def test_broker_settings_round_trip(sh, client, monkeypatch):
    started = []
    monkeypatch.setattr(sh.threading, 'Thread', lambda *a, **k: type('T', (), {'start': lambda self: started.append(1)})())
    sh.mqtt_client = None
    cfg = {'host': 'mqtt.example', 'port': 1885, 'username': 'u', 'password': 'p', 'timezone': 'UTC'}
    assert client.post('/api/broker', json=cfg).get_json()['success']
    assert client.get('/api/broker').get_json() == cfg
    assert started == [1]
    assert client.post('/api/broker', json={'host': ''}).status_code == 400


def test_broker_test_reports_failure(client):
    res = client.post('/api/broker/test', json={'host': '127.0.0.1', 'port': 1}).get_json()
    assert res['success'] is False and res['error']


def test_log_lines_cannot_be_forged(sh):
    assert sh.log_safe('evil\nINFO admin signed in\r\x1b[31m') == 'evil INFO admin signed in ?[31m'
    assert len(sh.log_safe('x' * 1000)) == 200


def test_broker_errors_are_fixed_messages_not_exception_text(sh):
    import socket
    assert sh.broker_error_text(ConnectionRefusedError(111, 'secret detail')).startswith('Connection refused')
    assert sh.broker_error_text(socket.gaierror('secret detail')) == 'Host name not found'
    assert 'secret' not in sh.broker_error_text(RuntimeError('secret detail'))


def test_timezones_listed(client):
    assert 'Asia/Kolkata' in client.get('/api/timezones').get_json()['timezones']


# ---------------------------------------------------------------- Home Assistant ingress

def test_ingress_proxy_is_trusted_only_when_configured(make_app):
    sh = make_app(SENSEHIVE_INGRESS_PROXY='172.30.32.2')
    ingress = sh.app.test_client()
    assert ingress.get('/api/nodes', environ_base={'REMOTE_ADDR': '172.30.32.2'}).status_code == 200
    assert ingress.get('/', environ_base={'REMOTE_ADDR': '172.30.32.2'}).status_code == 200
    other = sh.app.test_client()
    assert other.get('/api/nodes', environ_base={'REMOTE_ADDR': '192.168.1.50'}).status_code == 401


def test_ingress_disabled_by_default(sh):
    c = sh.app.test_client()
    assert c.get('/api/nodes', environ_base={'REMOTE_ADDR': '172.30.32.2'}).status_code == 401


def test_session_cookie_name(client):
    assert client.get_cookie('sensehive_session') is not None
