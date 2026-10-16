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

## Browser policy (CSP)

Every page is sent with:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none';
  form-action 'self'; frame-ancestors 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
X-Frame-Options: SAMEORIGIN
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
never in the repository. The image ships no database and no secrets.

## Checks on every change

CI runs CodeQL, Bandit, pip-audit, ruff, the regression tests, the browser UI
test (including CSP violations) and a front-end build check; Dependabot and
GitHub secret scanning are on. See [Development](DEVELOPMENT.md#ci).

## Reporting a problem

Please use GitHub's **private vulnerability reporting** (Security tab >
Report a vulnerability) rather than a public issue.
