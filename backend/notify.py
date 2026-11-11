"""
Emails new flood alerts and rainfall warnings to the people who act on them (proposal use case
"Receive real-time flood alerts"): every active Emergency Responder and Government Official with an
email address on their account. Sending never blocks scoring: a mail failure is logged and returned.
Only live readings and live forecasts notify; replayed or rescored history does not.
"""
from html import escape

import config
import db
import mailer
import models

NOTIFY_ROLES = ("emergency_responder", "government_official")


def recipients():
    """Email addresses of the active users who receive alerts."""
    rows = db.query_all(
        "SELECT email FROM users WHERE is_active AND email IS NOT NULL AND email <> '' AND role IN %s",
        (NOTIFY_ROLES,),
    )
    return [r["email"] for r in rows]


def _send_all(subject, text, html, what):
    """Send one message to every recipient; log the outcome once. Returns the number sent."""
    to = recipients()
    if not to:
        models.log_event(None, "alert_notify_skipped", f"{what}: no responder or official has an email address")
        return 0
    sent, failed = 0, []
    for address in to:
        try:
            mailer.send_email(address, subject, text, html)
            sent += 1
        except mailer.MailNotConfigured:
            models.log_event(None, "alert_notify_skipped", f"{what}: email is not configured on this server")
            return 0
        except Exception as e:  # noqa: BLE001 - one bad address must not stop the rest
            failed.append(f"{address} ({e.__class__.__name__})")
    detail = f"{what}: emailed {sent} of {len(to)}" + (f"; failed {', '.join(failed)}" if failed else "")
    models.log_event(None, "alert_notified", detail)
    return sent


def flood_alert(catchment, wards, day, severity, score, threshold):
    """Email a new model alert for one catchment-day."""
    places = ", ".join(wards or []) or "the catchment"
    subject = f"Flood alert ({severity}): {catchment}, {day:%d %b %Y}"
    link = f"{config.FRONTEND_URL}/alerts"
    footnote = "You receive this because your account is an Emergency Responder or Government Official account."
    text = (f"The flood model flagged {catchment} for {day:%d %B %Y}.\n"
            f"Severity: {severity} (score {score:.2f}, alert line {threshold:.3f}).\n"
            f"Wards in the catchment: {places}.\n\nOpen the alert list: {link}\n\n{footnote}\n")
    html = mailer._html(
        f"Flood alert: {catchment}",
        [f"The flood model flagged <strong>{escape(catchment)}</strong> for <strong>{day:%d %B %Y}</strong>.",
         f"Severity <strong>{escape(severity)}</strong>, score {score:.2f} against an alert line of {threshold:.3f}.",
         f"Wards in the catchment: {escape(places)}."],
        "Open the alert list", link, footnote,
    )
    return _send_all(subject, text, html, f"flood alert {catchment} {day}")


def rainfall_warning(catchment, wards, day, mm, threshold_mm):
    """Email a new forecast rainfall warning for one catchment-day."""
    places = ", ".join(wards or []) or "the catchment"
    subject = f"Heavy rain warning: {catchment}, {day:%d %b %Y}"
    link = f"{config.FRONTEND_URL}/"
    footnote = "This warning comes from the rainfall forecast, not from the flood model."
    text = (f"The rainfall forecast for {catchment} on {day:%d %B %Y} is {mm:.0f} mm, "
            f"at or above the {threshold_mm:.0f} mm warning level.\nWards in the catchment: {places}.\n\n"
            f"Open the dashboard: {link}\n\n{footnote}\n")
    html = mailer._html(
        f"Heavy rain warning: {catchment}",
        [f"The forecast for <strong>{escape(catchment)}</strong> on <strong>{day:%d %B %Y}</strong> "
         f"is <strong>{mm:.0f} mm</strong>, at or above the {threshold_mm:.0f} mm warning level.",
         f"Wards in the catchment: {escape(places)}."],
        "Open the dashboard", link, footnote,
    )
    return _send_all(subject, text, html, f"rainfall warning {catchment} {day}")
