# Security

## Sign-in

- **Passwords** are stored as salted, slow hashes (Werkzeug scrypt or
  PBKDF2). Accounts from before 1.3 (unsalted SHA-256) still sign in and are
  rehashed on that sign-in.
- **Lockout:** after `SENSEHIVE_MAX_FAILED_LOGINS` (5) failures for a user or
  from an address within `SENSEHIVE_LOCK_MINUTES` (15), sign-in is refused for
  that user or address until the window passes. The answer never says which
  part was wrong, and an unknown user takes as long as a known one.
- **Sessions:** a new session on every sign-in (no fixation), HttpOnly cookie,
  `SameSite`, `Secure` and `Path` from the environment, lifetime
  `SENSEHIVE_SESSION_HOURS` (12).
- **No default password on screen:** the sign-in page does not show
  credentials. Set `SENSEHIVE_ADMIN_PASSWORD` for the first start, or change
  `admin123` at once.

## Requests

- **Cross-site requests** that change anything are refused when the browser
  marks them as coming from another site (`Origin`, `Sec-Fetch-Site`).
- **SQL:** values are always bound parameters. A topic's table name is the only
  identifier built from input; it is always quoted with any `"` doubled, and
  topics with quotes or control characters are refused when added.
- **Everything except** `/login`, `/api/login`, `/api/health` and
  `/api/status` needs a signed-in session (the heartbeat API also takes its
  bearer token).

## Untrusted input

Everything from MQTT and from the network is treated as hostile:

| Input | Protection |
| ----- | ---------- |
| MQTT payloads | Over `MQTT_MAX_PAYLOAD_BYTES` (64 KB) dropped and counted; deeply nested JSON kept as text instead of crashing the parser |
| Topic names and payloads in the log | Line breaks and control characters removed, length capped: no forged log lines |
| Request bodies | Over 1 MB refused before they are read (413) |
| Numbers in queries | Only finite numbers accepted (`nan`, `inf` fall back to defaults) |
| Live-update streams | At most `SENSEHIVE_MAX_STREAMS` (50) at once; more get 503 |
| Heartbeats | Verified, fresh and in order (see [ADR 0002](adr/0002-heartbeat-receiver.md)); a node faster than `HEARTBEAT_MIN_SPACING` is dropped as a flood |
| API tokens | 20 wrong tokens from one address in 15 minutes lock that address out for a while |
| Health endpoint | The exact version is shown only to signed-in users and token holders (no fingerprinting) |

## Exports

CSV files (topic export and heartbeat export) escape any cell that starts with
`=`, `+`, `-`, `@`, a tab or a carriage return with a leading `'`, so opening a
file in a spreadsheet can never run a formula from a payload or a node name.
Plain numbers such as `-12.5` stay numbers.

## Browser policy (CSP)

Every page is sent with:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none';
  form-action 'self'; frame-ancestors 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
X-Frame-Options: SAMEORIGIN
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
```

All scripts come from SenseHive itself (`version-1.0/static`, built ahead of
time with fixed versions, see [ADR 0004](adr/0004-vendored-frontend-and-csp.md)).
No CDN is contacted, there is no inline script and no `eval`, so a compromised
third-party host cannot run code in SenseHive, or in a site that serves it on
the same origin. The browser UI test fails on any CSP violation.

## Behind a reverse proxy

- Set `SENSEHIVE_TRUST_PROXY=true` only when the proxy sets `X-Real-IP`;
  otherwise clients could choose their own address for the lockout.
- Behind HTTPS: `SENSEHIVE_COOKIE_SECURE=true`,
  `SENSEHIVE_COOKIE_SAMESITE=Strict`, and `SENSEHIVE_COOKIE_PATH` set to the
  sub-path if it shares a domain with other apps.
- Do not expose port 5000 directly to the internet; put SenseHive behind a
  proxy with TLS, or keep it on a private network.

## Secrets

`SENSEHIVE_ADMIN_PASSWORD`, `DEFAULT_BROKER_PASSWORD`, `HEARTBEAT_MASTER_KEY`,
`HEARTBEAT_API_TOKEN` and `SECRET_KEY` belong in `.env` or a secret store,
never in the repository. The image ships no database and no secrets. A session
secret generated on first start is written readable by its owner only (0600).

## Checks on every change

CI runs CodeQL, Bandit, pip-audit, ruff, the regression tests, the browser UI
test (including CSP violations) and a front-end build check; Dependabot and
GitHub secret scanning are on. See [Development](DEVELOPMENT.md#ci).

## Build-time dependencies

`node_modules` is only used to build `version-1.0/static`; none of it ships in
the image, the pip package or the Home Assistant add-on. Advisories against
these tools (for example in Tailwind 3's file watcher, which has no patched
release) cannot be reached from a running SenseHive. They are still tracked by
Dependabot and fixed when a compatible release exists, with the build checked
to produce identical files.

## Reporting a problem

Please use GitHub's **private vulnerability reporting** (Security tab >
Report a vulnerability) rather than a public issue.
