"""The public demo in one container: a private broker, SenseHive, real heartbeat
agents, an emulated PowerPulse node and the emulated fleet (sensehive-demo).

Every boot is fresh: new broker login, new heartbeat master key, new secure key,
new database. Nothing here is shared with any other SenseHive. The broker
listens on 127.0.0.1 only; the web port (PORT) is the only way in.

This supervisor runs as root only to set up the agents (setup.py wants root);
every program it starts runs as the unprivileged user "demo". If the broker or
SenseHive stops, the container stops (the host restarts it); the others are
restarted here. One heartbeat node crashes now and then and comes back, so the
dashboard shows a node going offline and returning.
"""
import json
import os
import pwd
import random
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

sys.path.insert(0, '/app')
import demo_fleet                          # noqa: E402  the same fleet as sensehive-demo

RUN = '/run/demo'
AGENT = '/demo/agent'
LOGINS = '/run/demo/broker-logins'
BROKER_CONF = '/run/demo/mosquitto.conf'
BROKER_SETTINGS = ('listener 1883 127.0.0.1\nallow_anonymous false\npassword_file /run/demo/broker-logins\n'
                   'persistence false\nlog_dest stdout\nlog_type error\nlog_type warning\n')
PORT = os.environ.get('PORT', '5000')
URL = f'http://127.0.0.1:{PORT}/'
NODES = ['edge-gateway-01', 'pi-node-01', 'pi-node-02', 'mini-pc-01']
FLAKY = 'pi-node-02'                       # crashes now and then, then comes back
DEVICES = 6
PASSWORD = 'admin123'                      # public: shown on the sign-in page

demo = pwd.getpwnam('demo')
mqtt_user, mqtt_password = 'demo', secrets.token_urlsafe(18)
setup_token = secrets.token_urlsafe(24)
children = {}                              # name -> (Popen, argv, env)


def log(msg):
    print(f'demo: {msg}', flush=True)


def start(name, argv, env=None):
    env = {'PATH': os.environ['PATH'], 'HOME': RUN, 'PYTHONUNBUFFERED': '1', **(env or {})}
    children[name] = (subprocess.Popen(argv, env=env, cwd=RUN, user=demo.pw_uid, group=demo.pw_gid,  # nosec B603
                                       extra_groups=[]), argv, env)


def chown_tree(path):
    for root, _, files in os.walk(path):
        for p in [root] + [os.path.join(root, f) for f in files]:
            os.chown(p, demo.pw_uid, demo.pw_gid)


def broker():
    os.makedirs(RUN, exist_ok=True)
    os.chown(RUN, demo.pw_uid, demo.pw_gid)
    # mosquitto_passwd stores the login hashed; the config only names that file
    subprocess.run(['mosquitto_passwd', '-b', '-c', LOGINS, mqtt_user, mqtt_password], check=True)  # nosec B603 B607
    os.chmod(LOGINS, 0o600)
    os.chown(LOGINS, demo.pw_uid, demo.pw_gid)
    with open(BROKER_CONF, 'w') as f:
        f.write(BROKER_SETTINGS)
    start('broker', ['mosquitto', '-c', BROKER_CONF])


def sensehive():
    start('sensehive', [sys.executable, '/demo/serve.py'], {
        'PORT': PORT, 'DB_PATH': os.path.join(RUN, 'sensehive.db'), 'SECRET_KEY': secrets.token_hex(32),
        'SENSEHIVE_ADMIN_PASSWORD': PASSWORD, 'DEMO_SETUP_TOKEN': setup_token,
        'DEFAULT_BROKER_HOST': '127.0.0.1', 'DEFAULT_BROKER_PORT': '1883', 'SENSEHIVE_FORCE_BROKER': 'true',
        'DEFAULT_BROKER_USERNAME': mqtt_user, 'DEFAULT_BROKER_PASSWORD': mqtt_password,
        'HEARTBEAT_MASTER_KEY': secrets.token_hex(32), 'HEARTBEAT_BROKER': '127.0.0.1', 'HEARTBEAT_PORT': '1883',
        'HEARTBEAT_TLS': 'false', 'HEARTBEAT_BROKER_USERNAME': mqtt_user, 'HEARTBEAT_BROKER_PASSWORD': mqtt_password,
    })


