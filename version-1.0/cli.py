"""Command line entry point for the pip package: `sensehive --port 5000`."""
import argparse
import os

from . import __version__

DEFAULT_DATA_DIR = os.path.join(os.path.expanduser('~'), '.sensehive')


def build_parser():
    parser = argparse.ArgumentParser(
        prog='sensehive',
        description='SenseHive - lightweight MQTT data logger and dashboard. '
                    'Run -> Add Topic -> Publish -> See Data.',
    )
    parser.add_argument('--host', default=os.getenv('HOST', '0.0.0.0'),
                        help='interface to listen on (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '5000')),
                        help='port for the web dashboard (default: 5000)')
    parser.add_argument('--broker',
                        help='MQTT broker host, e.g. broker.hivemq.com (overrides the broker saved in Settings)')
    parser.add_argument('--broker-port', type=int, default=1883, help='MQTT broker port (default: 1883)')
    parser.add_argument('--broker-username', default='', help='MQTT username (optional)')
    parser.add_argument('--broker-password', default='', help='MQTT password (optional)')
    parser.add_argument('--timezone', help='timezone for stored timestamps, e.g. Asia/Kolkata')
    parser.add_argument('--data-dir',
                        help=f'directory for the SQLite database (default: $DB_PATH or {DEFAULT_DATA_DIR})')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    return parser


def apply_args(args, environ=None):
    """Translate CLI arguments into the environment variables app.py reads at import time."""
    environ = os.environ if environ is None else environ

    if args.data_dir:
        environ['DB_PATH'] = os.path.join(os.path.abspath(os.path.expanduser(args.data_dir)), 'iot_dashboard.db')
    elif not environ.get('DB_PATH'):
        environ['DB_PATH'] = os.path.join(DEFAULT_DATA_DIR, 'iot_dashboard.db')

    if args.broker:
        environ['DEFAULT_BROKER_HOST'] = args.broker
        environ['DEFAULT_BROKER_PORT'] = str(args.broker_port)
        environ['DEFAULT_BROKER_USERNAME'] = args.broker_username
        environ['DEFAULT_BROKER_PASSWORD'] = args.broker_password
        environ['SENSEHIVE_FORCE_BROKER'] = 'true'

    if args.timezone:
        environ['DEFAULT_TIMEZONE'] = args.timezone
        environ['SENSEHIVE_TIMEZONE'] = args.timezone

    return environ


def main(argv=None):
    args = build_parser().parse_args(argv)
    apply_args(args)

    # Imported after the environment is prepared: app.py reads DB_PATH on import
    from . import app as sensehive_app
    sensehive_app.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
