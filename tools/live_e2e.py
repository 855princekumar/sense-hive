"""End to end with a browser against a SenseHive that is really running: the pip
package (`sensehive`), the Docker image, or (from the add-on repository) the Home
Assistant panel. An emulated fleet (`sensehive-demo`) publishes over a real broker;
the browser signs in like a person and checks what a person sees.

  python tools/live_e2e.py --url http://127.0.0.1:5056 --password admin123 \
      --broker 127.0.0.1 --demo "sensehive-demo" --out live-report

Checks: sign-in; every emulated device has its card with live readings, its node
and tag, and shows Active from its last will; values keep updating; the details
view and CSV; phone, tablet, laptop and desktop with no sideways scroll, nothing
sticking out, no JavaScript, CSP or console error, light and dark; and after the
fleet stops, every device shows Inactive (two of them by their last will alone).
Exit code 0 = every check passed. Prints a STATS line.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'version-1.0'))
from demo_fleet import devices  # noqa: E402  (the same fleet sensehive-demo publishes)

# The same strict layout check the in-process browser test uses (tools/ui_test.py)
with open(os.path.join(ROOT, 'tools', 'ui_test.py'), encoding='utf-8') as _fh:
    _src = _fh.read()
LAYOUT_JS = _src[_src.index('LAYOUT_JS = r"""') + len('LAYOUT_JS = r"""'):]
LAYOUT_JS = LAYOUT_JS[:LAYOUT_JS.index('"""')]

SCREENS = [('phone', 390, 844, 3), ('tablet', 820, 1180, 2), ('laptop', 1366, 768, 1), ('desktop', 1920, 1080, 1)]


class Report:
    def __init__(self, out):
        self.out, self.passes, self.fails = out, 0, []
        os.makedirs(out, exist_ok=True)

    def check(self, label, ok, detail='', page=None):
        if ok:
            self.passes += 1
            print('PASS', label, flush=True)
            return True
        self.fails.append(label)
        print('FAIL', label, ('[' + str(detail)[:500] + ']') if detail else '', flush=True)
        if page is not None:
            try:
                page.screenshot(path=os.path.join(self.out, 'fail-%d.png' % len(self.fails)), full_page=True)
            except Exception:
                pass
        return False


def watch_errors(page, errors):
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' and 'favicon' not in m.text
            and 'net::ERR' not in m.text else None)


def card(frame, name):
    return frame.locator('.sh-card').filter(has_text='node: ' + name)


def wait_cards(frame, fleet, status, seconds=60):
    """Every device's card shows `status` (Active or Inactive) within `seconds`."""
    deadline = time.time() + seconds
    missing = [d['name'] for d in fleet]
    while time.time() < deadline:
        missing = [d['name'] for d in fleet if card(frame, d['name']).filter(has_text=status).count() == 0]
        if not missing:
            return []
        time.sleep(1)
    return missing


def check_fleet(frame, page, fleet, rep, label):
    """What a person sees for the emulated fleet, on one screen."""
    missing = wait_cards(frame, fleet, 'Active')
    rep.check(f'{label}: every device has its card and shows Active (from its last will)', not missing, missing, page)
    first = card(frame, fleet[0]['name']).first
    text = first.inner_text() if first.count() else ''
    rep.check(f'{label}: a card shows the live readings, its node and tag',
              all(k in text for k in ('temperature', 'humidity', 'battery', 'node: ' + fleet[0]['name'], '#' + fleet[0]['tag'])),
              text[:300], page)
    before = first.inner_text() if first.count() else ''
    time.sleep(4)
    after = first.inner_text() if first.count() else ''
    rep.check(f'{label}: values keep updating without a reload', before != after, after[:200], page)
    issues = frame.evaluate(LAYOUT_JS)
    rep.check(f'{label}: the dashboard fits (no sideways scroll, nothing sticks out)', not issues, '; '.join(issues[:4]), page)


