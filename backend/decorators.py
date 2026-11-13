"""
Access-control decorators: login_required for any signed-in user, role_required(*roles)
for the given roles (config.ROLES).
"""

from functools import wraps

from flask import jsonify, session


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "authentication required"}), 401
        return view_func(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return jsonify({"error": "authentication required"}), 401
            if session.get("role") not in roles:
                return jsonify({"error": "insufficient permissions"}), 403
            return view_func(*args, **kwargs)

        return wrapped

    return decorator
