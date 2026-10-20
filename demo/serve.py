"""SenseHive as the public demo runs it: the real app, with a guard in front.

Anyone may sign in (admin / admin123, shown on the sign-in page), look around,
add a few topics and make join tokens. What would spoil the demo for the next
visitor is refused: the password, the broker, retention, deleting or editing
nodes, the recycle bin and the secure keys. The demo's own setup (demo/run.py)
passes with a per-boot secret header.
"""
import os
import re
import sys

sys.path.insert(0, '/app')
import app as sensehive                    # noqa: E402  the real SenseHive, unchanged
from flask import jsonify, request         # noqa: E402

USER = 'admin'
PASSWORD = os.environ.get('SENSEHIVE_ADMIN_PASSWORD', 'admin123')
SETUP = os.environ.pop('DEMO_SETUP_TOKEN', '')
MAX_NODES = 40                             # topics a visitor may add, all together

REFUSED = [
    ('POST', r'/api/change-password'),
    ('POST', r'/api/broker'),
    ('POST', r'/api/broker/test'),         # would connect to any host:port from here
    ('POST', r'/api/settings/retention'),
    ('POST', r'/api/retention/run'),
    ('PUT', r'/api/nodes/\d+'),
    ('DELETE', r'/api/nodes/\d+'),
    ('POST', r'/api/heartbeat/bin'),
    ('POST', r'/api/secure/keys(/.*)?'),
]

BANNER = ('<div style="position:fixed;left:0;right:0;bottom:0;z-index:9999;padding:8px 12px;'
          'font:14px/1.4 system-ui,sans-serif;text-align:center;background:#1e293b;color:#f8fafc">'
          'Public demo: sign in as <b>admin</b> / <b>admin123</b>. An emulated fleet, real heartbeat agents '
          'and a PowerPulse node on a private broker. Changes are limited and it resets on restart. '
          '<a style="color:#93c5fd" href="https://github.com/855princekumar/sense-hive">Get SenseHive</a></div>')

app = sensehive.app


@app.before_request
def guard():
    if SETUP and request.headers.get('X-Demo-Setup') == SETUP:
        return None
    path, method = request.path, request.method
    if any(method == m and re.fullmatch(p, path) for m, p in REFUSED):
        return jsonify({'success': False, 'error': 'Not in the public demo. Install SenseHive to try this.'}), 403
    if method == 'POST' and path == '/api/login':
        data = request.get_json(silent=True) or {}
        # A wrong guess never reaches the sign-in limiter, so nobody can lock the demo for everyone.
        if data.get('username') != USER or data.get('password') != PASSWORD:
            return jsonify({'success': False, 'error': 'In the demo, sign in as admin / admin123.'}), 401
    if method == 'POST' and path == '/api/nodes':
        with sensehive.get_db() as conn:
            if conn.execute('SELECT COUNT(*) FROM nodes').fetchone()[0] >= MAX_NODES:
                return jsonify({'success': False, 'error': 'The demo has enough topics already.'}), 403
    return None


@app.after_request
def banner(resp):
    """The demo's sign-in on the sign-in page (only there: it never covers the dashboard)."""
    if request.path == '/login' and resp.mimetype == 'text/html' and resp.status_code == 200:
        resp.direct_passthrough = False            # a file response: read it to edit it
        body = resp.get_data(as_text=True)
        if '</body>' in body:
            resp.set_data(body.replace('</body>', BANNER + '</body>', 1))
            resp.headers.pop('ETag', None)
    return resp


if __name__ == '__main__':
    sensehive.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')))  # nosec B104 - the demo's web port
