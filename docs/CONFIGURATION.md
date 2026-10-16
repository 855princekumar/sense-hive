# Configuration

Most day-to-day settings live in the UI (**Settings**): the MQTT broker and its
credentials, the timezone, data retention and the admin password. Environment
variables set the defaults for a new database and everything that must be
decided before SenseHive starts.

Keep secrets (passwords, keys, tokens) in an `.env` file or your orchestrator's
secret store, never in a compose file you commit.

## Core

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `DB_PATH` | `/app/data/iot_dashboard.db` | Database file |
| `HOST` / `PORT` | `0.0.0.0` / `5000` | Listen address and port |
| `SECRET_KEY` | random, saved next to the database | Signs session cookies; set it to share sessions across replicas |
| `SQLITE_WAL` | `true` | WAL mode; set `false` on network filesystems (NFS, SMB) |
| `MQTT_MAX_PAYLOAD_BYTES` | `65536` | Larger MQTT messages are dropped and counted (protects the disk) |
| `SENSEHIVE_MAX_STREAMS` | `50` | Open live-update views (browser tabs) at once; more get 503 |
| `SENSEHIVE_INGRESS_PROXY` | empty | Home Assistant add-on only: requests from this proxy address are already signed in by Home Assistant |

## MQTT broker (defaults for a new database)

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `DEFAULT_BROKER_HOST` / `DEFAULT_BROKER_PORT` | `broker.hivemq.com` / `1883` | Broker |
| `DEFAULT_BROKER_USERNAME` / `DEFAULT_BROKER_PASSWORD` | empty | Broker credentials (secret) |
| `SENSEHIVE_FORCE_BROKER` | `false` | `true` applies the values above on every start, overriding the UI |
| `DEFAULT_TIMEZONE` | `UTC` | Timezone for a new database |
| `SENSEHIVE_TIMEZONE` | empty | Overrides the stored timezone on every start (CLI `--timezone`) |

## Retention

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `RETENTION_DAYS` | `0` (off) | Delete entries older than this many days |
| `RETENTION_MAX_ENTRIES` | `0` (off) | Keep at most this many entries per topic |
| `RETENTION_INTERVAL` | `3600` | Seconds between retention runs |

Both can be changed later in **Settings** > **Data Retention**, and run at once
with **Run cleanup now**.

## Sign-in and sessions

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `SENSEHIVE_ADMIN_PASSWORD` | empty (`admin123`) | First password of `admin` in a new database; never printed |
| `SENSEHIVE_MAX_FAILED_LOGINS` | `5` | Failures allowed per user and per address ... |
| `SENSEHIVE_LOCK_MINUTES` | `15` | ... within this window, before sign-in is refused |
| `SENSEHIVE_SESSION_HOURS` | `12` | Session lifetime |
| `SENSEHIVE_COOKIE_SECURE` | `false` | `true` behind HTTPS |
| `SENSEHIVE_COOKIE_SAMESITE` | `Lax` | `Strict` behind HTTPS on its own site |
| `SENSEHIVE_COOKIE_PATH` | `/` | Cookie path, e.g. `/sensehive/` under a sub-path |
| `SENSEHIVE_TRUST_PROXY` | `false` | Behind a reverse proxy: the client address comes from `X-Real-IP` |

## Heartbeat receiver

Off unless `HEARTBEAT_MASTER_KEY` is set. See [Heartbeats](HEARTBEAT.md).

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `HEARTBEAT_MASTER_KEY` | empty (off) | Fleet master key, 64 hex characters (secret) |
| `HEARTBEAT_API_TOKEN` | empty | Bearer token for the read-only API, 32+ characters (secret) |
| `HEARTBEAT_BROKER` / `HEARTBEAT_PORT` / `HEARTBEAT_TLS` | `broker.hivemq.com` / `8883` / `true` | Heartbeat broker (TLS, certificate verified) |
| `HEARTBEAT_STALE_SECONDS` | `35` | No heartbeat for this long: `silent` |
| `HEARTBEAT_KEEP_DAYS` | `30` | How long per-minute presence and events are kept |
| `HEARTBEAT_BEATS_HOURS` | `48` | How long every single heartbeat is kept (charts up to 1 day, CSV); `0` keeps none. About 0.35 MB per node per day (0.7 MB for 48 hours, measured) |
| `HEARTBEAT_MIN_SPACING` | `2` | Seconds a node must leave between heartbeats; faster ones are dropped as a flood |

Generate the secrets with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"      # HEARTBEAT_MASTER_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"  # HEARTBEAT_API_TOKEN
```

## Example `.env` behind HTTPS on a sub-path

```bash
SENSEHIVE_ADMIN_PASSWORD=<strong password>
SENSEHIVE_TRUST_PROXY=true
SENSEHIVE_COOKIE_SECURE=true
SENSEHIVE_COOKIE_SAMESITE=Strict
SENSEHIVE_COOKIE_PATH=/sensehive/
DEFAULT_BROKER_HOST=mqtt.internal
DEFAULT_TIMEZONE=UTC
```
