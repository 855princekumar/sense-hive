"""README screenshots (assets/*.png), taken from a real SenseHive in a browser, so the
pictures always show the current UI. CI runs it on every change and keeps the
result as an artifact; commit the new images after a change to the pages.

SenseHive runs from source on a temporary database, filled the same way the
browser UI test fills its own, but with an example site (greenhouse, cold room,
pump house...) instead of the test's edge cases. Made-up data, no real devices.

    python tools/screenshots.py                          # writes assets/*.png
    python tools/screenshots.py --broker 127.0.0.1:1883  # "Connected" in the header
"""
import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_test  # noqa: E402

OUT = os.path.join(ui_test.ROOT, 'assets')

# The example site the pictures show (ui_test's own data is made to break layouts)
ui_test.TOPICS = [
    ('greenhouse/zone-1/climate', 'greenhouse', 'greenhouse-esp32', 'greenhouse/status',
     lambda i: {'temperature': round(24 + random.uniform(-1.5, 1.5), 1), 'humidity': random.randint(55, 68),
                'co2_ppm': random.randint(420, 610)}),
    ('greenhouse/zone-1/soil', 'greenhouse', 'greenhouse-esp32', 'greenhouse/status',
     lambda i: {'moisture': random.randint(31, 44), 'ph': round(random.uniform(6.2, 6.8), 2)}),
    ('cold-room/freezer-2/temperature', 'cold-chain', 'cold-room-pi', 'cold-room/status',
     lambda i: {'temperature': round(-18 + random.uniform(-0.6, 0.6), 1), 'door': 'closed', 'compressor': 'on'}),
    ('pump-house/pump-1/power', 'energy', 'pump-house-meter', 'pump-house/status',
     lambda i: {'voltage': round(229 + random.uniform(-2, 2), 1), 'current': round(random.uniform(3.8, 4.4), 2),
                'kwh': 1820 + i}),
    ('weather/roof/station', 'weather', 'roof-station', '',
     lambda i: {'wind_kmh': round(random.uniform(4, 18), 1), 'rain_mm': 0.2, 'uv': 5}),
    ('lab/air-quality', 'lab', 'lab-sensor', '',
     lambda i: {'pm2_5': random.randint(6, 14), 'pm10': random.randint(11, 22), 'voc': random.randint(80, 140)}),
]
ui_test.HB_NODES = [('gateway-01', 'online', 0, 1.3), ('greenhouse-pi', 'online', 0, 1.3),
                    ('pump-house-pi', 'online', 0, 1.3), ('cold-room-pi', 'offline', 1500, 1.2),
                    ('warehouse-gw', 'silent', 400, 1.3)]
ui_test.NO_BEATS = set()


def shrink(path):
    """A palette PNG: a fraction of the size, the same to the eye (a UI has few colours)."""
    try:
        from PIL import Image
    except ImportError:
        return
    Image.open(path).convert('RGB').quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                                             dither=Image.Dither.NONE).save(path, optimize=True)


def shot(page, name):
    page.wait_for_timeout(400)
    path = os.path.join(OUT, name)
    page.screenshot(path=path)
    shrink(path)
    print('wrote assets/%-24s %4.0f KB' % (name, os.path.getsize(path) / 1024))


