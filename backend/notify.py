"""
In-app notifications for the Notifications screen, also pushed to phones and browsers where a user has
installed the app and turned notifications on (Web Push, VAPID keys in backend/.env). Pushing is best
effort: the notification is always saved in the app, and a phone that cannot be reached is skipped.

Who is told what (proposal use cases, with Disaster Management verification before the field is told):
  verify    a new incident needs checking            Disaster Management officers
  incident  an incident was verified                 Emergency Responders and Government Officials
  update    the full model confirmed or withdrew     Disaster Management, and the field once verified
            a provisional incident
  rain      a heavy-rain forecast warning             all three roles
Only live data notifies; replays and rescoring do not.
"""
import json

import config
import db

DMA = ("disaster_management_agency",)
FIELD = ("emergency_responder", "government_official")


def _users(roles):
    return [r["id"] for r in db.query_all("SELECT id FROM users WHERE is_active AND role = ANY(%s)", (list(roles),))]


def _push(user_ids, payload):
    """Send one Web Push message to every subscription of these users. Returns how many were delivered."""
    if not (config.VAPID_PRIVATE_KEY and config.VAPID_PUBLIC_KEY) or not user_ids:
        return 0
    try:
        from pywebpush import WebPushException, webpush  # noqa: PLC0415 - optional until push is configured
    except ImportError:
        return 0
    subs = db.query_all("SELECT id, endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ANY(%s)",
                        (list(user_ids),))
    sent = 0
    for s in subs:
        try:
            webpush({"endpoint": s["endpoint"], "keys": {"p256dh": s["p256dh"], "auth": s["auth"]}},
                    json.dumps(payload), vapid_private_key=config.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": config.VAPID_SUBJECT}, timeout=10)
            sent += 1
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):  # unsubscribed or expired
                db.execute("DELETE FROM push_subscriptions WHERE id = %s", (s["id"],))
        except Exception:  # noqa: BLE001 - one unreachable device must not stop the rest
            pass
    return sent


def send(roles, kind, title, body, link):
    """Save one notification for every active user in roles, push it, and return how many users got it."""
    user_ids = _users(roles)
    for uid in user_ids:
        db.execute("INSERT INTO notifications (user_id, kind, title, body, link) VALUES (%s, %s, %s, %s, %s)",
                   (uid, kind, title, body, link))
    _push(user_ids, {"title": title, "body": body, "link": link})
    return len(user_ids)


def _place(incident):
    wards = ", ".join(incident.get("wards") or [])
    return incident["catchment"] + (f" ({wards})" if wards else "")


def _days(incident):
    start, end = incident["start_day"], incident["end_day"]
    return f"{start:%d %b %Y}" if start == end else f"{start:%d %b} to {end:%d %b %Y}"


def incident_to_verify(incident):
    note = " Provisional: CHIRPS rainfall for these days is not published yet." if incident.get("provisional") else ""
    return send(DMA, "verify", f"Incident to verify: {incident['catchment']}",
                f"The model flagged {_place(incident)} for {_days(incident)}, severity {incident['severity']}.{note}",
                f"/incidents?id={incident['id']}")


def incident_verified(incident, by):
    return send(FIELD, "incident", f"Flood incident ({incident['severity']}): {incident['catchment']}",
                f"{_place(incident)}, {_days(incident)}. Verified by {by}.", f"/incidents?id={incident['id']}")


def incident_settled(incident, settled):
    """The full model confirmed or withdrew a provisional incident."""
    word = "confirmed" if settled == "confirmed" else "not confirmed"
    title = f"Incident {word} by the full model: {incident['catchment']}"
    body = f"{_place(incident)}, {_days(incident)}, now that CHIRPS rainfall is in."
    link = f"/incidents?id={incident['id']}"
    told = send(DMA, "update", title, body, link)
    if incident["verification"] == "verified":
        told += send(FIELD, "update", title, body, link)
    return told


def rainfall_warning(catchment, wards, day, mm, threshold_mm):
    place = catchment + (f" ({', '.join(wards)})" if wards else "")
    return send(DMA + FIELD, "rain", f"Heavy rain forecast: {catchment}",
                f"{mm:.0f} mm forecast for {day:%d %b %Y} in {place}, at or above the {threshold_mm:.0f} mm warning "
                "level. This comes from the rainfall forecast, not the flood model.", "/")
