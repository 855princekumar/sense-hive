"""Sign-in hardening: retries are limited, passwords are salted and slow
(old ones upgraded), cross-site changes are refused, cookies are safe."""
import hashlib
import os

import pytest


def login(c, password='admin123', user='admin', **headers):
    return c.post('/api/login', json={'username': user, 'password': password}, headers=headers)


def test_repeated_wrong_passwords_lock_sign_in(sh):
    c = sh.app.test_client()
    for _ in range(5):
        assert login(c, 'wrong').status_code == 401
    r = login(c)                                             # even the right password, while locked
    assert r.status_code == 429 and 'Too many' in r.get_json()['error']


def test_the_lock_follows_the_real_client_behind_the_proxy(make_app):
    sh = make_app(SENSEHIVE_TRUST_PROXY='true')
    c = sh.app.test_client()
    for _ in range(5):
        login(c, 'wrong', user='nobody', **{'X-Real-IP': '203.0.113.9'})
    assert login(c, 'wrong', user='other', **{'X-Real-IP': '203.0.113.9'}).status_code == 429
    assert login(c, **{'X-Real-IP': '198.51.100.7'}).status_code == 200   # another client is not punished


def test_the_proxy_header_is_ignored_unless_trusted(sh):
    c = sh.app.test_client()
    for i in range(5):
        login(c, 'wrong', user='nobody', **{'X-Real-IP': f'203.0.113.{i}'})   # rotating a forged header
    assert login(c, 'wrong', user='x', **{'X-Real-IP': '198.51.100.7'}).status_code == 429


def test_new_passwords_are_salted_and_slow(sh):
    with sh.get_db() as conn:
        stored = conn.execute("SELECT password FROM users WHERE username = 'admin'").fetchone()['password']
    assert stored != hashlib.sha256(b'admin123').hexdigest() and stored.startswith(('scrypt:', 'pbkdf2:'))


def test_an_old_sha256_password_still_works_and_is_upgraded(sh):
    with sh.get_db() as conn:
        conn.execute("UPDATE users SET password = ? WHERE username = 'admin'",
                     (hashlib.sha256(b'old-pass-1').hexdigest(),))
        conn.commit()
    assert login(sh.app.test_client(), 'old-pass-1').status_code == 200
    with sh.get_db() as conn:
        stored = conn.execute("SELECT password FROM users WHERE username = 'admin'").fetchone()['password']
    assert stored.startswith(('scrypt:', 'pbkdf2:'))
    assert login(sh.app.test_client(), 'old-pass-1').status_code == 200


def test_the_first_password_can_come_from_the_environment(make_app, capsys):
    sh = make_app(SENSEHIVE_ADMIN_PASSWORD='Initial-pass-77')
    assert login(sh.app.test_client()).status_code == 401
    assert login(sh.app.test_client(), 'Initial-pass-77').status_code == 200
    assert 'Initial-pass-77' not in capsys.readouterr().out          # never printed


def test_a_short_new_password_is_refused(client):
    r = client.post('/api/change-password', json={'current_password': 'admin123', 'new_password': 'short'})
    assert r.status_code == 400


