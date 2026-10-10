"""
Access-control decorators for Flask routes.

login_required: any authenticated user.
role_required(*roles): authenticated AND one of the given roles
(see config.ROLES for the four actor roles from Chapter 3's use case diagram).
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
