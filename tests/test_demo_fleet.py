"""`sensehive-demo`, the emulated fleet for the quick start and the end-to-end
tests, and what the dashboard shows inside Home Assistant."""
import io
import json
import urllib.request

import demo_fleet


def test_the_fleet_has_unique_devices_with_a_telemetry_and_a_status_topic():
    fleet = demo_fleet.devices(10, 'sensehive-demo')
    names = [d['name'] for d in fleet]
    assert len(set(names)) == 10 and names[0] == 'greenhouse-01' and names[8] == 'greenhouse-02'
    assert all(d['topic'] == 'sensehive-demo/%s/telemetry' % d['name'] and d['lwt'] == 'sensehive-demo/%s/status' % d['name']
               for d in fleet)


def test_readings_are_plausible_json():
    import random
    r = demo_fleet.reading(0, 30, random.Random(1))
    assert set(r) == {'temperature', 'humidity', 'battery', 'rssi'} and 15 < r['temperature'] < 30
    json.dumps(r)


def test_register_signs_in_and_adds_each_device_once(make_app, monkeypatch):
    """--register talks to SenseHive's own API; devices already added are left as they are."""
    sh = make_app()
    client = sh.app.test_client()

    class Resp(io.BytesIO):
        def __init__(self, r):
            super().__init__(r.data)
            self.status = r.status_code

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def open(self, req, timeout=None):
            path = '/' + req.full_url.split('/', 3)[3]
            if req.get_method() == 'POST':
                r = client.post(path, data=req.data, content_type='application/json')
            else:
                r = client.get(path)
            if r.status_code >= 400:
                raise urllib.error.HTTPError(req.full_url, r.status_code, 'err', {}, io.BytesIO(r.data))
            return Resp(r)
    monkeypatch.setattr(demo_fleet.urllib.request, 'build_opener', lambda *a: Opener())
    fleet = demo_fleet.devices(4, 'sensehive-demo')
    assert demo_fleet.register('http://sensehive.test', 'admin', 'admin123', fleet) == 4
    nodes = client.get('/api/nodes').get_json()
    assert sorted(n['node_name'] for n in nodes) == sorted(d['name'] for d in fleet)
    assert all(n['lwt_topic'].endswith('/status') for n in nodes)
    assert demo_fleet.register('http://sensehive.test', 'admin', 'admin123', fleet) == 4      # again: nothing doubled
    assert len(client.get('/api/nodes').get_json()) == 4


def test_inside_home_assistant_the_page_has_no_sign_out(make_app):
    sh = make_app(SENSEHIVE_INGRESS_PROXY='172.30.32.2')
    via_ha = sh.app.test_client().get('/api/stats', environ_base={'REMOTE_ADDR': '172.30.32.2'}).get_json()
    assert via_ha['ingress'] is True
    direct = sh.app.test_client()
    assert direct.post('/api/login', json={'username': 'admin', 'password': 'admin123'}).status_code == 200
    assert direct.get('/api/stats', environ_base={'REMOTE_ADDR': '192.168.1.50'}).get_json()['ingress'] is False
