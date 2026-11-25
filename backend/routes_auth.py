"""
Authentication routes using Flask's signed-cookie session.

Every account signs in with two factors. /login checks the password but never opens a full session:
the account then gives its authenticator code (/login/verify-totp), or sets one up first
(/totp/setup, /totp/enable). POST /login/google replaces the password step with a Google ID token
matched to an existing account's email; there is no public registration.
"""

import base64
import datetime
import hmac
import io
import time

import pyotp
import qrcode
from flask import Blueprint, jsonify, request, session
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

import config
import models
import password_policy
from decorators import current_user, login_required
from security import limit, login_name, pending_user, signed_in_user

auth_bp = Blueprint("auth", __name__)

TOTP_ISSUER = "Flood Early Warning System"
_google_request = google_requests.Request()


def _second_step(user, detail):
    """Every account signs in with two factors. After the first (password, Google or a
    set-password link): a code if 2FA is set up, otherwise setting 2FA up now. No full
    session exists until that second step succeeds."""
    session.clear()
    session["step_started"] = int(time.time())
    if user.get("totp_enabled"):
        session["pending_user_id"] = user["id"]
        models.log_event(user["username"], "login_password_ok_awaiting_totp", detail)
        return jsonify({"requires_totp": True})
    session["setup_user_id"] = user["id"]
    models.log_event(user["username"], "login_password_ok_awaiting_2fa_setup", detail)
    return jsonify({"requires_totp_setup": True})


def _in_progress(key):
    """The user id stored under key by _second_step, or None once the sign-in step has timed out
    (config.SIGN_IN_STEP_SECONDS), so a half-finished sign-in cannot be used for long."""
    if key not in session:
        return None
    if time.time() - session.get("step_started", 0) > config.SIGN_IN_STEP_SECONDS:
        session.clear()
        return None
    return session[key]