@pytest.mark.parametrize('headers', [{'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}])
def test_another_site_cannot_change_anything(client, headers):
    r = client.post('/api/nodes', json={'topic': 'x/y', 'tag': 't', 'node_name': 'n'}, headers=headers)
    assert r.status_code == 403
    r = client.post('/api/logout', headers=headers)
    assert r.status_code == 403
    assert client.get('/api/nodes').status_code == 200                # still signed in


def test_the_same_site_and_scripts_work(client):
    r = client.post('/api/nodes', json={'topic': 'x/y', 'tag': 't', 'node_name': 'n'},
                    headers={'Origin': 'http://localhost', 'Sec-Fetch-Site': 'same-origin'})
    assert r.status_code in (200, 201)


def test_cookies_are_httponly_and_follow_the_settings(make_app):
    sh = make_app(SENSEHIVE_COOKIE_SAMESITE='strict', SENSEHIVE_COOKIE_SECURE='true', SENSEHIVE_COOKIE_PATH='/sensehive/')
    r = login(sh.app.test_client())
    cookie = r.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in cookie and 'SameSite=Strict' in cookie and 'Secure' in cookie and 'Path=/sensehive/' in cookie


def test_signing_in_starts_a_new_session(sh):
    c = sh.app.test_client()
    with c.session_transaction() as s:
        s['planted'] = 'by-an-attacker'
    login(c)
    with c.session_transaction() as s:
        assert 'planted' not in s and s['logged_in']


@pytest.mark.parametrize('topic', ['x" (timestamp, payload) SELECT 1, password FROM users --', 'a\x00b', 'line\nbreak',
                                   't' * 513])
def test_a_topic_that_could_break_sql_or_logs_is_refused(client, topic):
    r = client.post('/api/nodes', json={'topic': topic, 'tag': 't', 'node_name': 'n'})
    assert r.status_code == 400 and r.get_json()['success'] is False
    assert client.get('/api/nodes').get_json() == []


def test_a_quote_in_a_table_name_cannot_end_the_identifier(sh):
    # defence in depth: even a topic stored before validation existed stays one identifier
    name = sh.table_name_for('evil"; DROP TABLE users; --')
    assert name == 'evil""; DROP TABLE users; --'
    sh.create_topic_table('evil"; DROP TABLE users; --')
    with sh.get_db() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert 'users' in tables and 'evil"; DROP TABLE users; --' in tables


def test_ordinary_topics_keep_their_table_names(sh):
    assert sh.table_name_for('plant/line-1/+/temp/#') == 'plant_line-1_plus_temp_wildcard'


def test_csv_cells_keep_numbers_but_not_formulas(sh):
    import heartbeat
    for cell in (sh.csv_cell, heartbeat.csv_cell):
        assert cell('-12.5') == '-12.5' and cell('+3') == '+3' and cell('42') == '42'
        assert cell('=cmd|calc') == "'=cmd|calc" and cell('@SUM(A1)') == "'@SUM(A1)" and cell('-x') == "'-x"
        assert cell(None) == ''


def test_an_oversized_or_deeply_nested_payload_cannot_hurt(sh, add_topic, publish, client):
    add_topic('big/one')
    publish('big/one', 'x' * (sh.MAX_PAYLOAD_BYTES + 1))
    assert sh.dropped_payloads == 1
    publish('big/one', '[' * 20000 + ']' * 20000)                   # would blow the parser's stack
    nodes = client.get('/api/nodes').get_json()
    assert nodes[0]['entry_count'] == 1                                # kept as text, not lost, no crash


def test_huge_request_bodies_are_refused(client):
    r = client.post('/api/nodes', data='x' * (2 * 1024 * 1024), content_type='application/json')
    assert r.status_code == 413


def test_browser_security_headers(sh):
    r = sh.app.test_client().get('/login')
    assert r.headers['Permissions-Policy'].startswith('camera=()')
    assert r.headers['Cross-Origin-Opener-Policy'] == 'same-origin'
    assert r.headers['Cross-Origin-Resource-Policy'] == 'same-origin'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX file modes')
def test_the_generated_session_secret_is_private(make_app, tmp_path):
    make_app(db_file=tmp_path / "d.db")
    assert (os.stat(tmp_path / 'secret_key').st_mode & 0o777) == 0o600


def test_live_streams_are_capped(make_app):
    sh = make_app(SENSEHIVE_MAX_STREAMS='1')
    c1, c2 = sh.app.test_client(), sh.app.test_client()
    for c in (c1, c2):
        c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    first = c1.get('/stream', buffered=False)
    assert first.status_code == 200
    assert c2.get('/stream', buffered=False).status_code == 503
    first.close()
