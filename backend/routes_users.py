"""
User management for the System Administration screen. Accounts are created by email
invite: the administrator never sets or sees a password. The invited person gets a
single-use link (routes_auth.py's /account/link/<code>) and chooses their own.
Every route here is restricted to the system_administrator role.
"""
import re

from flask import Blueprint, jsonify, request, session

import config
import db
import mailer
import models
from decorators import role_required

users_bp = Blueprint("users", __name__, url_prefix="/api")

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ROLE_LABELS = {
    "disaster_management_agency": "Disaster Management Officer",
    "emergency_responder": "Emergency Responder",
    "government_official": "Government Official",
    "system_administrator": "System Administrator",
}


def _link(code):
    return f"{config.FRONTEND_URL}/account/{code}"


def _public(row):
    """A list_users() row as the screen needs it, with a status and no secrets."""
    out = {k: row.get(k) for k in ("id", "username", "full_name", "email", "organisation", "role",
                                   "is_active", "totp_enabled", "created_at", "last_sign_in",
                                   "invite_expires_at")}
    out["status"] = models.user_status(row)
    for key in ("created_at", "last_sign_in", "invite_expires_at"):
        if out[key] is not None:
            out[key] = out[key].isoformat()
    return out


def _find(user_id):
    row = next((r for r in models.list_users() if r["id"] == user_id), None)
    return row


def _clean(value):
    value = (value or "").strip()
    return value or None


def _mail_error(exc):
    if isinstance(exc, mailer.MailNotConfigured):
        return jsonify({"error": str(exc)}), 503
    # The mail server's own message can name internal hosts or accounts, so it goes to the activity log only
    models.log_event(session.get("username"), "email_send_failed", str(exc)[:500])
    return jsonify({"error": "the email could not be sent, so nothing was saved. Try again, and if it keeps "
                             "failing, check the email settings on the server (the activity log has the reason)."}), 502


@users_bp.route("/users", methods=["GET"])
@role_required("system_administrator")
def list_users():
    return jsonify([_public(r) for r in models.list_users()])


