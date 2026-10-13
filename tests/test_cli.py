import importlib.util
import os
import re
import sys
import types
from pathlib import Path

import pytest

from conftest import APP_DIR, ROOT


def load_package():
    """Import version-1.0/ as the `sensehive` package, the way the wheel installs it."""
    spec = importlib.util.spec_from_file_location('sensehive', APP_DIR / '__init__.py',
                                                  submodule_search_locations=[str(APP_DIR)])
    package = importlib.util.module_from_spec(spec)
    sys.modules['sensehive'] = package
    spec.loader.exec_module(package)
    import sensehive.cli as cli
    return package, importlib.reload(cli)


def test_versions_are_in_sync():
    package, _ = load_package()
    app_version = re.search(r"__version__ = '([^']+)'", (APP_DIR / 'app.py').read_text(encoding='utf-8')).group(1)
    pyproject_version = re.search(r'^version = "([^"]+)"', (ROOT / 'pyproject.toml').read_text(encoding='utf-8'), re.M).group(1)
    assert package.__version__ == app_version == pyproject_version


def test_version_flag(capsys):
    package, cli = load_package()
    with pytest.raises(SystemExit) as exc:
        cli.main(['--version'])
    assert exc.value.code == 0
    assert package.__version__ in capsys.readouterr().out


def test_defaults_use_home_data_dir():
    _, cli = load_package()
    env = cli.apply_args(cli.build_parser().parse_args([]), environ={})
    assert env['DB_PATH'] == os.path.join(cli.DEFAULT_DATA_DIR, 'iot_dashboard.db')
    assert 'SENSEHIVE_FORCE_BROKER' not in env


def test_existing_db_path_env_is_respected():
    _, cli = load_package()
    env = cli.apply_args(cli.build_parser().parse_args([]), environ={'DB_PATH': '/srv/x.db'})
    assert env['DB_PATH'] == '/srv/x.db'


def test_all_arguments_map_to_environment(tmp_path):
    _, cli = load_package()
    args = cli.build_parser().parse_args([
        '--host', '127.0.0.1', '--port', '8080', '--broker', 'broker.hivemq.com', '--broker-port', '8883',
        '--broker-username', 'u', '--broker-password', 'p', '--timezone', 'Asia/Kolkata', '--data-dir', str(tmp_path),
    ])
    env = cli.apply_args(args, environ={'DB_PATH': '/ignored.db'})
    assert (args.host, args.port) == ('127.0.0.1', 8080)
    assert env['DB_PATH'] == os.path.join(str(tmp_path), 'iot_dashboard.db')
    assert env['DEFAULT_BROKER_HOST'] == 'broker.hivemq.com' and env['DEFAULT_BROKER_PORT'] == '8883'
    assert env['DEFAULT_BROKER_USERNAME'] == 'u' and env['DEFAULT_BROKER_PASSWORD'] == 'p'
    assert env['SENSEHIVE_FORCE_BROKER'] == 'true'
    assert env['SENSEHIVE_TIMEZONE'] == 'Asia/Kolkata'


def test_main_runs_app_with_host_and_port(monkeypatch, tmp_path):
    _, cli = load_package()
    calls = []
    fake_app = types.ModuleType('sensehive.app')
    fake_app.run = lambda host, port: calls.append((host, port, os.environ['DB_PATH']))
    monkeypatch.setitem(sys.modules, 'sensehive.app', fake_app)
    monkeypatch.setattr(sys.modules['sensehive'], 'app', fake_app, raising=False)
    monkeypatch.delenv('DB_PATH', raising=False)
    cli.main(['--port', '5055', '--data-dir', str(tmp_path)])
    assert calls == [('0.0.0.0', 5055, os.path.join(str(tmp_path), 'iot_dashboard.db'))]
