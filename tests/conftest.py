import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / 'version-1.0'
FIXTURES = Path(__file__).resolve().parent / 'fixtures'

sys.path.insert(0, str(APP_DIR))

ENV_VARS = (
    'DB_PATH', 'SECRET_KEY', 'SQLITE_WAL', 'DEFAULT_BROKER_HOST', 'DEFAULT_BROKER_PORT',
    'DEFAULT_BROKER_USERNAME', 'DEFAULT_BROKER_PASSWORD', 'DEFAULT_TIMEZONE', 'SENSEHIVE_FORCE_BROKER',
    'SENSEHIVE_TIMEZONE', 'SENSEHIVE_INGRESS_PROXY', 'RETENTION_DAYS', 'RETENTION_MAX_ENTRIES',
    'HEARTBEAT_MASTER_KEY', 'HEARTBEAT_API_TOKEN', 'HEARTBEAT_BROKER', 'HEARTBEAT_PORT', 'HEARTBEAT_TLS',
    'HEARTBEAT_NODE_BROKER', 'HEARTBEAT_BROKER_USERNAME', 'HEARTBEAT_BROKER_PASSWORD',
    'SENSEHIVE_ADMIN_PASSWORD', 'SENSEHIVE_TRUST_PROXY', 'SENSEHIVE_MAX_FAILED_LOGINS', 'SENSEHIVE_LOCK_MINUTES',
    'SENSEHIVE_COOKIE_SAMESITE', 'SENSEHIVE_COOKIE_SECURE', 'SENSEHIVE_COOKIE_PATH',
)


class FakeMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload.encode() if isinstance(payload, str) else payload


class FakeMqttClient:
    def __init__(self):
        self.subscribed = []
        self.unsubscribed = []

    def subscribe(self, topic, *args, **kwargs):
        self.subscribed.append(topic)

    def unsubscribe(self, topic, *args, **kwargs):
        self.unsubscribed.append(topic)


@pytest.fixture
def make_app(tmp_path, monkeypatch):
    """Fresh app module bound to a temporary database; pass env overrides as kwargs."""
    def factory(db_file=None, **env):
        for name in ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv('DB_PATH', str(db_file or tmp_path / 'test.db'))
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        import app as module
        module = importlib.reload(module)
        module.init_db()
        module.mqtt_client = FakeMqttClient()
        module.app.config['TESTING'] = True
        return module
    return factory


@pytest.fixture
def sh(make_app):
    return make_app()


@pytest.fixture
def client(sh):
    c = sh.app.test_client()
    res = c.post('/api/login', json={'username': 'admin', 'password': 'admin123'})
    assert res.status_code == 200
    return c


@pytest.fixture
def add_topic(client):
    def add(topic, tag='test', node_name='node-1', **extra):
        res = client.post('/api/nodes', json={'topic': topic, 'tag': tag, 'node_name': node_name, **extra})
        assert res.status_code == 200, res.get_json()
        return next(n for n in client.get('/api/nodes').get_json() if n['topic'] == topic)
    return add


@pytest.fixture
def publish(sh):
    def send(topic, payload):
        if not isinstance(payload, (str, bytes)):
            payload = json.dumps(payload)
        sh.on_message(None, None, FakeMessage(topic, payload))
    return send