@users_bp.route("/users/invite", methods=["POST"])
@role_required("system_administrator")
def invite_user():
    """Create an account with no password and email its owner a link to activate it."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    full_name = _clean(data.get("full_name"))
    organisation = _clean(data.get("organisation"))
    role = data.get("role")

    if not EMAIL_PATTERN.match(email):
        return jsonify({"error": "enter a valid email address"}), 400
    if not full_name:
        return jsonify({"error": "full name is required"}), 400
    if role not in config.ROLES:
        return jsonify({"error": f"role must be one of {', '.join(config.ROLES)}"}), 400
    if models.get_user_by_email(email) is not None:
        return jsonify({"error": f"{email} already has an account"}), 409

    username = models.username_from_email(email)
    inviter = session.get("username")

    def send(code):
        subject, text, html = mailer.invite_email(full_name, username, ROLE_LABELS[role], inviter,
                                                  _link(code), config.INVITE_LINK_HOURS)
        mailer.send_email(email, subject, text, html)

    try:
        user_id = models.create_invited_user(username, email, full_name, organisation, role, inviter,
                                             config.INVITE_LINK_HOURS, send)
    except Exception as exc:  # noqa: BLE001 - any email failure means nothing was saved
        return _mail_error(exc)

    models.log_event(inviter, "user_invited", f"{username} <{email}> ({role})")
    return jsonify(_public(_find(user_id))), 201


@users_bp.route("/users/<int:user_id>/resend-invite", methods=["POST"])
@role_required("system_administrator")
def resend_invite(user_id):
    row = _find(user_id)
    if row is None:
        return jsonify({"error": "no such user"}), 404
    if row["has_password"]:
        return jsonify({"error": "this account is already active"}), 409
    inviter = session.get("username")

    def send(code):
        subject, text, html = mailer.invite_email(row["full_name"], row["username"], ROLE_LABELS[row["role"]],
                                                  inviter, _link(code), config.INVITE_LINK_HOURS)
        mailer.send_email(row["email"], subject, text, html)

    try:
        models.issue_link(user_id, "invite", config.INVITE_LINK_HOURS, inviter, send)
    except Exception as exc:  # noqa: BLE001
        return _mail_error(exc)
    models.log_event(inviter, "user_invite_resent", row["username"])
    return jsonify(_public(_find(user_id)))


@users_bp.route("/users/<int:user_id>/send-reset", methods=["POST"])
@role_required("system_administrator")
def send_reset(user_id):
    """Email an active user a link to choose a new password; the administrator never sets it."""
    row = _find(user_id)
    if row is None:
        return jsonify({"error": "no such user"}), 404
    if not row["has_password"] or not row["is_active"]:
        return jsonify({"error": "only active accounts can be sent a reset link"}), 409
    if not row["email"]:
        return jsonify({"error": "this account has no email address to send the link to"}), 409
    admin = session.get("username")

    def send(code):
        subject, text, html = mailer.reset_email(row["full_name"], row["username"], _link(code),
                                                 config.RESET_LINK_HOURS)
        mailer.send_email(row["email"], subject, text, html)

    try:
        models.issue_link(user_id, "reset", config.RESET_LINK_HOURS, admin, send)
    except Exception as exc:  # noqa: BLE001
        return _mail_error(exc)
    models.log_event(admin, "password_reset_sent", row["username"])
    return jsonify({"sent": True})


@users_bp.route("/users/<int:user_id>/reset-2fa", methods=["POST"])
@role_required("system_administrator")
def reset_two_factor(user_id):
    """For someone who lost their phone: turn their 2FA off so their next sign-in sets it up again."""
    if user_id == session.get("user_id"):
        return jsonify({"error": "you cannot reset your own two-factor sign-in"}), 400
    target = models.get_user_by_id(user_id)
    if target is None:
        return jsonify({"error": "no such user"}), 404
    models.disable_totp(user_id)
    models.log_event(session.get("username"), "user_2fa_reset", target["username"])
    return jsonify(_public(_find(user_id)))


@users_bp.route("/users/<int:user_id>", methods=["PATCH"])
@role_required("system_administrator")
def update_user(user_id):
    """Change a user's role, active status, name, organisation or email address."""
    data = request.get_json(silent=True) or {}
    target = models.get_user_by_id(user_id)
    if target is None:
        return jsonify({"error": "no such user"}), 404
    admin = session.get("username")

    if "is_active" in data and not data["is_active"] and user_id == session.get("user_id"):
        return jsonify({"error": "you cannot deactivate your own account"}), 400
    if "role" in data and data["role"] not in config.ROLES:
        return jsonify({"error": f"role must be one of {', '.join(config.ROLES)}"}), 400
    if "role" in data and data["role"] != target["role"] and user_id == session.get("user_id"):
        return jsonify({"error": "you cannot change your own role"}), 400
    if "full_name" in data and not _clean(data["full_name"]):
        return jsonify({"error": "full name cannot be empty"}), 400
    new_email = None
    if "email" in data:
        new_email = (data["email"] or "").strip().lower()
        if not EMAIL_PATTERN.match(new_email):
            return jsonify({"error": "enter a valid email address"}), 400
        other = models.get_user_by_email(new_email)
        if other is not None and other["id"] != user_id:
            return jsonify({"error": f"{new_email} already belongs to another account"}), 409

    if "role" in data and data["role"] != target["role"]:
        models.update_user_role(user_id, data["role"])
        models.log_event(admin, "user_role_changed", f"{target['username']} -> {data['role']}")
    if "is_active" in data and bool(data["is_active"]) != target["is_active"]:
        models.set_user_active(user_id, bool(data["is_active"]))
        models.log_event(admin, "user_reactivated" if data["is_active"] else "user_deactivated",
                         target["username"])
    if "full_name" in data or "organisation" in data:
        full_name = _clean(data.get("full_name", target["full_name"]))
        organisation = _clean(data.get("organisation", target["organisation"]))
        if (full_name, organisation) != (target["full_name"], target["organisation"]):
            models.update_user_details(user_id, full_name, organisation)
            models.log_event(admin, "user_details_changed", target["username"])
    if new_email and new_email != (target["email"] or "").lower():
        models.set_user_email(user_id, new_email)
        models.log_event(admin, "user_email_changed", f"{target['username']} -> {new_email}")
        if user_id == session.get("user_id"):  # an administrator editing their own email stays signed in
            state = models.session_state(user_id)
            session["sv"] = state["session_version"] if state else None

    return jsonify(_public(_find(user_id)))


@users_bp.route("/users/organisations", methods=["GET"])
@role_required("system_administrator")
def list_organisations():
    """Organisations already in use, offered as suggestions when inviting someone."""
    rows = db.query_all("SELECT DISTINCT organisation FROM users WHERE organisation IS NOT NULL ORDER BY 1")
    return jsonify([r["organisation"] for r in rows])
