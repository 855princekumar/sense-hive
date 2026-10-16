# 0003: Sign-in hardening

- **Status:** Accepted (1.3; SQL identifier safety and no default password on screen added in 1.4)
- **Date:** 2026-10-16

## Context

SenseHive started with one user, an unsalted SHA-256 password hash and no limit
on guesses. It is now also served under EdgeShell's domain, so its cookies and
forms share a site with a fleet manager.

## Decision

- Salted, slow hashes (Werkzeug scrypt/PBKDF2); legacy hashes verified once and
  upgraded on that sign-in.
- Lockout per user **and** per client address after
  `SENSEHIVE_MAX_FAILED_LOGINS` failures in `SENSEHIVE_LOCK_MINUTES`; the client
  address from `X-Real-IP` only when `SENSEHIVE_TRUST_PROXY` is set.
- Uniform answers and timing for wrong users and wrong passwords.
- A new session on every sign-in; HttpOnly cookies; SameSite, Secure and Path
  configurable (Strict, Secure and `/sensehive/` behind EdgeShell).
- Requests that change something are refused when the browser says they come
  from another site (`Origin`, `Sec-Fetch-Site`).
- First admin password from `SENSEHIVE_ADMIN_PASSWORD`; the sign-in page never
  shows a default password (1.4).
- Topic table names quoted with `"` doubled; topics with quotes or control
  characters refused (1.4).

## Consequences

- Online guessing is slow and visible; offline cracking of a stolen database is
  expensive.
- Existing installs keep working with no migration step.
- Behind a proxy, `SENSEHIVE_TRUST_PROXY` must be set correctly, or the lockout
  counts the proxy (too strict) or trusts clients (too loose); documented in
  [Security](../SECURITY.md).
