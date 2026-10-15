"""Sign-in hardening: retries are limited, passwords are salted and slow
(old ones upgraded), cross-site changes are refused, cookies are safe."""
import hashlib

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