def _code_ok(user, code):
    """Whether code is the account's current authenticator code (one 30-second step either side,
    for clock drift) and has not been used before. Using it records its step, so the same code,
    or an older one, is refused afterwards."""
    code = (code or "").strip()
    secret = user.get("totp_secret")
    if not secret or len(code) != 6 or not code.isdigit():
        return False
    totp = pyotp.TOTP(secret)
    now = totp.timecode(datetime.datetime.now())
    for step in (now - 1, now, now + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            return models.claim_totp_step(user["id"], step)
    return False


def _sign_in(user, detail):
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["sv"] = user.get("session_version")
    models.log_event(user["username"], "login_success", detail)
    return {"id": user["id"], "username": user["username"], "role": user["role"]}


@auth_bp.route("/login", methods=["POST"])
@limit("login-ip", 20, 60)
@limit("login-ip-hour", 100, 3600)
@limit("login-account", 10, 900, key=login_name)
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
@limit("code-ip", 20, 60)
@limit("code-account", 5, 300, key=pending_user)
@limit("code-account-hour", 20, 3600, key=pending_user)
def verify_totp():
    pending_id = _in_progress("pending_user_id")
    if pending_id is None:
        return jsonify({"error": "this sign-in has timed out. Enter your password again."}), 400

    data = request.get_json(silent=True) or {}
    code = data.get("code")
    if not code:
        return jsonify({"error": "code is required"}), 400

    user = models.get_user_by_id(pending_id)
    if user is None or not user.get("totp_secret") or not user.get("is_active", True):
        session.clear()
        return jsonify({"error": "no login in progress"}), 400

    if not _code_ok(user, code):
        models.log_event(user["username"], "login_failure", "invalid 2FA code")
        return jsonify({"error": "invalid code"}), 401

    return jsonify(_sign_in(user, "via 2FA"))


@auth_bp.route("/login/google", methods=["POST"])
@limit("google-ip", 20, 60)
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
@limit("link-ip", 20, 60)
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
@limit("link-ip", 20, 60)
def use_account_link(code):
    """Set the password from an invite or reset link (once), then go on to the second
    sign-in step: entering a code, or setting up 2FA for a new account."""
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""

    link = models.find_link(code)
    if link is None or not link["is_active"]:
        return jsonify({"error": "this link is no longer valid. Ask your administrator for a new one."}), 404
    problem = password_policy.check(password, link["username"], link.get("full_name"), link.get("email"))
    if problem:
        return jsonify({"error": problem}), 400
    if not models.set_password_with_link(link["link_id"], link["user_id"], password):
        return jsonify({"error": "this link has already been used"}), 409

    action = "user_activated" if link["purpose"] == "invite" else "password_reset_completed"
    models.log_event(link["username"], action, None)

    return _second_step(models.get_user_by_id(link["user_id"]), "after setting password")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Sign out, and end this account's sessions on every other device too (models.end_sessions),
    so a copy of the cookie stops working."""
    user = current_user()
    if user is not None:
        models.end_sessions(user["id"])
        models.log_event(user["username"], "logout", None)
    session.clear()
    return jsonify({"message": "logged out"})


@auth_bp.route("/me", methods=["GET"])
def me():
    user = current_user()
    if user is None:
        return jsonify({"error": "not logged in"}), 401
    return jsonify({"id": user["id"], "username": user["username"], "role": user["role"]})


@auth_bp.route("/account", methods=["GET"])
@login_required
def account():
    """The signed-in user's own details for the Settings page. Never returns the password hash or 2FA secret."""
    user = models.get_user_by_id(session["user_id"])
    if user is None:
        return jsonify({"error": "authentication required"}), 401
    return jsonify({
        "username": user["username"],
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "organisation": user.get("organisation"),
        "role": user["role"],
        "totp_enabled": bool(user.get("totp_enabled")),
        "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
        "password_changed_at": _iso(models.last_password_change(user["username"])),
    })


def _iso(value):
    return value.isoformat() if value else None


@auth_bp.route("/account/password", methods=["POST"])
@login_required
@limit("password-change", 5, 900, key=signed_in_user)
def change_password():
    """Change the signed-in user's own password. The current password is required, so a session left
    open on a shared computer cannot be used to take over the account."""
    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""
    if not current or not new:
        return jsonify({"error": "current and new password are required"}), 400
    if new == current:
        return jsonify({"error": "the new password must be different from the current one"}), 400

    user = models.get_user_by_id(session["user_id"])
    if user is None:
        return jsonify({"error": "authentication required"}), 401
    problem = password_policy.check(new, user["username"], user.get("full_name"), user.get("email"),
                                    user.get("organisation"))
    if problem:
        return jsonify({"error": problem}), 400
    if not models.verify_password(user, current):
        models.log_event(user["username"], "password_change_failure", "wrong current password")
        return jsonify({"error": "the current password is not correct"}), 403

    models.update_password(user["username"], new)  # also ends every other session of this account
    state = models.session_state(user["id"])
    session["sv"] = state["session_version"] if state else None  # this device stays signed in
    models.log_event(user["username"], "password_changed", None)
    return jsonify({"message": "password changed"})


def _enrolling_user():
    """The signed-in user, or the person part-way through sign-in who must set up 2FA (within the
    time allowed for that step)."""
    signed_in = current_user()
    user_id = signed_in["id"] if signed_in else _in_progress("setup_user_id")
    return models.get_user_by_id(user_id) if user_id else None


@auth_bp.route("/totp/setup", methods=["POST"])
@limit("totp-setup", 10, 3600, key=pending_user)
def totp_setup():
    """Make a new TOTP secret and return it as a QR code plus the key for manual entry.
    2FA stays off until /totp/enable confirms a code from it, so an abandoned setup never
    locks anyone out."""
    user = _enrolling_user()
    if user is None:
        return jsonify({"error": "not logged in"}), 401
    if user.get("totp_enabled"):
        # Replacing a working secret would let anyone holding a session lock the owner out, so a
        # new authenticator only comes after an administrator resets 2FA (routes_users.py).
        return jsonify({"error": "two-factor sign-in is already set up. If you have lost your "
                                 "authenticator, ask an administrator to reset it."}), 409

    secret = pyotp.random_base32()
    models.set_totp_secret(user["id"], secret)

    uri = pyotp.TOTP(secret).provisioning_uri(name=user["username"], issuer_name=TOTP_ISSUER)
    qr_image = qrcode.make(uri)
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return jsonify({"secret": secret, "qr_code_png_base64": qr_base64})


@auth_bp.route("/totp/enable", methods=["POST"])
@limit("code-ip", 20, 60)
@limit("code-account", 5, 300, key=pending_user)
@limit("code-account-hour", 20, 3600, key=pending_user)
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
    if not _code_ok(user, code):
        models.log_event(user["username"], "login_failure", "invalid 2FA setup code")
        return jsonify({"error": "invalid code"}), 401

    models.enable_totp(user["id"])
    models.log_event(user["username"], "totp_enabled", None)
    if "setup_user_id" in session:
        return jsonify({**_sign_in(user, "after setting up 2FA"), "totp_enabled": True})
    return jsonify({"totp_enabled": True})
