"""The browser code ships with SenseHive: no page loads anything from another
host, every file a page names exists, the files match their checksums, and
the security headers are sent."""
import hashlib
import os
import re

import pytest

ROOT = os.path.join(os.path.dirname(__file__), '..', 'version-1.0')
PAGES = ('index.html', 'login.html')


def page(name):
    with open(os.path.join(ROOT, 'templates', name), encoding='utf-8') as fh:
        return fh.read()


@pytest.mark.parametrize('name', PAGES)
def test_no_page_loads_anything_from_another_host(name):
    html = page(name)
    assert not re.search(r'(src|href)="(https?:)?//', html), 'external resource in ' + name
    assert 'text/babel' not in html and '<script>' not in html          # no inline scripts (CSP)


@pytest.mark.parametrize('name', PAGES)
def test_every_static_file_a_page_names_exists(name):
    for ref in re.findall(r'(?:src|href)="(static/[^"]+)"', page(name)):
        assert os.path.isfile(os.path.join(ROOT, ref)), ref


def test_the_built_files_match_their_checksums():
    with open(os.path.join(ROOT, 'static', 'SHA256SUMS'), encoding='utf-8') as fh:
        sums = fh.read().split('\n')
    listed = {}
    for line in filter(None, sums):
        digest, path = line.split('  ', 1)
        listed[path] = digest
        with open(os.path.join(ROOT, 'static', path), 'rb') as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == digest, path
    assert {'dashboard.js', 'login.js', 'heartbeats.js', 'secure.js', 'sensehive.css',
            'vendor/react.js'} <= set(listed)


def test_pages_are_served_with_a_strict_script_policy(sh):
    c = sh.app.test_client()
    r = c.get('/login')
    csp = r.headers['Content-Security-Policy']
    assert "script-src 'self'" in csp and 'unsafe-eval' not in csp and "object-src 'none'" in csp
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert c.get('/static/login.js').status_code == 200
    assert c.get('/static/vendor/react.js').status_code == 200


def test_react_is_bundled_locally_and_exposed_as_the_pages_expect():
    """React 19 has no UMD files: tools/react_globals.js is bundled into vendor/react.js,
    which sets the globals React and ReactDOM (with createRoot and createPortal)."""
    with open(os.path.join(ROOT, 'static', 'vendor', 'react.js'), encoding='utf-8') as fh:
        js = fh.read()
    assert 'window.React=' in js.replace(' ', '') and 'window.ReactDOM=' in js.replace(' ', '')
    assert 'createRoot' in js and 'createPortal' in js and '19.3.0' in js
    for page in ('index.html', 'login.html'):
        with open(os.path.join(ROOT, 'templates', page), encoding='utf-8') as fh:
            html = fh.read()
        assert 'static/vendor/react.js' in html and 'production.min.js' not in html
