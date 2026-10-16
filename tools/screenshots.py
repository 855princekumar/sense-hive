"""README screenshots, taken from the same seeded test install as the browser UI test
(made-up topics and nodes, no real data), so the pictures always show the current UI.

    python tools/screenshots.py            # writes assets/*.png
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_test  # noqa: E402

OUT = os.path.join(ui_test.ROOT, 'assets')


def shot(page, name):
    page.wait_for_timeout(400)
    page.screenshot(path=os.path.join(OUT, name))
    print('wrote assets/' + name)


def main():
    base = ui_test.serve(5098)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={'width': 1440, 'height': 900}, device_scale_factor=1)
        page.on('dialog', lambda d: d.accept())
        page.goto(base + '/login')
        page.wait_for_selector('#submitBtn')
        shot(page, 'login.png')
        ui_test.login(page, base)
        shot(page, 'dashboard.png')
        page.click('#groupByNode')
        ui_test.settle(page)
        shot(page, 'dashboard-grouped.png')
        page.click('#groupByNode')
        page.locator('.sh-card', has_text='flow-meter').locator('button', has_text='Details').click()
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
        page.goto(base + '/heartbeats')
        page.wait_for_selector('tbody#rows tr td.name')
        ui_test.settle(page)
        shot(page, 'heartbeats.png')
        page.goto(base + '/')
        page.click('[title="Toggle theme"]')          # back to light
        phone = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2,
                                    is_mobile=True, has_touch=True).new_page()
        ui_test.login(phone, base)
        shot(phone, 'phone.png')
        browser.close()


if __name__ == '__main__':
    main()
