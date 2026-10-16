# 0004: Browser code built ahead of time, served locally, strict CSP

- **Status:** Accepted (1.4)
- **Date:** 2026-10-16

## Context

Until 1.3 the pages loaded React, ReactDOM, Babel and the Tailwind CDN script
from public CDNs at run time, unpinned, and compiled JSX in the browser. That
meant:

- a compromised or changed CDN file would run with full access to SenseHive, and
  to EdgeShell too when SenseHive is served on its origin;
- no Content Security Policy was possible (Babel needs `eval`, the scripts were
  inline);
- the pages did not work offline or on networks that block CDNs, and were slow
  on small devices (in-browser compilation, the whole Tailwind runtime).

## Decision

- JSX and CSS are compiled **ahead of time** (esbuild, Tailwind CLI) from
  `frontend/` into `version-1.0/static/`, with exact versions from
  `package-lock.json`. React and ReactDOM production files are copied from the
  same lock. The output is **committed**, with a `SHA256SUMS` file.
- CI rebuilds and fails if the committed files differ from what the sources
  produce (`npm run check`), so what ships is exactly what the sources say.
- Every response carries a CSP with `script-src 'self'` and no `unsafe-eval`
  or inline script, plus `nosniff`, `same-origin` referrer and `SAMEORIGIN`
  framing. Inline styles stay allowed (`style-src 'unsafe-inline'`): React sets
  style attributes, and styles cannot run code.
- No page references another host; tests enforce it.

## Consequences

- No third party can run code in SenseHive; the browser blocks anything that is
  not SenseHive's own file, and the UI test fails on any CSP violation.
- Docker, pip and Home Assistant need no Node.js; Node is a developer tool only.
- Changing the UI needs `npm run build` and committing `static/`; CI catches a
  forgotten build.
- Pages load faster: minified scripts and CSS with only the classes in use.
