"""The public demo (demo/Dockerfile) end to end, as a visitor sees it.

  python tools/demo_e2e.py --url http://127.0.0.1:10000 [--out demo-report]

Checks the guard (what a visitor may not change), the emulated fleet, the four
heartbeat agents, the PowerPulse node on its secure topic, and the pages in a
browser on a laptop and a phone (sign-in banner, dashboard, heartbeats).
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

results = []


def check(ok, what):
    results.append((bool(ok), what))
    print(('PASS ' if ok else 'FAIL ') + what, flush=True)


class Http:
    def __init__(self, url):
        self.url = url.rstrip('/') + '/'
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with self.op.open(req, timeout=15) as r:  # nosec B310 - the demo URL given
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')


def wait(fn, what, timeout=90):
    """A check that may take a while (the demo fills in during its first minute)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if fn():
                return check(True, what)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        time.sleep(2)
    check(False, f'{what} (waited {timeout}s)')


def api_checks(url):
    h = Http(url)
    code, res = h.call('POST', 'api/login', {'username': 'admin', 'password': 'wrong'})
    check(code == 401 and 'admin123' in res.get('error', ''), 'a wrong password is refused and the demo login shown')
    for _ in range(8):                                  # never reaches the limiter: nobody locks the demo
        h.call('POST', 'api/login', {'username': 'admin', 'password': 'wrong'})
    code, res = h.call('POST', 'api/login', {'username': 'admin', 'password': 'admin123'})
    check(code == 200 and res.get('success'), 'admin / admin123 signs in, even after many wrong guesses')

    refused = [('POST', 'api/change-password', {'current_password': 'admin123', 'new_password': 'something-else'}),
               ('POST', 'api/broker', {'host': 'example.com', 'port': 1883}),
               ('POST', 'api/broker/test', {'host': 'example.com', 'port': 1883}),
               ('POST', 'api/settings/retention', {'retention_days': 1}),
               ('POST', 'api/retention/run', {}),
               ('PUT', 'api/nodes/1', {'node_name': 'x'}),
               ('DELETE', 'api/nodes/1', None),
               ('POST', 'api/heartbeat/bin', {'action': 'bin', 'node': 'pi-node-01'}),
               ('POST', 'api/secure/keys', {'count': 1}),
               ('POST', 'api/secure/keys/abc/revoke', {})]
    for method, path, body in refused:
        check(h.call(method, path, body)[0] == 403, f'{method} /{path} is refused')
    code, _ = h.call('POST', 'api/heartbeat/join', {'node': 'visitor-node'})
    check(code == 200, 'a visitor can make a join token')

    def nodes():
        return {n['topic']: n for n in h.call('GET', 'api/nodes')[1]}
    wait(lambda: sum(t.startswith('sensehive-demo/') and n['entry_count'] > 0 for t, n in nodes().items()) == 6,
         'six emulated devices logging')
    beacon = 'sensehive/secure/powerpulse-a1b2c3/powerbeacon'
    wait(lambda: nodes()[beacon]['secure'] and nodes()[beacon]['status'] == 'active',
         'the PowerPulse beacon found on its secure topic')
    firmware = (nodes().get(beacon) or {}).get('last_value', {}).get('firmware')
    check(firmware == 'powerpulse-v2.0-auto', 'the beacon opens to the firmware document')
    want = {'edge-gateway-01', 'pi-node-01', 'pi-node-02', 'mini-pc-01'}

    def online():
        return {n['name'] for n in h.call('GET', 'api/heartbeat/nodes')[1]['nodes'] if n['status'] == 'online'}
    wait(lambda: want <= online(), 'four heartbeat agents online')
    code, res = h.call('GET', 'api/broker')
    check(res.get('host') == '127.0.0.1', 'the broker is the private one in the container')


def browser_checks(url, out):
    from playwright.sync_api import sync_playwright
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for name, vp in (('laptop', {'width': 1366, 'height': 820}), ('phone', {'width': 390, 'height': 844})):
            pg = b.new_page(viewport=vp)
            errors = []
            pg.on('console', lambda m, errors=errors: m.type == 'error' and errors.append(m.text))
            pg.goto(url.rstrip('/') + '/login', timeout=90000)
            check(pg.get_by_text('Public demo').is_visible(), f'{name}: the demo sign-in is shown')
            pg.fill('input[type=password]', 'admin123')
            pg.fill('input:not([type=password])', 'admin')
            pg.keyboard.press('Enter')
            pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)
            pg.wait_for_timeout(3000)
            check('greenhouse-01' in pg.inner_text('body'), f'{name}: the fleet on the dashboard')
            pg.screenshot(path=f'{out}/{name}-dashboard.png')
            pg.get_by_text('Secure topics').first.click()
            pg.wait_for_timeout(1500)
            check('powerpulse-v2.0-auto' in pg.inner_text('body'), f'{name}: PowerPulse under Secure topics')
            pg.goto(url.rstrip('/') + '/heartbeats')
            pg.wait_for_timeout(3000)
            check('edge-gateway-01' in pg.inner_text('body'), f'{name}: the heartbeat nodes')
            pg.screenshot(path=f'{out}/{name}-heartbeats.png')
            check(not pg.evaluate('document.documentElement.scrollWidth > window.innerWidth + 1'),
                  f'{name}: no sideways scrolling')
            check(not errors, f'{name}: no console errors {errors[:2]}')
        b.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--url', default='http://127.0.0.1:10000')
    ap.add_argument('--out', default='demo-report')
    ap.add_argument('--no-browser', action='store_true')
    a = ap.parse_args()
    api_checks(a.url)
    if not a.no_browser:
        browser_checks(a.url, a.out)
    failed = [w for ok, w in results if not ok]
    print(f'{len(results) - len(failed)}/{len(results)} checks passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
