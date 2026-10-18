# Changelog

## 1.8.0 (2026-10-18)

**Add a heartbeat node without EdgeShell**
- **Heartbeats, Add node:** a name, then a one-line join token. On the node:
  `git clone` the [heartbeat agent](https://github.com/855princekumar/mqtt-heartbeat-service),
  `sudo python3 setup.py`, paste the token. The agent is installed as a
  hardened systemd service and the node appears by itself. SenseHive never
  connects to the node.
- The token holds only that node's keys and the broker, never the fleet master
  key, with a checksum that refuses a cut or changed paste.
- `HEARTBEAT_MASTER_KEY=auto`: a random fleet key made once and kept next to
  the database (owner only), so every SenseHive is its own fleet.
- `HEARTBEAT_NODE_BROKER`: the broker address written into tokens when nodes
  reach it by another name than SenseHive does.
- The fleet id (a hash, 12 hex) shows in SenseHive and on the node
  (`setup.py --status`), so anyone can check a node belongs to this SenseHive.
- **Many nodes:** **Add node, Many nodes (CSV)**: names or a prefix and a
  range, up to 500 tokens at a time, one per node, as a CSV for the agent's
  bulk SSH tool (`tools/bulk_setup.py`, agent 1.2.0).
- `HEARTBEAT_BROKER_USERNAME` / `HEARTBEAT_BROKER_PASSWORD`: SenseHive's login
  on the heartbeat broker (nodes have theirs since agent 1.2.0).

**Isolation, tested**
- Two SenseHives on one broker never see each other's nodes: different topics,
  no decryption, the same node names kept apart, a token cannot be edited to
  speak for another node.

**Validate without hardware**
- New guide [Validate without hardware](docs/VALIDATE-WITHOUT-HARDWARE.md) with
  the numbers measured in the simulations.
- New **Devices** workflow: on every pull request, the PowerPulse firmware's
  messages end to end and the heartbeat agent installed from a join token on a
  systemd node beside a second SenseHive; on `main` and weekly, the real
  PowerPulse firmware on a simulated ESP32 (Wokwi).
- README: **The SenseHive Family**, the heartbeat agent and PowerPulse.

## 1.7.0 (2026-10-18)

**Secure topics** ([guide](docs/SECURE-TOPICS.md), ADR 0009)
- Topics encrypted and signed per topic (AES-256-CTR and HMAC-SHA256, protocol
  sst1) with keys SenseHive issues. A device publishes under
  `sensehive/secure/...` and its topic appears by itself; nobody without the
  key can read, change, move or replay its data.
- Generate 1 to 100 keys at a time with a label, shown once, CSV download. A
  key waits 24 hours for its first message, is then bound to that topic for
  good, and otherwise expires. Key ids are never issued again. Show a key again
  with your password; revoke it at once.
- A secure device can name its status (last will) topic in a signed message
  (`sensehive_lwt`) for online and offline.
- Topic logs has two cards, **Open topics** and **Secure topics**, each with an
  (i) guide; `?topics=secure` opens the secure view.
- Device code tested in CI: Python, MicroPython, Node.js and Node-RED, and an
  ESP32 Arduino sketch.
- `SENSEHIVE_SECURE_TOPICS`, `SENSEHIVE_SECURE_ROOT`.

**Heartbeats**
- Recycle bin: move nodes that are gone for good out of the list and the read
  API; heartbeats from a binned node are verified but not stored, and the bin
  shows when one comes back. Restore, delete for good, or deleted after
  `HEARTBEAT_BIN_DAYS` (30).

**Topics**
- `on` and `off` count as online and offline in status payloads.

**Documentation**
- Minimum system requirements, secure topics, recycle bin; new screenshots.

## 1.6.1 (2026-10-16)

**Fixed**
- Heartbeat history always shows an outage that is still going on. An offline
  or silent node shows how long it has been down since its last heartbeat (and
  when its last will arrived), also when it went down before the chosen range
  or before heartbeat history was kept (1.5.0), and on the 7 and 30 day views.
  Before, such a node showed no break at all.
- With fewer than two heartbeats in the range, breaks are measured against the
  agent's 10 s interval instead of not at all.
- A last will inside an outage no longer splits it into two breaks; the break
  shows when the last will arrived.
- A break that began before the range is drawn from the chart's left edge.

## 1.6.0 (2026-10-16)

**Interface**
- An (i) button on the Topic logs and Heartbeats cards opens a guide: what the
  view is for, how to use it step by step, and tips. The Heartbeats guide links
  to the heartbeat agent's repository in a new tab.
- Filter by status: topics by online (active), offline (inactive) or no last
  will; heartbeat nodes by online, offline or silent, with the count of each.

**Documentation**
- [Deploying securely](docs/SECURITY.md#deploying-securely) with a diagram:
  DNS, firewall, TLS proxy, SenseHive's port on loopback only, an nginx example
  and checks from outside.
- The setup guide no longer claims the container runs as a non-root user (it
  does not yet); keep the port private and the data volume on the host.

## 1.5.0 (2026-10-16)

**Heartbeat history**
- Every verified heartbeat is kept (`HEARTBEAT_BEATS_HOURS`, 48): per-node
  charts for 1 minute, 1 hour and 1 day (gaps between heartbeats, breaks, last
  wills) and 7 and 30 days (uptime per hour), with uptime, longest break,
  breaks list and delivery delay.
- CSV export for one node, the selected nodes or all: every heartbeat, online
  minutes or status changes. New API: `/api/heartbeat/history`,
  `/api/heartbeat/export.csv`.

**Interface**
- Two cards at the top of the dashboard, Topic logs and Heartbeats, replace the
  Heartbeats button; switching fades smoothly (opacity and transform only, so it
  runs at the screen's refresh rate; reduced motion respected).
- Every dialog fits the visible screen at any size and zoom: fixed header and
  buttons, scrolling middle. Settings text readable in the light theme.

**Security** (strict review, [ADR 0008](docs/adr/0008-hostile-input.md))
- MQTT payloads over 64 KB dropped; deeply nested JSON no longer crashes the
  handler; no forged log lines.
- A node sending heartbeats faster than every 2 s is dropped as a flood.
- 20 wrong API tokens from one address lock it out for a while.
- CSV exports escape spreadsheet formulas (numbers kept).
- Request bodies over 1 MB refused; live streams capped; version hidden from
  anonymous callers; `Permissions-Policy`, `Cross-Origin-Opener-Policy` and
  `Cross-Origin-Resource-Policy` headers; session secret file 0600.
- CI actions pinned to commit SHAs.

**Quality**
- The browser UI test now checks that every dialog fits the screen at every
  size and zoom, the heartbeat view, history charts for each period, and real
  CSV downloads.

## 1.4.2 (2026-10-16)

**Security**
- Values from requests are made safe before they reach the log (no line breaks
  or control characters), so a signed-in user cannot forge log entries
  (CodeQL `py/log-injection`).

## 1.4.1 (2026-10-16)

**Security**
- A failed broker test or CSV export no longer sends exception text to the
  browser: fixed messages for users, details in the server log (CodeQL
  `py/stack-trace-exposure`).
- Build tools: esbuild 0.28.1 (GHSA-67mh-4wv8-2f99) and postcss-selector-parser
  7.1.6 under Tailwind 3 (GHSA-rj75-hqrm-r3gf), with byte-identical built files.
  Both are build-time only; nothing from `node_modules` ships.
- Dependabot watches the npm build tools; Tailwind major versions are upgraded
  on purpose, not automatically.

## 1.4.0 (2026-10-16)

**Interface**
- EdgeShell's theme: same colours, font, sign-in card and top bar; light by
  default, dark remembered per browser and shared with the heartbeats page.
- Top bar wraps on phones (icon buttons), new **Heartbeats** link, cards no
  longer stretch to the tallest card in a row, theme-aware borders and tags,
  Escape closes dialogs, dialogs fit at every zoom level.
- The sign-in page no longer shows the default password.

**Security**
- Browser code built ahead of time and served by SenseHive (no CDN, no
  in-browser compiler); strict Content Security Policy (`script-src 'self'`, no
  `eval`), `nosniff`, `same-origin` referrer, `SAMEORIGIN` framing.
- Topic table names quoted with `"` doubled; topics with double quotes, control
  characters or over 512 characters are refused (fixes an SQL injection open to
  signed-in users).

**Quality**
- Browser UI test (about 145 checks): phone to desktop, 67 to 200 % zoom, light
  and dark, CSP violations, main interactions.
- ruff, Bandit and pip-audit in CI; front-end build check; no-em-dash check.
- Full documentation in `docs/` with ADRs; README screenshots generated from
  seeded test data.

## 1.3.0 (2026-10-16)
- Sign-in hardening: salted slow hashes (old ones upgraded), lockout per user
  and address, new session on sign-in, cross-site changes refused, cookie flags
  from the environment, first admin password from the environment.

## 1.2.0 (2026-10-15)
- Heartbeat receiver: encrypted, authenticated heartbeats and last wills from
  edge nodes over a public broker, `/heartbeats` page, read-only API.

## 1.1.0 (2026-10-13)
- SQLite WAL mode and retention; topic stats, tags, node grouping and LWT
  status; payload wrapping; wildcard topics; multi-tab live updates; pip CLI;
  Home Assistant add-on; regression suite and CI/CD; multi-arch image.

## 1.0.0 (2026-03-18)
- First public release: MQTT topic logging to SQLite, live dashboard, history,
  CSV export.
