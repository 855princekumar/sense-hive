# Development and testing

## Layout

```
version-1.0/            the service (what Docker and pip ship)
  app.py                Flask app: pages, API, MQTT client, retention, SSE stream
  heartbeat.py          heartbeat receiver and its read-only API
  heartbeat_protocol.py shared protocol (same file in the agent and EdgeShell)
  security.py           password hashing, lockout, CSRF and cookie settings
  cli.py                the `sensehive` command (pip install)
  templates/            index.html, login.html, heartbeats.html (no inline scripts)
  static/               BUILT browser code, committed (see below)
frontend/               browser sources: dashboard.jsx, login.jsx, heartbeats.js, input.css
tools/
  build_frontend.mjs    builds frontend/ into version-1.0/static
  ui_test.py            browser UI test (Playwright)
  screenshots.py        README screenshots from the same seeded install
tests/                  pytest suites (unit, API, security, heartbeat, front-end, integration)
docs/                   this documentation; docs/adr/ for decisions
```

## Running locally

```bash
pip install -r version-1.0/requirements.txt pytest
DB_PATH=/tmp/sh.db python version-1.0/app.py
```

## Front end

The pages use React and Tailwind, **compiled ahead of time** and committed to
`version-1.0/static`, so Docker, pip and Home Assistant need no Node.js and the
browser loads nothing from a CDN ([ADR 0004](adr/0004-vendored-frontend-and-csp.md)).

```bash
npm ci            # exact versions from package-lock.json
npm run build     # frontend/ -> version-1.0/static (+ SHA256SUMS)
npm run check     # CI: rebuild in a temp dir, fail if static/ is out of date
```

Change a `.jsx`, `.js` or `input.css` file, run `npm run build`, and commit the
sources and `version-1.0/static` together.

### Theme

SenseHive uses EdgeShell's palette so the two look like one product
([ADR 0005](adr/0005-edgeshell-theme.md)). `tailwind.config.js` maps
Tailwind's colour names onto it:

| Role | Colour |
| ---- | ------ |
| Primary (`blue-600` / `700`) | `#1a56db` / `#1044b0` |
| Accent (`purple-*` mapped to sky) | `#0ea5e9` |
| Success (`green-500`) | `#059669` |
| Warning (`yellow-500`) | `#d97706` |
| Danger (`red-500`) | `#dc2626` |
| Text, borders, backgrounds | Tailwind grays |
| Font | Inter, JetBrains Mono for JSON |

Light is the default; the dark choice is kept in `localStorage`
(`sensehive-dark`) and also applies to the heartbeats page.

### Rules for browser code

- No inline `<script>` and no `eval`: the CSP refuses them.
- Relative URLs only (`fetch('api/..')`, not `'/api/..'`): SenseHive runs under
  sub-paths (Home Assistant ingress, `/sensehive/` behind EdgeShell).
- Boxes that hold user text get `min-w-0` and wrap (`break-all`,
  `overflow-wrap: anywhere`) so long topics and payloads stay inside.
- Test hooks: cards `.sh-card`, top bar `.sh-nav`, summary bar `.sh-bar`,
  dialogs `.sh-modal` (Escape closes them).

## Tests

| Suite | Command | What it covers |
| ----- | ------- | -------------- |
| Unit and API | `python -m pytest` | Topics, payloads, LWT, retention, export, settings, sign-in hardening, SQL safety, CSP headers, static files and checksums, heartbeat protocol vectors and receiver |
| Integration | `SENSEHIVE_TEST_BROKER=localhost:1883 python -m pytest` | The same plus end-to-end over a real Mosquitto broker |
| Browser UI | `python tools/ui_test.py` | See below |
| Lint | `ruff check .` | pyflakes, pycodestyle, bugbear, simplify, pylint errors (config in `pyproject.toml`) |
| Security | `bandit -r version-1.0 tools -ll`, `pip-audit -r version-1.0/requirements.txt` | No unreviewed medium/high finding; no dependency with a known vulnerability |
| Front-end build | `npm run check` | `version-1.0/static` matches the sources |

### Browser UI test

```bash
pip install playwright && python -m playwright install chromium
python tools/ui_test.py --out ui-report           # about 145 checks
python tools/ui_test.py --quick                   # no zoom levels
```

It starts SenseHive on a temporary database seeded with long topic names,
nested and array payloads, LWT states and heartbeat nodes in every state, then
in Chromium:

- loads the sign-in page, the dashboard, the heartbeats page and the settings
  and add-node dialogs on **phone, tablet, laptop and desktop**, at **67, 125,
  150 and 200 % zoom**, and in **light and dark**;
- fails when a page scrolls sideways, something sticks out of its card, dialog
  or bar, text spills out of its box, a short word breaks over two lines, a
  JavaScript error or **CSP violation** occurs;
- signs in (and is refused with a wrong password), filters by tag, sorts,
  groups by node, switches and remembers the theme, adds a topic, opens the
  heartbeats page and signs out, on desktop and phone.

Screenshots of failures go to `--out`. `--min-checks N` fails a run that
silently shrank.

### Screenshots

```bash
python tools/screenshots.py      # rewrites assets/*.png from the seeded test data
```

## CI

Every pull request and push to `main` runs (all required for merging):

| Job | Checks |
| --- | ------ |
| Tests (Python 3.9, 3.11, 3.12, 3.13; paho-mqtt 1.x) | pytest against a real Mosquitto broker |
| Lint and static checks | ruff, no em dashes in text |
| Security scans | Bandit, pip-audit |
| Front-end build | `npm ci` and `npm run check` |
| Browser UI | `tools/ui_test.py --min-checks 140` |
| pip package | wheel build, install in a clean venv, CLI smoke test |
| Docker image | build, no database in the image, health check, CSP header and static files served |
| CodeQL | Python and JavaScript |

Tags `vX.Y.Z` publish the multi-arch image, the Docker Hub description, the
PyPI package and a GitHub release (`cd.yml`).
