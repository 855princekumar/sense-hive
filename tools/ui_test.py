"""Browser UI test: layout on every screen size and zoom, and the main interactions.

Starts SenseHive in-process on a temporary database seeded like a real
install (topics with long names, nested and array payloads, LWT status,
heartbeat nodes in every state), then drives Chromium through every page on
phone, tablet, laptop and desktop sizes and at browser zoom levels, checking
that:

  - no page scrolls sideways and no JavaScript error or CSP violation occurs,
  - nothing sticks out of its card, dialog or top bar (text that spills out of
    a button or badge counts too) and no short word is broken over two lines,
  - sign-in, the tag filter, sorting, grouping, dark mode, the settings and
    add-node dialogs and the heartbeats page work.

    pip install playwright && python -m playwright install chromium
    python tools/ui_test.py --out ui-report

Exit code 1 on any failure; screenshots of failures go to --out.
"""
import argparse
import json
import os
import random
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'version-1.0'))

# name, CSS width, CSS height, device scale. Browser zoom Z on a W px screen
# gives a W/Z px wide layout at Z device pixels per CSS pixel.
SCREENS = [('phone', 390, 844, 3), ('tablet', 820, 1180, 2), ('laptop', 1366, 768, 1),
           ('desktop', 1920, 1080, 1)]
ZOOMS = [('laptop', 1366, 768, z) for z in (0.67, 1.25, 1.5, 2.0)] + \
        [('desktop', 1920, 1080, z) for z in (1.5, 2.0)]
PAGES = ['/login', '/', '/heartbeats']
PASSWORD = 'ui-test-' + os.urandom(6).hex()

LAYOUT_JS = r"""
() => {
  const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' && +cs.opacity !== 0; };
  const name = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
    + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '')
    + (el.textContent ? ' "' + el.textContent.replace(/\s+/g, ' ').trim().slice(0, 30) + '"' : '');
  const out = [];
  const vw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > vw + 1) {
    const wide = [...document.body.querySelectorAll('*')].filter(el => vis(el)
      && el.getBoundingClientRect().right > vw + 1 && !(el.parentElement && el.parentElement.getBoundingClientRect().right > vw + 1));
    out.push('page scrolls sideways: content ' + document.documentElement.scrollWidth + 'px wide in a ' + vw
      + 'px window, widened by ' + wide.slice(0, 3).map(el => name(el) + ' (' + Math.round(el.getBoundingClientRect().width) + 'px)').join(', '));
  }
  const boxes = [...document.querySelectorAll('.sh-card, .sh-nav, .sh-modal, .sh-bar, header, .wrap, .pill')].filter(vis);
  for (const el of document.querySelectorAll('.sh-card, .sh-modal'))
    if (vis(el) && el.getBoundingClientRect().width < 120)
      out.push(name(el) + ' is squeezed to ' + Math.round(el.getBoundingClientRect().width) + 'px wide');
  // a short word or number split over two lines ("ONLI / NE", "7 / 91") means its box is too narrow
  const range = document.createRange();
  for (const el of document.querySelectorAll('body *')) {
    if (el.childElementCount || !vis(el)) continue;
    const t = el.textContent.trim();
    if (t.length < 2 || t.length > 20 || /\s/.test(t) || el.closest('pre, code, textarea, .payload-box, .break-all')) continue;
    range.selectNodeContents(el);
    const tops = new Set([...range.getClientRects()].filter(r => r.width > 0).map(r => Math.round(r.top)));
    if (tops.size > 1) out.push('"' + t + '" is broken over ' + tops.size + ' lines in ' + name(el));
  }
  for (const box of boxes) {
    if (/(auto|scroll)/.test(getComputedStyle(box).overflowX)) continue;   // scrolls on purpose (wide tables)
    const b = box.getBoundingClientRect();
    for (const el of box.querySelectorAll('*')) {
      if (!vis(el)) continue;
      let p = el.parentElement, clipped = false;
      while (p && p !== box) {                 // inside a scroll or clip area of the box: intended
        if (/(auto|scroll|hidden|clip)/.test(getComputedStyle(p).overflowX)) { clipped = true; break; }
        p = p.parentElement;
      }
      if (clipped) continue;
      const r = el.getBoundingClientRect();
      if (r.right > b.right + 1.5 || r.left < b.left - 1.5)
        out.push(name(el) + ' sticks out of ' + name(box) + ' by ' + Math.round(Math.max(r.right - b.right, b.left - r.left)) + 'px');
      const cs = getComputedStyle(el);
      if (!el.childElementCount && el.textContent.trim() && cs.display !== 'inline'
          && !/(auto|scroll|hidden|clip)/.test(cs.overflowX) && el.scrollWidth > el.clientWidth + 1)
        out.push('text spills out of ' + name(el) + ' (' + el.scrollWidth + 'px in ' + el.clientWidth + 'px)');
    }
  }
  return [...new Set(out)].slice(0, 15);
}
"""