def main():
    global OUT
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--broker', help='host:port of an MQTT broker, so the header shows Connected')
    a = ap.parse_args()
    OUT = a.out
    os.makedirs(OUT, exist_ok=True)
    if a.broker:
        host, _, port = a.broker.partition(':')
        os.environ.update(DEFAULT_BROKER_HOST=host, DEFAULT_BROKER_PORT=port or '1883', SENSEHIVE_FORCE_BROKER='true')
    random.seed(11)
    base = ui_test.serve(5098)
    import time
    import app as sensehive
    with sensehive.get_db() as conn:                # the devices' last wills: two online, the cold room offline
        now = time.strftime('%Y-%m-%dT%H:%M:%S')
        conn.executemany("INSERT OR REPLACE INTO lwt_status (topic, payload, status, updated_at) VALUES (?, ?, ?, ?)",
                         [('greenhouse/status', 'online', 'active', now), ('pump-house/status', 'online', 'active', now),
                          ('cold-room/status', 'offline', 'inactive', now)])
        conn.commit()
    if a.broker:
        sensehive.init_mqtt()                        # as `sensehive` does at start
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=1)
        page.on('dialog', lambda d: d.accept())
        page.goto(base + '/login')
        page.wait_for_selector('#submitBtn')
        shot(page, 'login.png')
        ui_test.login(page, base)
        if a.broker:
            for _ in range(40):                      # the header polls the broker status every 5 s
                if page.get_by_text('Connected', exact=True).count():
                    break
                page.wait_for_timeout(500)
            page.reload()
            page.wait_for_selector('.sh-card')
            ui_test.settle(page)
        shot(page, 'dashboard.png')
        page.click('#addNodeBtn')                        # Add Node: topic, node id, tag, last will
        page.wait_for_selector('.sh-modal')
        page.fill('input[placeholder="e.g., sensors/temperature"]', 'boiler-room/boiler-1/telemetry')
        page.fill('input[placeholder="e.g., greenhouse-esp32"]', 'boiler-room-esp32')
        page.fill('input[placeholder="e.g., environment"]', 'heating')
        page.fill('input[placeholder="e.g., greenhouse-esp32/status"]', 'boiler-room/status')
        shot(page, 'add-node.png')
        page.keyboard.press('Escape')
        page.click('#groupByNode')
        ui_test.settle(page)
        shot(page, 'dashboard-grouped.png')
        page.click('#groupByNode')
        page.locator('.sh-card', has_text='greenhouse/zone-1/climate').locator('button', has_text='Details').click()
        page.wait_for_selector('.sh-modal')
        shot(page, 'history.png')
        page.keyboard.press('Escape')
        page.click('[title="Settings"]')
        page.wait_for_selector('.sh-modal')
        shot(page, 'settings.png')
        page.keyboard.press('Escape')
        page.click('[title="Toggle theme"]')
        ui_test.settle(page)
        shot(page, 'dashboard-dark.png')
        page.click('[title="Toggle theme"]')          # heartbeats in the light theme
        ui_test.settle(page)
        page.click('#viewHeartbeats')
        page.wait_for_selector('#hbTable tbody tr')
        ui_test.settle(page)
        shot(page, 'heartbeats.png')
        page.locator('#hbTable tbody tr', has_text='greenhouse-pi').locator('.hb-history').click()
        page.wait_for_selector('.sh-modal svg')
        page.click('.sh-modal [data-range="1d"]')
        page.wait_for_selector('#hbDownNow, .sh-modal svg rect, .sh-modal svg polyline', timeout=15000)
        ui_test.settle(page)
        shot(page, 'heartbeat-history.png')
        page.click('.sh-modal [data-range="7d"]')
        page.wait_for_selector('.sh-modal svg rect', timeout=15000)
        ui_test.settle(page)
        shot(page, 'heartbeat-uptime.png')
        page.keyboard.press('Escape')
        page.click('#hbBinOpen')                         # the recycle bin (1.7)
        page.wait_for_selector('#hbBinDialog')
        shot(page, 'heartbeat-bin.png')
        page.locator('#hbBinDialog button', has_text='Close').click()
        page.click('#hbAddNode')                         # add a node without EdgeShell (1.8)
        page.fill('#hbJoinName', 'boiler-room-pi')
        page.click('#hbJoinGo')
        page.wait_for_selector('#hbJoinToken')
        shot(page, 'heartbeat-add-node.png')            # a throwaway key of this temporary install
        page.keyboard.press('Escape')
        page.click('#viewTopics')
        page.wait_for_selector('.sh-card')
        page.click('#kindSecure')                        # secure topics (1.7): found by themselves
        page.wait_for_selector('#secureView .sh-card')
        ui_test.settle(page)
        shot(page, 'secure-topics.png')
        page.click('#genKeysBtn')
        page.fill('#genCount', '3')
        page.fill('#genLabel', 'pump-house')
        shot(page, 'secure-generate.png')
        page.click('#genGo')
        page.wait_for_selector('#madeDialog')
        shot(page, 'secure-keys.png')                    # throwaway keys of this temporary install
        page.locator('#madeDialog button', has_text='Done').click()
        page.click('#infoSecure')
        page.wait_for_selector('#guideBody')
        shot(page, 'secure-guide.png')
        page.keyboard.press('Escape')
        page.click('#kindOpen')
        phone = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2,
                                    is_mobile=True, has_touch=True).new_page()
        ui_test.login(phone, base)
        shot(phone, 'phone.png')
        phone.goto(base + '/?view=heartbeats')
        phone.wait_for_selector('#hbTable tbody tr')
        ui_test.settle(phone)
        shot(phone, 'phone-heartbeats.png')
        browser.close()


if __name__ == '__main__':
    main()
