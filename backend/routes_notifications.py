"""
The Notifications screen (each user's own notifications, newest first) and Web Push sign-up for the
installed app. Notifications are created by notify.py; nothing here creates them.
"""
import datetime
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request, session

import config
import db
from decorators import login_required

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api")


def _serialize(rows):
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (datetime.datetime, datetime.date)):
                row[key] = value.isoformat()
    return rows


@notifications_bp.route("/notifications", methods=["GET"])
@login_required
def list_notifications():
    limit = min(request.args.get("limit", default=50, type=int) or 50, 200)
    sql = "SELECT id, kind, title, body, link, created_at, read_at FROM notifications WHERE user_id = %s "
    if request.args.get("unread") == "true":
        sql += "AND read_at IS NULL "
    rows = db.query_all(sql + "ORDER BY created_at DESC, id DESC LIMIT %s", (session["user_id"], limit))
    return jsonify(_serialize(rows))


@notifications_bp.route("/notifications/unread-count", methods=["GET"])
@login_required
def unread_count():
    row = db.query_one("SELECT COUNT(*) AS unread FROM notifications WHERE user_id = %s AND read_at IS NULL",
                       (session["user_id"],))
    return jsonify(row)


@notifications_bp.route("/notifications/<int:notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    db.execute("UPDATE notifications SET read_at = now() WHERE id = %s AND user_id = %s AND read_at IS NULL",
               (notification_id, session["user_id"]))
    return jsonify({"id": notification_id, "read": True})


@notifications_bp.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_all_read():
    db.execute("UPDATE notifications SET read_at = now() WHERE user_id = %s AND read_at IS NULL",
               (session["user_id"],))
    return jsonify({"read": True})


@notifications_bp.route("/push/key", methods=["GET"])
@login_required
def push_key():
    """The public key browsers need to subscribe, or null when push is not set up on this server."""
    return jsonify({"key": config.VAPID_PUBLIC_KEY or None})


# The Web Push services browsers use. A subscription naming any other address is refused, so the server
# never sends requests to a host a user chose.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com")
PUSH_HOST_SUFFIXES = (".push.apple.com", ".notify.windows.com")
MAX_SUBSCRIPTIONS = 10  # browsers and phones per user


def _push_service(endpoint):
    host = urlsplit(endpoint).hostname or ""
    return urlsplit(endpoint).scheme == "https" and (host in PUSH_HOSTS or host.endswith(PUSH_HOST_SUFFIXES))


@notifications_bp.route("/push/subscribe", methods=["POST"])
@login_required
def push_subscribe():
    """Save this browser's push subscription for the signed-in user (moving it over if another user had it)."""
    data = request.get_json(silent=True) or {}
    keys = data.get("keys") or {}
    endpoint, p256dh, auth = data.get("endpoint"), keys.get("p256dh"), keys.get("auth")
    if not (isinstance(endpoint, str) and len(endpoint) <= 1000 and isinstance(p256dh, str) and isinstance(auth, str)
            and p256dh and auth and len(p256dh) <= 200 and len(auth) <= 100):
        return jsonify({"error": "a push subscription with endpoint and keys is required"}), 400
    if not _push_service(endpoint):
        return jsonify({"error": "this push service is not supported"}), 400
    owned = db.query_one("SELECT COUNT(*) AS n FROM push_subscriptions WHERE user_id = %s AND endpoint <> %s",
                         (session["user_id"], endpoint))
    if owned and owned["n"] >= MAX_SUBSCRIPTIONS:
        return jsonify({"error": f"at most {MAX_SUBSCRIPTIONS} devices can receive notifications. "
                                 "Turn them off on one you no longer use."}), 409
    # A browser that signs in as someone else moves its subscription over, but only with the same keys,
    # which only that browser holds, so knowing another person's endpoint is not enough to take it.
    db.execute(
        "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id "
        "WHERE push_subscriptions.p256dh = EXCLUDED.p256dh AND push_subscriptions.auth = EXCLUDED.auth",
        (session["user_id"], endpoint, p256dh, auth))
    return jsonify({"subscribed": True}), 201


@notifications_bp.route("/push/unsubscribe", methods=["POST"])
@login_required
def push_unsubscribe():
    endpoint = (request.get_json(silent=True) or {}).get("endpoint")
    db.execute("DELETE FROM push_subscriptions WHERE endpoint = %s AND user_id = %s", (endpoint, session["user_id"]))
    return jsonify({"subscribed": False})
