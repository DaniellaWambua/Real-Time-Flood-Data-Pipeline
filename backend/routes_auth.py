"""
Authentication routes using Flask's signed-cookie session.

Every account signs in with two factors. /login checks the password but never opens a full session:
the account then gives its authenticator code (/login/verify-totp), or sets one up first
(/totp/setup, /totp/enable). POST /login/google replaces the password step with a Google ID token
matched to an existing account's email; there is no public registration.
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


def _second_step(user, detail):
    """Every account signs in with two factors. After the first (password, Google or a
    set-password link): a code if 2FA is set up, otherwise setting 2FA up now. No full
    session exists until that second step succeeds."""
    session.clear()
    if user.get("totp_enabled"):
        session["pending_user_id"] = user["id"]
        models.log_event(user["username"], "login_password_ok_awaiting_totp", detail)
        return jsonify({"requires_totp": True})
    session["setup_user_id"] = user["id"]
    models.log_event(user["username"], "login_password_ok_awaiting_2fa_setup", detail)
    return jsonify({"requires_totp_setup": True})


def _sign_in(user, detail):
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    models.log_event(user["username"], "login_success", detail)
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()  # a username or an email address
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = models.get_user_by_login(username)
    if user is None or not models.verify_password(user, password):
        # Logged under the attempted name, so repeated failures show in the activity log.
        models.log_event(username, "login_failure", "invalid username or password")
        return jsonify({"error": "invalid username or password"}), 401

    if not user.get("is_active", True):
        models.log_event(username, "login_failure", "account is deactivated")
        return jsonify({"error": "this account has been deactivated"}), 403

    return _second_step(user, None)


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

    return jsonify(_sign_in(user, "via 2FA"))


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
        # Generic on purpose, so it does not reveal which emails have accounts.
        models.log_event(email, "login_failure", "no account linked to this Google email")
        return jsonify({"error": "no account is linked to this Google account. Ask an administrator to add it."}), 403

    if not user.get("password_hash"):
        models.log_event(user["username"], "login_failure", "account not activated yet")
        return jsonify({"error": "activate your account from your invite email first"}), 403

    if not user.get("is_active", True):
        models.log_event(user["username"], "login_failure", "account is deactivated")
        return jsonify({"error": "this account has been deactivated"}), 403

    return _second_step(user, "via Google")


@auth_bp.route("/account/link/<code>", methods=["GET"])
def account_link(code):
    """What the set-password page needs to show for an invite or reset link."""
    link = models.find_link(code)
    if link is None or not link["is_active"]:
        return jsonify({"error": "this link is no longer valid. Ask your administrator for a new one."}), 404
    return jsonify({
        "purpose": link["purpose"],
        "username": link["username"],
        "full_name": link["full_name"],
        "email": link["email"],
        "expires_at": link["expires_at"].isoformat(),
    })


@auth_bp.route("/account/link/<code>", methods=["POST"])
def use_account_link(code):
    """Set the password from an invite or reset link (once), then go on to the second
    sign-in step: entering a code, or setting up 2FA for a new account."""
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400
    if len(password) > 128:
        return jsonify({"error": "password must be at most 128 characters"}), 400

    link = models.find_link(code)
    if link is None or not link["is_active"]:
        return jsonify({"error": "this link is no longer valid. Ask your administrator for a new one."}), 404
    if not models.set_password_with_link(link["link_id"], link["user_id"], password):
        return jsonify({"error": "this link has already been used"}), 409

    action = "user_activated" if link["purpose"] == "invite" else "password_reset_completed"
    models.log_event(link["username"], action, None)

    return _second_step(models.get_user_by_id(link["user_id"]), "after setting password")


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


def _enrolling_user():
    """The signed-in user, or the person part-way through sign-in who must set up 2FA."""
    user_id = session.get("user_id") or session.get("setup_user_id")
    return models.get_user_by_id(user_id) if user_id else None


@auth_bp.route("/totp/setup", methods=["POST"])
def totp_setup():
    """Make a new TOTP secret and return it as a QR code plus the key for manual entry.
    2FA stays off until /totp/enable confirms a code from it, so an abandoned setup never
    locks anyone out."""
    user = _enrolling_user()
    if user is None:
        return jsonify({"error": "not logged in"}), 401

    secret = pyotp.random_base32()
    models.set_totp_secret(user["id"], secret)

    uri = pyotp.TOTP(secret).provisioning_uri(name=user["username"], issuer_name=TOTP_ISSUER)
    qr_image = qrcode.make(uri)
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return jsonify({"secret": secret, "qr_code_png_base64": qr_base64})


@auth_bp.route("/totp/enable", methods=["POST"])
def totp_enable():
    """Confirm a code from the secret /totp/setup stored and switch 2FA on. For someone
    part-way through sign-in, this is the second step, so it also signs them in."""
    user = _enrolling_user()
    if user is None:
        return jsonify({"error": "not logged in"}), 401

    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400
    if not user.get("totp_secret"):
        return jsonify({"error": "call /totp/setup first"}), 400
    if not pyotp.TOTP(user["totp_secret"]).verify(code, valid_window=1):
        return jsonify({"error": "invalid code"}), 401

    models.enable_totp(user["id"])
    models.log_event(user["username"], "totp_enabled", None)
    if "setup_user_id" in session:
        return jsonify({**_sign_in(user, "after setting up 2FA"), "totp_enabled": True})
    return jsonify({"totp_enabled": True})
