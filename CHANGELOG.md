# Changelog

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
