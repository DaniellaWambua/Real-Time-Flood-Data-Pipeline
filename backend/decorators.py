"""
Access-control decorators: login_required for any signed-in user, role_required(*roles)
for the given roles (config.ROLES).

The session cookie only says who signed in. Every request checks it against the account as it
is now (current_user), so logging out, deactivation, a role change, a new password or email and
a 2FA reset take effect at once, even for a copy of the cookie taken earlier.
"""

from functools import wraps

from flask import jsonify, session

import models


def current_user():
    """The signed-in account as it is in the database now, or None (and the session is cleared)
    when there is no session, the account is gone or deactivated, or the session was ended."""
    if "user_id" not in session:
        return None
    user = models.session_state(session["user_id"])
    if user is None or not user["is_active"] or user["session_version"] != session.get("sv"):
        session.clear()
        return None
    return user


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return jsonify({"error": "authentication required"}), 401
        return view_func(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"error": "authentication required"}), 401
            if user["role"] not in roles:
                return jsonify({"error": "insufficient permissions"}), 403
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