TOPICS = [
    # topic, tag, node, LWT topic, payloads
    ('plant/line-1/boiler/temperature', 'boiler', 'gateway-01', 'plant/line-1/status',
     lambda i: {'temperature': round(60 + random.random() * 20, 2), 'unit': 'C'}),
    ('plant/line-1/boiler/pressure', 'boiler', 'gateway-01', 'plant/line-1/status',
     lambda i: {'pressure': round(2 + random.random(), 3), 'unit': 'bar', 'ok': True}),
    ('site-b/water/flow-meter/readings-with-a-very-long-topic-name-that-does-not-wrap-easily', 'water', 'pi-node-2',
     'site-b/pi-node-2/lwt',
     lambda i: {'flow': [round(random.random() * 9, 2) for _ in range(6)],
                'meta': {'sensor': 'FM-' + 'X' * 40, 'calibrated': '2026-01-12', 'nested': {'a': 1, 'b': [1, 2, 3]}}}),
    ('site-b/water/level', 'water', 'pi-node-2', 'site-b/pi-node-2/lwt',
     lambda i: round(random.random() * 100, 1)),
    ('lab/raw-string', 'lab', 'mini-pc', '',
     lambda i: 'a-single-unbroken-value-' + 'Z' * 80),
    ('lab/energy/meter-7', 'energy', 'mini-pc', '',
     lambda i: {'kwh': 1200 + i, 'phase': ['L1', 'L2', 'L3'], 'v': [229.8, 230.1, 231.0]}),
]
HB_NODES = [('gateway-01', 'online', 0, 1.2), ('pi-node-2', 'online', 0, 1.2),
            ('mini-pc', 'offline', 900, 1.1),
            ('plant-east-gate-sensor-hub-panel-with-a-long-name', 'silent', 400, 1.1)]


def seed(app):
    """Topics, payloads, LWT states and heartbeat nodes, written straight to the database."""
    random.seed(7)
    now = time.time()
    with app.get_db() as conn:
        c = conn.cursor()
        for topic, tag, node, lwt, _make in TOPICS:
            c.execute('INSERT INTO nodes (topic, tag, node_name, lwt_topic) VALUES (?, ?, ?, ?)', (topic, tag, node, lwt))
        conn.commit()
    for topic, _tag, _node, _lwt, make in TOPICS:
        table = app.create_topic_table(topic)
        with app.get_db() as conn:
            conn.executemany(f'INSERT INTO "{table}" (timestamp, payload) VALUES (?, ?)',  # nosec B608 - fixed test topics
                             [(time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(now - 60 * (50 - i))), json.dumps(make(i)))
                              for i in range(50)])
            conn.commit()
    with app.get_db() as conn:
        conn.execute("INSERT INTO lwt_status (topic, payload, status, updated_at) VALUES "
                     "('plant/line-1/status', 'online', 'active', ?), ('site-b/pi-node-2/lwt', 'offline', 'inactive', ?)",
                     (time.strftime('%Y-%m-%dT%H:%M:%S'),) * 2)
        for name, status, age, version in HB_NODES:
            conn.execute('INSERT INTO hb_nodes (name, status, session, last_t, last_seen, since, version, lwt_at) '
                         'VALUES (?, ?, 1, ?, ?, ?, ?, ?)',
                         (name, status, now - age, now - age, now - 7200, str(version),
                          now - age if status == 'offline' else None))
        conn.commit()
    app.heartbeat_receiver.init_db()
    app.heartbeat_receiver.tracker.nodes.clear()        # statuses from the table, not a live tracker


class Report:
    def __init__(self, out):
        self.out, self.fails, self.passes = out, [], 0
        os.makedirs(out, exist_ok=True)

    def check(self, label, ok, detail='', page=None):
        if ok:
            self.passes += 1
            return True
        self.fails.append(f'{label}: {detail}')
        print(f'  FAIL  {label}: {detail}')
        if page is not None:
            safe = ''.join(c if c.isalnum() else '_' for c in label)[:90]
            try:
                page.screenshot(path=os.path.join(self.out, safe + '.png'))
            except Exception:
                pass
        return False


def settle(page):
    """Wait for fetched content; the dashboard keeps an event stream open, so never fully idle."""
    try:
        page.wait_for_load_state('networkidle', timeout=2500)
    except Exception:
        pass
    page.wait_for_timeout(500)


def login(page, base):
    page.goto(base + '/login')
    page.fill('#username', 'admin')
    page.fill('#password', PASSWORD)
    page.click('#submitBtn')
    page.wait_for_url(lambda u: '/login' not in u, timeout=15000)
    page.wait_for_selector('.sh-card', timeout=15000)
    settle(page)