def run(url, password, fleet, demo_cmd, broker, out, login=True, open_dashboard=None, shots=None, shot_prefix='quickstart'):
    """The checks; `open_dashboard(page)` returns the frame the dashboard is in (Home Assistant)."""
    from playwright.sync_api import sync_playwright
    rep = Report(out)
    stats = {}
    t0 = time.time()
    demo = subprocess.Popen(shlex.split(demo_cmd) + ['--broker', broker, '--devices', str(len(fleet)),
                                                     '--interval', '1', '--count', '150', '--offline', '2'],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for screen, w, h, scale in SCREENS:
            ctx = browser.new_context(viewport={'width': w, 'height': h}, device_scale_factor=scale)
            page = ctx.new_page()
            errors = []
            watch_errors(page, errors)
            if open_dashboard:
                frame = open_dashboard(page)
            else:
                page.goto(url + '/login')
                if login:
                    page.fill('#username', 'admin')
                    page.fill('#password', password)
                    page.click('#submitBtn')
                    page.wait_for_url(lambda u: '/login' not in u, timeout=20000)
                frame = page
            frame.wait_for_selector('.sh-card', timeout=30000)
            if screen == 'phone':
                stats['dashboard_after_s'] = round(time.time() - t0, 1)
            check_fleet(frame, page, fleet, rep, screen)
            if shots and screen in ('phone', 'laptop'):     # what a person sees, for the docs
                os.makedirs(shots, exist_ok=True)
                page.screenshot(path=os.path.join(shots, '%s-%s.png' % (shot_prefix, screen)))
            if screen == 'laptop':
                theme = frame.locator('button[title="Toggle theme"]').first
                rep.check('laptop: the theme button is there', theme.count() == 1, '', page)
                if theme.count():
                    bg = frame.evaluate("getComputedStyle(document.querySelector('#root > div')).backgroundColor")
                    theme.click()
                    time.sleep(1)
                    dark = frame.evaluate("getComputedStyle(document.querySelector('#root > div')).backgroundColor")
                    issues = frame.evaluate(LAYOUT_JS)
                    rep.check('laptop: dark mode switches and fits', dark != bg and not issues, [bg, dark] + issues[:3], page)
                    theme.click()
                c = card(frame, fleet[1]['name']).first
                c.locator('button', has_text='Details').click()
                time.sleep(1.5)
                body = frame.locator('body').inner_text()
                rep.check('laptop: Details shows the logged readings', 'temperature' in body, body[-300:], page)
                page.keyboard.press('Escape')
            rep.check(f'{screen}: no JavaScript, CSP or console error', not errors, errors[:3], page)
            ctx.close()
        # The fleet stops: two devices drop off (only their last will tells), the rest say offline
        demo.wait(timeout=180)
        log = demo.stdout.read()
        rep.check('the emulated fleet ran and stopped', demo.returncode == 0, log[-400:])
        ctx = browser.new_context(viewport={'width': 1366, 'height': 768})
        page = ctx.new_page()
        if open_dashboard:
            frame = open_dashboard(page)
        else:
            page.goto(url + '/login')
            if login:
                page.fill('#username', 'admin')
                page.fill('#password', password)
                page.click('#submitBtn')
                page.wait_for_url(lambda u: '/login' not in u, timeout=20000)
            frame = page
        frame.wait_for_selector('.sh-card', timeout=30000)
        t = time.time()
        missing = wait_cards(frame, fleet, 'Inactive', seconds=90)
        stats['offline_shown_after_s'] = round(time.time() - t, 1)
        rep.check('every device shows Inactive after the fleet stops (two by their last will alone)', not missing, missing, page)
        ctx.close()
        browser.close()
    print('STATS SenseHive live end to end', json.dumps(stats, sort_keys=True))
    print(f'{rep.passes} checks passed, {len(rep.fails)} failed')
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', required=True, help='where SenseHive runs, e.g. http://127.0.0.1:5056')
    ap.add_argument('--password', default='admin123', help='the admin password')
    ap.add_argument('--broker', default='127.0.0.1', help='the broker the emulated fleet publishes to')
    ap.add_argument('--demo', default='sensehive-demo', help='how to run the emulated fleet (the pip command by default)')
    ap.add_argument('--devices', type=int, default=6)
    ap.add_argument('--out', default='live-report')
    ap.add_argument('--min-checks', type=int, default=0)
    ap.add_argument('--shots', help='also save screenshots of the running fleet here (docs)')
    ap.add_argument('--register-url', help='SenseHive as the fleet reaches it (default: --url; differs when the fleet '
                                           'runs inside the container)')
    a = ap.parse_args()
    fleet = devices(a.devices, 'sensehive-demo')
    # Register the fleet's topics as a person would with Add Node (the command does it for them)
    r = subprocess.run(shlex.split(a.demo) + ['--broker', a.broker, '--devices', str(a.devices), '--count', '1',
                                               '--interval', '0', '--register', a.register_url or a.url,
                                               '--password', a.password],
                       check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    print(r.stdout.strip())
    if r.returncode != 0 or '%d of %d devices are nodes' % (a.devices, a.devices) not in r.stdout:
        print('FAIL sensehive-demo --register could not add the fleet')
        return 1
    rep = run(a.url, a.password, fleet, a.demo, a.broker, a.out, shots=a.shots)
    total = rep.passes + len(rep.fails)
    if a.min_checks and total < a.min_checks:
        print(f'Only {total} checks ran, fewer than {a.min_checks}')
        return 1
    return 0 if not rep.fails else 1


if __name__ == '__main__':
    sys.exit(main())
