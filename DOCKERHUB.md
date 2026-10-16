# SenseHive

**Lightweight, self-hosted MQTT data logger and dashboard.**
Run → Add Topic → Publish → See Data.

SenseHive subscribes to the MQTT topics you add, logs every message to SQLite 24/7
(with or without the dashboard open) and shows live values, history and device status
in a clean web UI.

- Source, docs and issues: https://github.com/855princekumar/sense-hive
- Home Assistant add-on: https://github.com/855princekumar/sensehive-ha-addon
- pip package: `pip install sensehive-iot`

---

## Quick start

```bash
docker run -d --name sense-hive \
  -p 5000:5000 \
  -v $(pwd)/sensehive-data:/app/data \
  --restart unless-stopped \
  devprincekumar/sense-hive:latest
```

Open http://localhost:5000 and sign in as `admin` with `SENSEHIVE_ADMIN_PASSWORD` if you set it, otherwise `admin123` (change it under
**Settings → Account**). The default broker is the public `broker.hivemq.com`; change it
under **Settings**.

## Tags

| Tag | Description |
| --- | ----------- |
| `latest` | Latest release, multi-arch (amd64 + arm64) |
| `1.5.0`, `1.5` | SenseHive 1.5.0, multi-arch |
| `1.4.2`, `1.4` | SenseHive 1.4.2 |
| `1.4.1` | SenseHive 1.4.1 |
| `1.4.0` | SenseHive 1.4.0 |
| `1.3.0`, `1.3` | SenseHive 1.3.0 |
| `1.2.0`, `1.2` | SenseHive 1.2.0 |
| `1.1.0`, `1.1` | SenseHive 1.1.0 |
| `arm-pi-5` | Same multi-arch release image; kept for existing Raspberry Pi setups |
| `edge` | Built from the `main` branch on every commit (tested, unreleased) |

One image runs on x86-64 servers and on ARM64 boards (Raspberry Pi 4/5, Jetson,
Apple Silicon). Docker picks the right architecture automatically.

## Features

| Area | What you get |
| ---- | ------------ |
| MQTT logging | Any broker, username/password auth, wildcard topics (`sensors/#`, `home/+/temp`), JSON or plain payloads |
| Dashboard | Live updates (SSE) across all open tabs, last value per topic, last 50 entries history, CSV export |
| Payload rendering | Nested JSON and arrays are pretty-printed and wrap correctly in Chrome and Firefox |
| Organization | Mandatory tag and Node ID per topic; filter by tag; sort by name, tag, status, last update, entries or size; group cards by node |
| Device health | Optional LWT/status topic per topic: online/offline per topic and per node, counts in the navbar, pushed live |
| Stats | Entry count and approximate size per topic, total entries and database size |
| Data management | Retention by age and/or max entries per topic (hourly, or "Run Cleanup Now"), SQLite WAL mode |
| Security | Login-protected UI and API, no CDN and a strict Content Security Policy, SQL-safe topic names, salted slow password hashes, lockout after repeated failed sign-ins, CSRF protection, HttpOnly cookies, persistent random session secret, no data baked into the image |
| Operations | `/api/health` and `/api/status` endpoints, Docker HEALTHCHECK, timezone-aware timestamps |
| Heartbeats (1.2) | Optional receiver for the [MQTT heartbeat agent](https://github.com/855princekumar/mqtt-heartbeat-service): encrypted, authenticated heartbeats and LWT over a public broker, `/heartbeats` page, read-only API. Off unless `HEARTBEAT_MASTER_KEY` is set |

## What's new in 1.5.0

- Heartbeat history: every heartbeat kept (48 h), per-node charts for 1 minute to 30 days with breaks, CSV export for one, selected or all nodes
- Two cards on the dashboard switch between Topic logs and Heartbeats with a smooth fade; dialogs always fit the screen
- Hardened against hostile input: payload size cap, flood limit per node, API token lockout, CSV formula escaping, request size limit, more security headers

## What's new in 1.4.0

- EdgeShell's look (light by default, dark remembered), a layout that fits phones to desktops at 67 to 200 % zoom, a Heartbeats link in the top bar
- Browser code served by SenseHive itself under a strict Content Security Policy (no CDN), SQL-safe topic names, no default password on the sign-in page
- Browser UI test, ruff, Bandit and pip-audit in CI; full documentation at https://github.com/855princekumar/sense-hive/tree/main/docs

## What's new in 1.3.0

- Sign-in hardening: salted password hashes (old ones upgraded automatically), lockout after repeated failures, a new session on each sign-in, cross-site changes refused, configurable cookie flags, `SENSEHIVE_ADMIN_PASSWORD` for the first password

## What's new in 1.2.0

- Heartbeat receiver (off by default): verifies encrypted heartbeats from edge nodes, per-node online/offline/silent state, `/heartbeats` page, read-only API with a bearer token. See the README

## What's new in 1.1.0

- Topic stats, tags, node grouping and LWT device status
- Data retention and SQLite WAL mode
- Wildcard topics are now logged
- JSON arrays and long values no longer overflow the cards
- Live updates reach every open browser tab
- Multi-arch image (amd64 + arm64); paho-mqtt 2.x support
- Home Assistant ingress support (used by the add-on)
- No development database shipped in the image
- v1.0 databases are migrated automatically. Keep your existing `/app/data` volume.

## Docker Compose

```yaml
services:
  sense-hive:
    image: devprincekumar/sense-hive:latest
    container_name: sense-hive
    ports:
      - "5000:5000"
    volumes:
      - ./sensehive-data:/app/data
    environment:
      DEFAULT_BROKER_HOST: broker.hivemq.com   # first start only
      DEFAULT_TIMEZONE: UTC
    restart: unless-stopped
```

## Environment variables

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `DEFAULT_BROKER_HOST` / `DEFAULT_BROKER_PORT` | `broker.hivemq.com` / `1883` | Broker for a new database |
| `DEFAULT_BROKER_USERNAME` / `DEFAULT_BROKER_PASSWORD` | empty | Broker credentials for a new database |
| `SENSEHIVE_FORCE_BROKER` | `false` | `true` applies the `DEFAULT_BROKER_*` values on every start |
| `DEFAULT_TIMEZONE` | `UTC` | Timezone for a new database |
| `RETENTION_DAYS` / `RETENTION_MAX_ENTRIES` | `0` (off) | Initial retention policy |
| `RETENTION_INTERVAL` | `3600` | Seconds between retention runs |
| `SQLITE_WAL` | `true` | Set `false` on network filesystems (NFS/SMB) |
| `SECRET_KEY` | random, persisted | Session secret |
| `DB_PATH` | `/app/data/iot_dashboard.db` | Database location |

## Home Assistant

HAOS / Supervised users can install the add-on in one click: it opens in the sidebar,
connects to the Mosquitto add-on automatically and stores data in Home Assistant backups.
See https://github.com/855princekumar/sensehive-ha-addon

## Quality

Every image is built by CI after the full regression suite passes (73 tests on Python
3.9 to 3.13, including an end-to-end run against a real Mosquitto broker), plus a container
health check and a pip package smoke test.
