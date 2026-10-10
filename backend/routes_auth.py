"""
Authentication routes: login, logout, and "who am I" using Flask's built-in
signed-cookie session (matches the proposal's "session management" wording
in section 3.6.2/3.6.6 rather than a token-based scheme like JWT).
"""

from flask import Blueprint, jsonify, request, session

import models

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = models.get_user_by_username(username)
    if user is None or not models.verify_password(user, password):
        return jsonify({"error": "invalid username or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    return jsonify(
        {"id": user["id"], "username": user["username"], "role": user["role"]}
    )


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "logged out"})


@auth_bp.route("/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401
    return jsonify(
        {
            "id": session["user_id"],
            "username": session["username"],
            "role": session["role"],
        }
    )
