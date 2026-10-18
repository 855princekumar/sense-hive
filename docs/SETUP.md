# Setup

SenseHive is one small Python service with a SQLite database. Pick the install
that fits your machine; all of them give the same dashboard on port 5000.

| Install | Best for | Database |
| ------- | -------- | -------- |
| [Docker](#docker) | Servers, Raspberry Pi (amd64 and arm64 images) | `/app/data/iot_dashboard.db` in a volume |
| [Docker Compose](#docker-compose) | The same, kept in a file with its settings | as Docker |
| [pip](#pip) | A laptop or a machine without Docker | `~/.sensehive/iot_dashboard.db` |
| [Home Assistant](#home-assistant) | A Home Assistant OS box | `/data/iot_dashboard.db` (in HA backups) |
| [From source](#from-source) | Development | `version-1.0/data/` unless `DB_PATH` is set |

## Minimum system requirements

| | Minimum | Recommended |
| --- | --- | --- |
| CPU | 1 core, ARMv8 (64-bit, e.g. Raspberry Pi 3) or x86-64 | 2 cores |
| Memory | 128 MB free (SenseHive uses about 28 MB idle, 35 MB with 500 nodes and 100 busy topics) | 512 MB free |
| Disk | 200 MB (image 57 MB) plus your data | 1 GB or more; about 0.35 MB per heartbeat node per day, topic data as published |
| OS | Linux with Docker 20.10+, Home Assistant OS, or any OS with Python 3.9 to 3.13 | Linux with Docker |
| Network | A reachable MQTT broker (the public default needs internet) | Your own broker on the LAN |
| Clock | Correct time (NTP); secure topics and heartbeats refuse messages more than a few minutes off | |
| Browser | A current Chrome, Edge, Firefox or Safari, desktop or phone | |

Measured, not estimated: see [Performance](PERFORMANCE.md).

## Docker

```bash
docker run -d --name sensehive --restart unless-stopped \
  -p 5000:5000 \
  -v sensehive-data:/app/data \
  -e SENSEHIVE_ADMIN_PASSWORD='choose-a-strong-password' \
  devprincekumar/sense-hive:latest
```

Open `http://<host>:5000` and sign in as `admin` with the password you chose.

- Without the volume (`-v`), data is lost when the container is removed.
- Tags: `latest` and `X.Y.Z` for releases, `edge` for the newest `main`.
  The images are multi-arch, so the same tag works on a Raspberry Pi.
- The image ships no database and no secrets; a health check
  calls `/api/health`.

## Docker Compose

```yaml
services:
  sensehive:
    image: devprincekumar/sense-hive:latest
    container_name: sensehive
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
    env_file: .env          # secrets stay out of this file
```

`.env` next to it (never commit it):

```bash
SENSEHIVE_ADMIN_PASSWORD=choose-a-strong-password
DEFAULT_BROKER_HOST=192.168.1.10
DEFAULT_TIMEZONE=Asia/Kolkata
```

Ready-made files for x86 and ARM are in [`Docker-compose/`](../Docker-compose).

## pip

```bash
pip install sensehive-iot
sensehive --port 5000 --data-dir ~/.sensehive
```

`sensehive --help` lists the options: `--host`, `--port`, `--data-dir`,
`--timezone`, `--broker`, `--broker-port`, `--broker-username`,
`--broker-password`.

## Home Assistant

Install the add-on from the
[SenseHive add-on repository](https://github.com/855princekumar/sensehive-ha-addon).
It opens in the Home Assistant sidebar (ingress), finds the Mosquitto add-on by
itself and keeps its database in Home Assistant backups.

## From source

```bash
git clone https://github.com/855princekumar/sense-hive.git
cd sense-hive
pip install -r version-1.0/requirements.txt
python version-1.0/app.py
```

The browser code is already built into `version-1.0/static`; Node.js is only
needed to change it (see [Development](DEVELOPMENT.md#front-end)).

## First sign-in

1. Sign in as `admin`. The password is `SENSEHIVE_ADMIN_PASSWORD` if you set it
   for the first start, otherwise `admin123`.
2. **Change the password straight away** if it is still `admin123`
   (**Settings** > **Change Password**, at least 6 characters).
3. In **Settings**, set your MQTT broker and timezone, then **Add Node** with a
   topic, a node ID and a tag.

Five wrong passwords for a user or from one address lock sign-in for 15
minutes (see [Security](SECURITY.md#sign-in)).

## Upgrades

Pull the new image and recreate the container with the same volume:

```bash
docker pull devprincekumar/sense-hive:latest
docker rm -f sensehive
docker run ...   # the same command as before
```

Databases from older versions are migrated in place on the first start.
Passwords from versions before 1.3 keep working and are rehashed on the next
sign-in.

## Backups

The whole state is the database file, plus the secret key file next to it
(`secret_key`, unless `SECRET_KEY` is set): it signs sessions and encrypts the
[secure topic](SECURE-TOPICS.md) keys, so back it up with the database. Copy it while SenseHive is stopped, or
use SQLite's online backup while it runs:

```bash
docker exec sensehive python -c "import sqlite3; s=sqlite3.connect('/app/data/iot_dashboard.db'); d=sqlite3.connect('/app/data/backup.db'); s.backup(d)"
```

The `-wal` and `-shm` files next to the database are normal (WAL mode).
