"""
Authentication routes: login, logout, and "who am I" using Flask's built-in
signed-cookie session (matches the proposal's "session management" wording
in section 3.6.2/3.6.6 rather than a token-based scheme like JWT).

Login is a two-step flow for an account with 2FA enabled (proposal's
"extra mile" security requirement, TOTP-based so it works with no
internet at demo time: /login checks the password and, if the account
has 2FA on, stops short of a full session and asks for a 6-digit code;
/login/verify-totp checks that code and only then sets the full,
logged-in session. An account with no 2FA enabled still logs in in one
step, exactly as before.

POST /login/google is a second, parallel way to clear the password
step: the frontend hands it a Google-issued ID token instead of a
username/password pair, this verifies that token against Google (so it
needs internet, unlike the rest of this system) and looks up the
verified email against an already-provisioned account (models.
get_user_by_email). There is still no public registration anywhere:
an email with no matching account is refused outright, and a matching
account with 2FA enabled still has to clear /login/verify-totp exactly
as a password login would, same session state, same route.
"""

import base64
import io

import pyotp
import qrcode
from flask import Blueprint, jsonify, request, session
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

import config
import models

auth_bp = Blueprint("auth", __name__)

TOTP_ISSUER = "Flood Early Warning System"
_google_request = google_requests.Request()


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = models.get_user_by_username(username)
    if user is None or not models.verify_password(user, password):
        # Logged under the attempted username even when it doesn't match
        # a real account, so a run of failed logins against one name is
        # visible on the System Administration screen's log panel.
        models.log_event(username, "login_failure", "invalid username or password")
        return jsonify({"error": "invalid username or password"}), 401

    if not user.get("is_active", True):
        models.log_event(username, "login_failure", "account is deactivated")
        return jsonify({"error": "this account has been deactivated"}), 403

    if user.get("totp_enabled"):
        # Password is correct, but the session stays unauthenticated
        # until verify_totp succeeds below: only a short-lived marker
        # is set, not user_id/username/role.
        session["pending_user_id"] = user["id"]
        models.log_event(username, "login_password_ok_awaiting_totp", None)
        return jsonify({"requires_totp": True})

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    models.log_event(username, "login_success", None)

    return jsonify(
        {"id": user["id"], "username": user["username"], "role": user["role"]}
    )


@auth_bp.route("/login/verify-totp", methods=["POST"])
def verify_totp():
    if "pending_user_id" not in session:
        return jsonify({"error": "no login in progress"}), 400

    data = request.get_json(silent=True) or {}
    code = data.get("code")
    if not code:
        return jsonify({"error": "code is required"}), 400

    user = models.get_user_by_id(session["pending_user_id"])
    if user is None or not user.get("totp_secret"):
        session.pop("pending_user_id", None)
        return jsonify({"error": "no login in progress"}), 400

    totp = pyotp.TOTP(user["totp_secret"])
    if not totp.verify(code, valid_window=1):
        models.log_event(user["username"], "login_failure", "invalid 2FA code")
        return jsonify({"error": "invalid code"}), 401

    session.pop("pending_user_id", None)
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    models.log_event(user["username"], "login_success", "via 2FA")

    return jsonify(
        {"id": user["id"], "username": user["username"], "role": user["role"]}
    )


@auth_bp.route("/login/google", methods=["POST"])
def login_google():
    if not config.GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google sign-in is not configured on this server"}), 503

    data = request.get_json(silent=True) or {}
    credential = data.get("credential")
    if not credential:
        return jsonify({"error": "credential is required"}), 400

    try:
        idinfo = google_id_token.verify_oauth2_token(
            credential, _google_request, config.GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        return jsonify({"error": f"invalid Google credential: {exc}"}), 401

    if not idinfo.get("email_verified"):
        return jsonify({"error": "Google account email is not verified"}), 401

    email = idinfo["email"]
    user = models.get_user_by_email(email)
    if user is None:
        # Deliberately generic: this is the one guardrail keeping Google
        # sign-in from becoming public self-registration, so it must not
        # leak whether any OTHER email is already linked.
        models.log_event(email, "login_failure", "no account linked to this Google email")
        return jsonify({"error": "no account is linked to this Google account. Ask an administrator to add it."}), 403

    if not user.get("is_active", True):
        models.log_event(user["username"], "login_failure", "account is deactivated")
        return jsonify({"error": "this account has been deactivated"}), 403

    if user.get("totp_enabled"):
        session["pending_user_id"] = user["id"]
        models.log_event(user["username"], "login_password_ok_awaiting_totp", "via Google")
        return jsonify({"requires_totp": True})

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]

    models.log_event(user["username"], "login_success", "via Google")

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


@auth_bp.route("/totp/setup", methods=["POST"])
def totp_setup():
    """Generate a new TOTP secret for the signed-in user and return it as
    a scannable QR code plus the raw key for manual entry. The secret is
    stored but 2FA stays off (totp_enabled stays false) until /totp/enable
    confirms the user can actually produce a valid code from it, so a
    setup attempt that's abandoned part-way never locks anyone out."""
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    secret = pyotp.random_base32()
    models.set_totp_secret(session["user_id"], secret)

    uri = pyotp.TOTP(secret).provisioning_uri(
        name=session["username"], issuer_name=TOTP_ISSUER
    )
    qr_image = qrcode.make(uri)
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return jsonify({"secret": secret, "qr_code_png_base64": qr_base64})


@auth_bp.route("/totp/enable", methods=["POST"])
def totp_enable():
    """Confirm the signed-in user can generate a valid code from the
    secret /totp/setup just stored, then switch 2FA on for their account."""
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    data = request.get_json(silent=True) or {}
    code = data.get("code")
    if not code:
        return jsonify({"error": "code is required"}), 400

    user = models.get_user_by_id(session["user_id"])
    if user is None or not user.get("totp_secret"):
        return jsonify({"error": "call /totp/setup first"}), 400

    totp = pyotp.TOTP(user["totp_secret"])
    if not totp.verify(code, valid_window=1):
        return jsonify({"error": "invalid code"}), 401

    models.enable_totp(session["user_id"])
    models.log_event(session["username"], "totp_enabled", None)

    return jsonify({"totp_enabled": True})


@auth_bp.route("/totp/disable", methods=["POST"])
def totp_disable():
    """Turn 2FA back off for the signed-in user, re-confirming their
    password first so a hijacked but still-open session can't disable it
    on its own."""
    if "user_id" not in session:
        return jsonify({"error": "not logged in"}), 401

    data = request.get_json(silent=True) or {}
    password = data.get("password")
    if not password:
        return jsonify({"error": "password is required"}), 400

    user = models.get_user_by_id(session["user_id"])
    if user is None or not models.verify_password(user, password):
        return jsonify({"error": "incorrect password"}), 401

    models.disable_totp(session["user_id"])
    models.log_event(session["username"], "totp_disabled", None)

    return jsonify({"totp_enabled": False})
