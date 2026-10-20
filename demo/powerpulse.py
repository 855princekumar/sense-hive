"""An emulated PowerPulse node for the public demo: what the firmware publishes.

  <base>/status                       retained {"node_id","location","status":"ON"};
                                      the last will is the same with "OFF" and "reason":"lwt"
  sensehive/secure/<base>/powerbeacon the beacon, sealed with a SenseHive secure key
                                      (SenseHive discovers the node from it, no Add Node)

Every few minutes the plug is pulled: the connection drops without a goodbye,
the broker sends the last will and the dashboard shows the node offline, then
power comes back. Settings come from the environment (demo/run.py).
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, '/app')
import paho.mqtt.client as mqtt            # noqa: E402
import secure                              # noqa: E402  SenseHive's own sealing

BROKER, PORT = os.environ.get('MQTT_HOST', '127.0.0.1'), int(os.environ.get('MQTT_PORT', '1883'))
LOGIN = (os.environ.get('MQTT_USER', ''), os.environ.get('MQTT_PASSWORD', ''))
KID, KEY = os.environ['PP_KID'], bytes.fromhex(os.environ['PP_KEY'])
ROOT = os.environ.get('SENSEHIVE_SECURE_ROOT', 'sensehive/secure')
BASE = os.environ.get('PP_BASE', 'powerpulse-a1b2c3')
LOCATION = os.environ.get('PP_LOCATION', 'pump-room')
EVERY = int(os.environ.get('PP_INTERVAL', '15'))
STATUS, BEACON = f'{BASE}/status', f'{ROOT}/{BASE}/powerbeacon'


def doc(status, **extra):
    return json.dumps({'node_id': BASE, 'location': LOCATION, 'status': status, **extra}, separators=(',', ':'))


def powered(minutes):
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'{BASE}-{random.randrange(1 << 24):06x}')
    if LOGIN[0]:
        c.username_pw_set(*LOGIN)
    c.will_set(STATUS, doc('OFF', reason='lwt'), qos=0, retain=True)
    c.connect(BROKER, PORT, keepalive=15)
    c.loop_start()
    c.publish(STATUS, doc('ON'), retain=True).wait_for_publish(5)
    print(f'powerpulse: power on, beacon every {EVERY}s for {minutes} min', flush=True)
    started, end = time.time(), time.time() + minutes * 60
    while time.time() < end:
        beacon = {'node_id': BASE, 'location': LOCATION, 'ip': '10.0.0.42', 'mac': 'AA:BB:CC:00:11:22',
                  'uptime_sec': int(time.time() - started), 'wifi_ssid': 'demo-lan',
                  'rssi_dbm': random.randint(-68, -55), 'broker': 'lan', 'firmware': 'powerpulse-v2.0-auto',
                  'status': 'ON', 'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  'sensehive_lwt': STATUS}
        c.publish(BEACON, secure.seal(KEY, KID, BEACON, json.dumps(beacon, separators=(',', ':')))).wait_for_publish(5)
        time.sleep(EVERY)
    c.loop_stop()
    c.socket().close()                     # the plug is pulled: no DISCONNECT, the broker sends the will
    print('powerpulse: power lost', flush=True)


if __name__ == '__main__':
    while True:
        powered(random.randint(6, 10))
        time.sleep(random.randint(60, 120))
