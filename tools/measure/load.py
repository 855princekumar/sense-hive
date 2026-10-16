"""Load generator for SenseHive measurements (runs in a container on the test network).
Phase marks are printed so the host can sample docker stats per phase."""
import json
import os
import random
import sys
import threading
import time

import paho.mqtt.client as mqtt
import requests

sys.path.insert(0, '/proto')
import heartbeat_protocol as hp  # noqa: E402

BASE = 'http://sh:5000'
MASTER = bytes.fromhex(os.environ['MASTER'])
NODES = int(os.environ.get('NODES', '500'))
TOPICS = int(os.environ.get('TOPICS', '100'))
RATE = float(os.environ.get('RATE', '50'))          # data messages per second, all topics together
PHASE = int(os.environ.get('PHASE', '120'))


def mark(name):
    print(f'PHASE {name} {time.time():.0f}', flush=True)


s = requests.Session()
for _ in range(60):
    try:
        if s.get(BASE + '/api/health', timeout=2).ok:
            break
    except Exception:
        time.sleep(1)
r = s.post(BASE + '/api/login', json={'username': 'admin', 'password': os.environ['PW']}, timeout=10)
assert r.ok, r.text
for i in range(TOPICS):
    r = s.post(BASE + '/api/nodes', json={'topic': f'load/site-{i % 10}/sensor-{i}', 'tag': f'site-{i % 10}',
                                          'node_name': f'dev-{i}'}, timeout=10)
    assert r.ok, r.text
print('topics created', TOPICS, flush=True)

pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='load-' + os.urandom(4).hex())
pub.connect('broker', 1883)
pub.loop_start()

ids = [hp.provision(MASTER, f'pi-node-{n:04d}') for n in range(NODES)]
session = time.time()
seq = [0] * NODES
stop = threading.Event()


def heartbeats():
    """Each node sends birth, then hb every 10 s (spread evenly)."""
    tk = bytes.fromhex(ids[0]['HB_TOPIC_KEY'])
    gap = 10.0 / NODES
    first = True
    while not stop.is_set():
        for n, p in enumerate(ids):
            if stop.is_set():
                return
            seq[n] += 1
            tpc = hp.topic(tk, hp.window())
            body = {'n': p['HB_NODE'], 'k': 'birth' if first else 'hb', 't': time.time(), 's': session, 'q': seq[n],
                    'v': '1.1.0'}
            pub.publish(tpc, hp.seal(bytes.fromhex(p['HB_NODE_KEY']), bytes.fromhex(p['HB_KID']), tpc, body), qos=1)
            time.sleep(gap)
        first = False


def data():
    while not stop.is_set():
        i = random.randrange(TOPICS)
        payload = {'temperature': round(random.uniform(18, 35), 2), 'humidity': round(random.uniform(30, 80), 1),
                   'battery': round(random.uniform(3.3, 4.2), 2), 'rssi': random.randint(-90, -40)}
        pub.publish(f'load/site-{i % 10}/sensor-{i}', json.dumps(payload), qos=0)
        time.sleep(1.0 / RATE)


time.sleep(5)
mark('idle_start')
time.sleep(PHASE)
mark('idle_end')

hb = threading.Thread(target=heartbeats, daemon=True)
hb.start()
mark('hb_start')
time.sleep(PHASE)
mark('hb_end')

dt = threading.Thread(target=data, daemon=True)
dt.start()
mark('both_start')
time.sleep(PHASE)
mark('both_end')
stop.set()
time.sleep(3)


def timed(path, n=20):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        resp = s.get(BASE + path, timeout=10)
        out.append((time.perf_counter() - t) * 1000)
        assert resp.ok, (path, resp.status_code)
    out.sort()
    return resp.json(), out[len(out) // 2], out[int(len(out) * 0.95) - 1]


nodes, p50, p95 = timed('/api/heartbeat/nodes')
online = sum(1 for x in nodes['nodes'] if x['status'] == 'online')
print(f'API /api/heartbeat/nodes: {len(nodes["nodes"])} nodes ({online} online) p50 {p50:.1f} ms p95 {p95:.1f} ms')
st, p50, p95 = timed('/api/heartbeat/status')
print(f'API /api/heartbeat/status: rejected {st["rejected"]} p50 {p50:.1f} ms p95 {p95:.1f} ms')
since = int(time.time()) - 3600
mins, p50, p95 = timed(f'/api/heartbeat/minutes?since={since}')
node_minutes = sum(len(v) for v in mins['minutes'].values())
print(f'API /api/heartbeat/minutes: {node_minutes} node-minutes p50 {p50:.1f} ms p95 {p95:.1f} ms')
topics, p50, p95 = timed('/api/nodes')
entries = sum(t['entry_count'] for t in topics)
print(f'API /api/nodes: {len(topics)} topics, {entries} entries p50 {p50:.1f} ms p95 {p95:.1f} ms')
stats, p50, p95 = timed('/api/stats')
print(f'API /api/stats: db {stats["db_size_bytes"]} bytes p50 {p50:.1f} ms p95 {p95:.1f} ms')
print(f'DATA entries {entries} sent_rate {RATE}/s')