def watch_errors(page, errors):
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' and 'favicon' not in m.text
            and 'net::ERR' not in m.text else None)


def layout(page):
    return page.evaluate(LAYOUT_JS)


def run_layout(pw, base, rep, configs, dark=False):
    for label, w, h, scale in configs:
        zoomed = label in ('laptop', 'desktop') and scale != 1
        css_w, css_h = (round(w / scale), round(h / scale)) if zoomed else (w, h)
        tag = f'{label}{f" at {int(scale * 100)}% zoom" if zoomed else ""}{" dark" if dark else ""}'
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={'width': css_w, 'height': css_h}, device_scale_factor=scale,
                                  is_mobile=label == 'phone', has_touch=label in ('phone', 'tablet'))
        if dark:
            ctx.add_init_script("try { localStorage.setItem('sensehive-dark', '1') } catch (e) {}")
        page = ctx.new_page()
        errors = []
        watch_errors(page, errors)
        print(f'== {tag}: {css_w}x{css_h} CSS px')
        errors.clear()
        page.goto(base + '/login')
        page.wait_for_selector('#submitBtn')
        rep.check(f'{tag} /login layout', not (i := layout(page)), '; '.join(i[:6]), page)
        login(page, base)
        for path in PAGES[1:]:
            errors.clear()
            page.goto(base + path)
            page.wait_for_selector('.sh-card, tbody#rows tr td', timeout=15000)
            settle(page)
            issues = layout(page)
            rep.check(f'{tag} {path} layout', not issues, '; '.join(issues[:6]), page)
            rep.check(f'{tag} {path} no JavaScript errors', not errors, '; '.join(errors[:3]), page)
        page.goto(base + '/')
        page.wait_for_selector('.sh-card')
        for name, opener in (('settings dialog', '[title="Settings"]'), ('add-node dialog', '#addNodeBtn')):
            page.click(opener)
            page.wait_for_selector('.sh-modal')
            settle(page)
            issues = layout(page)
            rep.check(f'{tag} {name} fits the screen', not issues, '; '.join(issues[:6]), page)
            page.keyboard.press('Escape')
            if page.locator('.sh-modal').count():
                page.locator('.sh-modal [data-close]').first.click()
            rep.check(f'{tag} {name} closes', page.locator('.sh-modal').count() == 0, '', page)
        browser.close()


def run_interactions(pw, base, rep, label, w, h, scale):
    browser = pw.chromium.launch()
    ctx = browser.new_context(viewport={'width': w, 'height': h}, device_scale_factor=scale,
                              is_mobile=label == 'phone', has_touch=label == 'phone')
    page = ctx.new_page()
    errors = []
    watch_errors(page, errors)
    page.on('dialog', lambda d: d.accept())
    print(f'== interactions on {label} ({w}x{h})')

    page.goto(base + '/')
    rep.check(f'{label}: signed-out visit goes to the sign-in page', '/login' in page.url, page.url, page)
    page.fill('#username', 'admin')
    page.fill('#password', 'wrong-password')
    page.click('#submitBtn')
    page.wait_for_selector('#loginError')
    rep.check(f'{label}: a wrong password shows an error', 'invalid' in page.inner_text('#loginError').lower(),
              page.inner_text('#loginError'), page)
    rep.check(f'{label}: the sign-in page shows no default password', 'admin123' not in page.content(), '', page)
    login(page, base)
    errors.clear()                               # the refused sign-in above logs a 401
    cards = page.locator('.sh-card')
    start = cards.count()                         # an earlier run may have added its own topic
    rep.check(f'{label}: every topic has a card', start >= len(TOPICS), start, page)
    rep.check(f'{label}: nested payloads render', page.locator('.payload-json').count() >= 1, '', page)

    page.select_option('#tagFilter', 'water')
    page.wait_for_timeout(300)
    rep.check(f'{label}: the tag filter narrows the cards', page.locator('.sh-card').count() == 2,
              page.locator('.sh-card').count(), page)
    page.select_option('#tagFilter', 'all')
    page.select_option('#sortBy', 'name')
    page.wait_for_timeout(300)
    first = page.locator('.sh-card h3').first.inner_text()
    rep.check(f'{label}: sorting by name puts the first topic first', first == sorted(t[0] for t in TOPICS)[0], first, page)
    page.check('#groupByNode')
    page.wait_for_timeout(300)
    rep.check(f'{label}: grouping by node shows one heading per node',
              page.locator('h2', has_text='gateway-01').count() == 1, '', page)
    rep.check(f'{label}: grouped layout', not (i := layout(page)), '; '.join(i[:4]), page)
    page.uncheck('#groupByNode')

    bg = page.evaluate("getComputedStyle(document.querySelector('#root > div')).backgroundColor")
    rep.check(f'{label}: light theme by default', bg in ('rgb(249, 250, 251)', 'rgb(241, 245, 249)'), bg, page)
    page.click('[title="Toggle theme"]')
    page.wait_for_timeout(300)
    page.reload()
    page.wait_for_selector('.sh-card')
    dark = page.evaluate("getComputedStyle(document.querySelector('#root > div')).backgroundColor")
    rep.check(f'{label}: the dark theme choice is remembered', dark != bg, dark, page)
    page.click('[title="Toggle theme"]')

    page.click('#heartbeatsLink')
    page.wait_for_selector('tbody#rows tr td')
    settle(page)
    rows = page.locator('tbody#rows tr').count()
    rep.check(f'{label}: the heartbeats page lists every node', rows == len(HB_NODES), rows, page)
    for state in ('online', 'offline', 'silent'):
        rep.check(f'{label}: a {state} heartbeat node is shown', page.locator(f'td.{state}').count() >= 1, '', page)
    page.click('#dashboardLink')
    page.wait_for_selector('.sh-card')

    page.click('#addNodeBtn')
    page.wait_for_selector('.sh-modal')
    fields = page.locator('.sh-modal input[type=text]')
    for k, value in enumerate((f'ui-test/{label}/new-topic', 'ui-test-node', 'ui')):
        fields.nth(k).fill(value)
    page.locator('.sh-modal button', has_text='Add').last.click()
    try:                                         # (no wait_for_function: the page's CSP forbids eval)
        page.locator('.sh-card').nth(start).wait_for(timeout=10000)
        added = True
    except Exception:
        added = False
    rep.check(f'{label}: adding a topic shows its card', added, page.locator('.sh-card').count(), page)
    rep.check(f'{label}: no JavaScript errors or CSP violations', not errors, '; '.join(errors[:3]), page)

    page.click('#logoutBtn')
    page.wait_for_url(lambda u: '/login' in u, timeout=10000)
    rep.check(f'{label}: signing out returns to the sign-in page', '/login' in page.url, page.url, page)
    browser.close()