class Api:
    """SenseHive's API as the demo's setup uses it (signed in, past the guard)."""

    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def call(self, path, body=None):
        req = urllib.request.Request(URL + path, data=None if body is None else json.dumps(body).encode(),
                                     method='GET' if body is None else 'POST',
                                     headers={'Content-Type': 'application/json', 'X-Demo-Setup': setup_token})
        try:
            with self.op.open(req, timeout=15) as r:  # nosec B310 - SenseHive on 127.0.0.1
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')


def wait_ready(api):
    for _ in range(120):
        try:
            code, res = api.call('api/health')
            if code == 200 and res.get('mqtt_connected'):
                return
        except OSError:
            pass
        time.sleep(1)
    raise SystemExit('demo: SenseHive did not come up')


def agent_env(node):
    return {'HB_HOME': os.path.join(RUN, 'nodes', node)}


def heartbeat_nodes(api):
    code, res = api.call('api/heartbeat/join', {'nodes': NODES})
    assert code == 200 and res.get('success'), res
    for t in res['tokens']:
        home = agent_env(t['node'])['HB_HOME']
        env = {**os.environ, 'HB_HOME': home, 'HB_JOIN_TOKEN': t['token'],
               'HB_MQTT_USERNAME': mqtt_user, 'HB_MQTT_PASSWORD': mqtt_password}
        out = subprocess.run([sys.executable, os.path.join(AGENT, 'setup.py'), '--files-only', '--interval', '10'],  # nosec B603
                             env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                             check=False)
        assert 'HEARTBEAT_FILES_OK' in out.stdout, out.stdout
        chown_tree(home)
        start('agent ' + t['node'], [sys.executable, os.path.join(AGENT, 'heartbeat_agent.py')], agent_env(t['node']))
    log(f"{len(NODES)} heartbeat agents, fleet {res['fleet']}")


def powerpulse(api):
    code, res = api.call('api/secure/keys', {'count': 1, 'label': 'PowerPulse (demo)'})
    assert code == 200, res
    k = res['keys'][0]
    start('powerpulse', [sys.executable, '/demo/powerpulse.py'], {
        'MQTT_USER': mqtt_user, 'MQTT_PASSWORD': mqtt_password, 'PP_KID': k['kid'], 'PP_KEY': k['key']})
    log('PowerPulse node on a secure topic')


def fleet(api):
    for d in demo_fleet.devices(DEVICES, 'sensehive-demo'):
        api.call('api/nodes', {'topic': d['topic'], 'tag': d['tag'], 'node_name': d['name'], 'lwt_topic': d['lwt']})
    start('fleet', [sys.executable, '/app/demo_fleet.py', '--broker', '127.0.0.1', '--username', mqtt_user,
                    '--password-mqtt', mqtt_password, '--devices', str(DEVICES), '--interval', '5'])
    log(f'{DEVICES} emulated devices')


def stop_all(*_):
    for p, _, _ in children.values():
        if p.poll() is None:
            p.terminate()
    raise SystemExit(0)


def main():
    signal.signal(signal.SIGTERM, stop_all)
    broker()
    time.sleep(1)
    sensehive()
    api = Api()
    wait_ready(api)
    code, res = api.call('api/login', {'username': 'admin', 'password': PASSWORD})
    assert code == 200 and res.get('success'), res
    heartbeat_nodes(api)
    powerpulse(api)
    fleet(api)
    log(f'ready on port {PORT}')

    flaky = 'agent ' + FLAKY
    next_crash, back_at = time.time() + random.randint(300, 480), None
    while True:
        time.sleep(5)
        now = time.time()
        for name, (p, argv, env) in list(children.items()):
            if p.poll() is None or name == flaky and back_at:
                continue
            if name in ('broker', 'sensehive'):
                log(f'{name} stopped ({p.returncode}): the container stops')
                stop_all()
            log(f'{name} stopped ({p.returncode}), restarting')
            start(name, argv, env)
        if back_at is None and now >= next_crash:
            children[flaky][0].kill()      # a crash: no goodbye, the node goes quiet
            back_at = now + random.randint(120, 200)
            log(f'{FLAKY} crashed (on purpose), back in {int(back_at - now)}s')
        elif back_at and now >= back_at:
            start(flaky, children[flaky][1], children[flaky][2])
            back_at, next_crash = None, now + random.randint(480, 720)
            log(f'{FLAKY} back')


if __name__ == '__main__':
    main()
