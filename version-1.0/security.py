"""Login and request hardening for SenseHive.

- Passwords: salted, slow hashes (Werkzeug: scrypt or PBKDF2). Accounts from
  older versions (unsalted SHA-256) keep working and are upgraded on their
  next successful login.
- Retries: after SENSEHIVE_MAX_FAILED_LOGINS failures (5) for a user or from an
  address within SENSEHIVE_LOCK_MINUTES (15), sign-in is refused for that user
  or address until the window passes. The answer never says which part was
  wrong, and an unknown user costs the same time as a known one.
- CSRF: requests that change something are refused when the browser says they
  come from another site (Origin, Sec-Fetch-Site).
- Cookies: HttpOnly always; SameSite, Secure and Path set from the
  environment (SENSEHIVE_COOKIE_SAMESITE, _SECURE, _PATH).
- Behind a reverse proxy (SENSEHIVE_TRUST_PROXY=true), the client address comes
  from X-Real-IP, so limits apply per real client, not per proxy.
"""
import hashlib
import hmac
import os
import threading
import time
from datetime import timedelta

from werkzeug.security import check_password_hash, generate_password_hash

_DUMMY = None


def _flag(name, default=False):
    v = os.getenv(name)
    return default if v is None or not v.strip() else v.strip().lower() in ('1', 'true', 'yes', 'on')


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ passwords
def hash_password(password):
    return generate_password_hash(password)


def _is_legacy(stored):
    return isinstance(stored, str) and len(stored) == 64 and all(c in '0123456789abcdef' for c in stored)


def verify_password(stored, password):
    if not stored or password is None:
        return False
    if _is_legacy(stored):
        return hmac.compare_digest(stored, hashlib.sha256(password.encode()).hexdigest())
    try:
        return check_password_hash(stored, password)
    except (ValueError, TypeError):
        return False


def needs_rehash(stored):
    return _is_legacy(stored)


def burn_time(password):
    """Same work as a real check, for unknown users (no timing hint)."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = generate_password_hash(os.urandom(16).hex())
    check_password_hash(_DUMMY, password or '')


# ------------------------------------------------------------------ retries
class LoginLimiter:
    def __init__(self):
        self.max_failed = max(_int('SENSEHIVE_MAX_FAILED_LOGINS', 5), 1)
        self.window = max(_int('SENSEHIVE_LOCK_MINUTES', 15), 1) * 60
        self.failures = {}
        self.lock = threading.Lock()

    def _recent(self, key, now):
        times = [t for t in self.failures.get(key, []) if now - t < self.window]
        if times:
            self.failures[key] = times
        else:
            self.failures.pop(key, None)
        return times

    def blocked(self, username, ip, now=None):
        now = time.time() if now is None else now
        with self.lock:
            return any(len(self._recent(k, now)) >= self.max_failed for k in (('u', username), ('ip', ip)))

    def failed(self, username, ip, now=None):
        now = time.time() if now is None else now
        with self.lock:
            for k in (('u', username), ('ip', ip)):
                self.failures.setdefault(k, []).append(now)
                self._recent(k, now)

    def succeeded(self, username):
        with self.lock:
            self.failures.pop(('u', username), None)


def client_ip(request):
    if _flag('SENSEHIVE_TRUST_PROXY') and request.headers.get('X-Real-IP'):
        return request.headers['X-Real-IP'].strip()[:45]
    return request.remote_addr or ''


# ------------------------------------------------------------------ CSRF and cookies
UNSAFE = ('POST', 'PUT', 'PATCH', 'DELETE')


def cross_site(request):
    """True when the browser says this state-changing request comes from
    another site. Non-browser clients (no Origin, no Sec-Fetch-Site) pass."""
    if request.method not in UNSAFE:
        return False
    if request.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
        return True
    origin = request.headers.get('Origin')
    if origin and origin != 'null':
        host = origin.split('://', 1)[-1].split('/', 1)[0]
        forwarded = request.headers.get('X-Forwarded-Host') if _flag('SENSEHIVE_TRUST_PROXY') else None
        return host not in {request.host, forwarded}
    return False


def configure(app):
    samesite = (os.getenv('SENSEHIVE_COOKIE_SAMESITE') or 'Lax').strip().capitalize()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=samesite if samesite in ('Lax', 'Strict', 'None') else 'Lax',
        SESSION_COOKIE_SECURE=_flag('SENSEHIVE_COOKIE_SECURE'),
        SESSION_COOKIE_PATH=(os.getenv('SENSEHIVE_COOKIE_PATH') or '/').strip() or '/',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=max(_int('SENSEHIVE_SESSION_HOURS', 12), 1)),
    )