def serve(port):
    """SenseHive on a fresh, seeded temporary database, in a background thread. Returns its URL."""
    for stream in (sys.stdout, sys.stderr):        # the app prints emoji; Windows consoles are cp1252
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass
    tmp = tempfile.mkdtemp(prefix='sensehive-ui-')
    os.environ.update(DB_PATH=os.path.join(tmp, 'ui.db'), SENSEHIVE_ADMIN_PASSWORD=PASSWORD,
                      HEARTBEAT_MASTER_KEY=os.urandom(32).hex(), SECRET_KEY=os.urandom(16).hex())
    import app
    app.init_db()
    seed(app)
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    threading.Thread(target=lambda: app.app.run(port=port, threaded=True, use_reloader=False),
                     daemon=True).start()
    time.sleep(1.5)
    return f'http://127.0.0.1:{port}'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default='ui-report')
    ap.add_argument('--port', type=int, default=5099)
    ap.add_argument('--quick', action='store_true', help='base screen sizes only, no zoom levels')
    ap.add_argument('--min-checks', type=int, default=0,
                    help='fail if fewer checks ran (guards against a suite that silently shrinks)')
    args = ap.parse_args()

    base = serve(args.port)
    rep = Report(args.out)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        run_layout(pw, base, rep, SCREENS + ([] if args.quick else ZOOMS))
        run_layout(pw, base, rep, [SCREENS[0], SCREENS[3]], dark=True)
        run_interactions(pw, base, rep, 'desktop', 1920, 1080, 1)
        run_interactions(pw, base, rep, 'phone', 390, 844, 3)
    total = rep.passes + len(rep.fails)
    short = args.min_checks and total < args.min_checks
    print(f'\n{rep.passes} checks passed, {len(rep.fails)} failed')
    if short:
        print(f'Only {total} checks ran, fewer than the required {args.min_checks}: part of the suite was skipped')
    if rep.fails:
        print(f'Screenshots of failures: {os.path.abspath(args.out)}')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write(f'### Browser UI test\n\n| Checks | Passed | Failed | Required at least |\n|---|---|---|---|\n'
                    f'| {total} | {rep.passes} | {len(rep.fails)} | {args.min_checks or "-"} |\n\n'
                    'Phone, tablet, laptop and desktop; zoom 67 to 200 percent; light and dark.\n\n')
            for line in rep.fails[:40]:
                f.write(f'- FAIL {line}\n')
    return 1 if rep.fails or short else 0


if __name__ == '__main__':
    sys.exit(main())
