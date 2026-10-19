"""A small emulated fleet to try SenseHive with: `sensehive-demo`.

Each emulated device connects to the broker with its own last will, says
"online" on its status topic and publishes JSON telemetry every few seconds:

  sensehive-demo/<device>/telemetry   {"temperature": 23.4, "humidity": 51, "battery": 97, "rssi": -61}
  sensehive-demo/<device>/status      online | offline (the last will)

With --register it also signs in to SenseHive and adds every device as a node
(topic, tag, node id and LWT topic), so the dashboard fills in by itself:

  sensehive-demo --broker localhost --register http://localhost:5000 --password admin123

Without it, add the topics on the dashboard (Add Node) as printed at start.
The same fleet runs in SenseHive's CI to test the quick start end to end.
"""
import argparse
import json
import math
import random
import sys
import time
import urllib.request
from http.cookiejar import CookieJar

KINDS = ('greenhouse', 'cold-room', 'pump-house', 'roof', 'lab', 'warehouse', 'garage', 'office')


def devices(n, prefix):
    out = []
    for i in range(n):
        name = '%s-%02d' % (KINDS[i % len(KINDS)], i // len(KINDS) + 1)
        out.append({'name': name, 'tag': KINDS[i % len(KINDS)],
                    'topic': '%s/%s/telemetry' % (prefix, name), 'lwt': '%s/%s/status' % (prefix, name)})
    return out


def reading(i, t, rnd):
    return {'temperature': round(22 + 4 * math.sin(t / 60.0 + i) + rnd.uniform(-0.3, 0.3), 1),
            'humidity': int(48 + 10 * math.cos(t / 90.0 + i) + rnd.uniform(-2, 2)),
            'battery': max(5, 100 - i - int(t / 600) % 50),
            'rssi': -55 - (i * 3) % 30}


def mqtt_client(client_id):
    import paho.mqtt.client as mqtt
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except AttributeError:                           # paho-mqtt 1.x
        return mqtt.Client(client_id=client_id)


def register(url, username, password, fleet):
    """Sign in to SenseHive and add each device as a node (an existing topic is left as it is)."""
    jar = CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    base = url.rstrip('/') + '/'

    def post(path, body=None):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     method='GET' if body is None else 'POST', headers={'Content-Type': 'application/json'})
        try:
            with op.open(req, timeout=15) as r:  # nosec B310 - the SenseHive URL the user gave
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    code, res = post('api/login', {'username': username, 'password': password})
    if code != 200 or not res.get('success'):
        raise SystemExit('sensehive-demo: sign-in to %s failed (%s)' % (url, res.get('error') or code))
    code, have = post('api/nodes')
    have = {n.get('topic') for n in have} if code == 200 and isinstance(have, list) else set()
    ready = 0
    for d in fleet:
        if d['topic'] in have:                       # added before: left as it is
            ready += 1
            continue
        code, res = post('api/nodes', {'topic': d['topic'], 'tag': d['tag'], 'node_name': d['name'],
                                       'lwt_topic': d['lwt']})
        ready += bool(res.get('success'))
    return ready


def main(argv=None):
    ap = argparse.ArgumentParser(prog='sensehive-demo', description='An emulated fleet of MQTT devices for SenseHive.')
    ap.add_argument('--broker', default='localhost', help='MQTT broker host (default: localhost)')
    ap.add_argument('--port', type=int, default=1883, help='MQTT broker port (default: 1883)')
    ap.add_argument('--username', default='', help='MQTT username (optional)')
    ap.add_argument('--password-mqtt', default='', help='MQTT password (optional)')
    ap.add_argument('--devices', type=int, default=5, help='number of devices, 1 to 50 (default: 5)')
    ap.add_argument('--interval', type=float, default=5, help='seconds between readings (default: 5)')
    ap.add_argument('--count', type=int, default=0, help='readings per device, then stop (default: run until Ctrl+C)')
    ap.add_argument('--offline', type=int, default=0, help='at the end, this many devices drop off (their last will)')
    ap.add_argument('--prefix', default='sensehive-demo', help='topic prefix (default: sensehive-demo)')
    ap.add_argument('--register', metavar='URL', help='also add the devices as nodes in SenseHive at this URL')
    ap.add_argument('--user', default='admin', help='SenseHive user for --register (default: admin)')
    ap.add_argument('--password', default='admin123', help='SenseHive password for --register (default: admin123)')
    ap.add_argument('--seed', type=int, help='random seed (repeatable readings)')
    a = ap.parse_args(argv)
    if not 1 <= a.devices <= 50:
        ap.error('--devices must be 1 to 50')
    fleet = devices(a.devices, a.prefix.strip('/'))
    rnd = random.Random(a.seed)

    if a.register:
        print('%d of %d devices are nodes in %s' % (register(a.register, a.user, a.password, fleet), len(fleet), a.register))
    else:
        print('Add these on the SenseHive dashboard (Add Node), or run again with --register URL:')
        for d in fleet:
            print('  topic %-40s node %-14s tag %-11s LWT %s' % (d['topic'], d['name'], d['tag'], d['lwt']))

    clients = []
    for d in fleet:
        c = mqtt_client('sensehive-demo-%s-%d' % (d['name'], rnd.randrange(1 << 30)))
        if a.username:
            c.username_pw_set(a.username, a.password_mqtt)
        c.will_set(d['lwt'], 'offline', qos=1, retain=True)
        c.connect(a.broker, a.port, keepalive=15)
        c.loop_start()
        c.publish(d['lwt'], 'online', qos=1, retain=True).wait_for_publish(10)
        clients.append(c)
    print('%d devices online on %s:%d, a reading every %gs%s' % (
        len(fleet), a.broker, a.port, a.interval, '' if a.count else ' (Ctrl+C to stop)'), flush=True)

    sent, t0 = 0, time.time()
    try:
        while not a.count or sent < a.count:
            for i, (d, c) in enumerate(zip(fleet, clients)):
                c.publish(d['topic'], json.dumps(reading(i, time.time() - t0, rnd)), qos=1).wait_for_publish(10)
            sent += 1
            if not a.count or sent < a.count:
                time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    for i, (d, c) in enumerate(zip(fleet, clients)):
        if i < a.offline:                            # drop off without a goodbye: the broker sends the last will
            c.loop_stop()
            sock = c.socket()
            if sock:
                sock.close()
            continue
        c.publish(d['lwt'], 'offline', qos=1, retain=True).wait_for_publish(10)
        c.loop_stop()
        c.disconnect()
    print('Sent %d readings from each of %d devices' % (sent, len(fleet)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
