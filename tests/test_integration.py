"""End-to-end test against a real MQTT broker.

Runs only when SENSEHIVE_TEST_BROKER=host:port is set (CI starts a Mosquitto service).
"""
import json
import os
import socket
import subprocess
import sys
import time
import uuid

import pytest
import requests_shim as http

from conftest import APP_DIR

BROKER = os.getenv('SENSEHIVE_TEST_BROKER')
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not BROKER, reason='SENSEHIVE_TEST_BROKER not set')]


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture
def running_app(tmp_path):
    host, port = BROKER.split(':')
    web_port = free_port()
    env = dict(os.environ, DB_PATH=str(tmp_path / 'it.db'), DEFAULT_BROKER_HOST=host, DEFAULT_BROKER_PORT=port,
               PORT=str(web_port), PYTHONIOENCODING='utf-8')
    proc = subprocess.Popen([sys.executable, str(APP_DIR / 'app.py')], cwd=str(tmp_path), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    session = http.Session(f'http://127.0.0.1:{web_port}')
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if session.get('/api/health')['mqtt_connected']:
                    break
            except OSError:
                pass
            time.sleep(0.3)
        else:
            pytest.fail('app did not connect to the broker')
        yield session, host, int(port)
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def wait_for(fn, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(0.2)
    return fn()


def test_publish_log_history_lwt_and_retention(running_app):
    import paho.mqtt.client as mqtt

    session, host, port = running_app
    prefix = f'sensehive-it/{uuid.uuid4().hex[:8]}'
    assert session.post('/api/login', {'username': 'admin', 'password': 'admin123'})['success']
    assert session.post('/api/nodes', {'topic': f'{prefix}/temp', 'tag': 'it', 'node_name': 'dev',
                                       'lwt_topic': f'{prefix}/status'})['success']
    assert session.post('/api/nodes', {'topic': f'{prefix}/all/#', 'tag': 'it', 'node_name': 'dev'})['success']
    time.sleep(0.5)

    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, 'CallbackAPIVersion') else mqtt.Client()
    pub.connect(host, port)
    pub.loop_start()
    try:
        for i in range(5):
            pub.publish(f'{prefix}/temp', json.dumps({'i': i, 'nested': {'arr': [1, 2]}}), qos=1).wait_for_publish()
        pub.publish(f'{prefix}/all/a/b', 'hello', qos=1).wait_for_publish()
        pub.publish(f'{prefix}/status', 'online', qos=1, retain=True).wait_for_publish()
    finally:
        pub.loop_stop()
        pub.disconnect()

    def nodes():
        return {n['topic']: n for n in session.get('/api/nodes')}

    temp = wait_for(lambda: (n := nodes()[f'{prefix}/temp'])['entry_count'] == 5 and n['status'] == 'active' and n)
    assert temp, nodes()
    assert temp['last_value'] == {'i': 4, 'nested': {'arr': [1, 2]}}
    wild = wait_for(lambda: nodes()[f'{prefix}/all/#']['entry_count'] == 1)
    assert wild

    stats = session.get('/api/stats')
    assert stats['nodes']['active'] == 1

    session.post('/api/settings/retention', {'retention_days': 0, 'retention_max_entries': 2})
    assert session.post('/api/retention/run', {})['deleted'] == 3
    assert len(session.get(f"/api/nodes/{temp['id']}/history")['history']) == 2
