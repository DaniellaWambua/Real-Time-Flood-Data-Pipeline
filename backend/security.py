"""
Request-level protections shared by the routes: a small rate limiter for the sign-in steps and the
check that every state-changing request is JSON.

The limiter counts in memory. That is exact for this deployment, which runs one Gunicorn worker
(deploy/app.Dockerfile); with several workers or servers it would need a shared store such as Redis.
"""
import threading
import time
from collections import deque
from functools import wraps

from flask import current_app, jsonify, request, session

_lock = threading.Lock()
_hits = {}  # "limit name:who" -> deque of attempt times
_MAX_KEYS = 20000  # past this, keys with no recent attempts are dropped, so the table cannot grow without end


def reset():
    """Forget every counted attempt (used by the tests)."""
    with _lock:
        _hits.clear()


def _prune(now):
    for key in [k for k, (window, times) in _hits.items() if not times or times[-1] <= now - window]:
        del _hits[key]


def _hit(key, count, seconds):
    """Count one attempt. Returns 0 if it is allowed, otherwise how many seconds until the next one is."""
    now = time.monotonic()
    with _lock:
        if len(_hits) > _MAX_KEYS:
            _prune(now)
        _, times = _hits.setdefault(key, (seconds, deque()))
        while times and times[0] <= now - seconds:
            times.popleft()
        if len(times) >= count:
            return max(1, int(times[0] + seconds - now) + 1)
        times.append(now)
        return 0


def client_ip():
    return request.remote_addr or "unknown"


def login_name():
    """The username or email a /login attempt is for, so one account cannot be guessed at from many addresses."""
    name = ((request.get_json(silent=True) or {}).get("username") or "").strip().lower()
    return name[:254] or None


def pending_user():
    """The account part-way through sign-in, for limits on guessing its authenticator code."""
    return session.get("pending_user_id") or session.get("setup_user_id") or session.get("user_id")


def signed_in_user():
    return session.get("user_id")


def limit(name, count, seconds, key=client_ip):
    """Allow at most count requests per seconds for each value of key(); more get HTTP 429."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if current_app.config.get("RATE_LIMITS", True):
                who = key()
                if who is not None:
                    wait = _hit(f"{name}:{who}", count, seconds)
                    if wait:
                        minutes = max(1, round(wait / 60))
                        resp = jsonify({"error": f"too many attempts. Wait about {minutes} minute"
                                                 f"{'s' if minutes != 1 else ''} and try again."})
                        resp.headers["Retry-After"] = str(wait)
                        return resp, 429
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


def failures_wait(name, who, count, seconds):
    """Seconds until another attempt is allowed once count failures were recorded under name for who
    within seconds, or 0. Unlike limit(), only failures count (see record_failure)."""
    now = time.monotonic()
    with _lock:
        entry = _hits.get(f"{name}:{who}")
        if entry is None:
            return 0
        _, times = entry
        while times and times[0] <= now - seconds:
            times.popleft()
        return max(1, int(times[0] + seconds - now) + 1) if len(times) >= count else 0


def record_failure(name, who, seconds):
    now = time.monotonic()
    with _lock:
        _hits.setdefault(f"{name}:{who}", (seconds, deque()))[1].append(now)


STATE_CHANGING = ("POST", "PUT", "PATCH", "DELETE")


def require_json():
    """Refuse a state-changing request that is not JSON. A page on another site can submit a form
    (and the browser would attach the cookie), but it cannot send application/json without a CORS
    preflight, which only the dashboard's own origin passes. Together with the SameSite cookie this
    stops cross-site request forgery."""
    if request.method in STATE_CHANGING and not request.is_json:
        return jsonify({"error": "requests that change something must be sent as JSON"}), 415
    return None
