"""
Sends the system's emails (account invites and password resets) through the SMTP
account set in backend/.env, over an encrypted STARTTLS connection.
"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from html import escape

import config


class MailNotConfigured(RuntimeError):
    """Raised when no SMTP account is set, so nothing is sent or saved."""


def _tls_context():
    try:
        import certifi  # noqa: PLC0415 - optional, fixes missing CA bundles on some Python builds
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def send_email(to, subject, text, html):
    """Send one email with a plain-text and an HTML version. Raises on any failure."""
    if not (config.SMTP_USERNAME and config.SMTP_PASSWORD):
        raise MailNotConfigured(
            "Email is not configured on this server. Set SMTP_USERNAME and SMTP_PASSWORD in backend/.env."
        )
    msg = EmailMessage()
    msg["From"] = formataddr((config.MAIL_FROM_NAME, config.MAIL_FROM_ADDRESS))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
        server.starttls(context=_tls_context())
        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.send_message(msg)


def _html(heading, paragraphs, button_text, link, footnote):
    body = "".join(f'<p style="margin:0 0 14px">{p}</p>' for p in paragraphs)
    return f"""<!doctype html>
<html><body style="margin:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#1f2933">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:520px;background:#ffffff;border-radius:12px;padding:32px">
        <tr><td>
          <p style="margin:0 0 8px;font-size:13px;color:#52606d">Flood Early Warning, Nairobi river catchments</p>
          <h1 style="margin:0 0 20px;font-size:22px">{escape(heading)}</h1>
          {body}
          <p style="margin:24px 0"><a href="{escape(link)}"
             style="background:#31493c;color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:8px;display:inline-block">{escape(button_text)}</a></p>
          <p style="margin:0 0 6px;font-size:13px;color:#52606d">If the button does not work, copy this link into your browser:</p>
          <p style="margin:0 0 20px;font-size:13px;word-break:break-all"><a href="{escape(link)}">{escape(link)}</a></p>
          <p style="margin:0;font-size:13px;color:#52606d">{escape(footnote)}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def invite_email(full_name, username, role_label, inviter, link, hours):
    """Subject, plain text and HTML for an account invite."""
    name = full_name or username
    subject = "You have been invited to the Flood Early Warning System"
    footnote = f"This link works once and expires in {hours} hours. If you were not expecting this email, you can ignore it."
    text = (
        f"Hello {name},\n\n"
        f"{inviter} has invited you to the Flood Early Warning System for the Nairobi river catchments "
        f"as a {role_label}.\n\nYour username is {username}. Set your password to activate your account:\n"
        f"{link}\n\n{footnote}\n"
    )
    html = _html(
        "Activate your account",
        [f"Hello {escape(name)},",
         f"{escape(inviter)} has invited you to the Flood Early Warning System as a <strong>{escape(role_label)}</strong>.",
         f"Your username is <strong>{escape(username)}</strong>. Choose your password to activate your account."],
        "Set your password", link, footnote,
    )
    return subject, text, html


def security_notice_email(full_name, username, change, admin):
    """Subject and plain text and HTML telling someone that an administrator changed how their account
    signs in, so a change they did not expect is noticed."""
    name = full_name or username
    subject = "A change was made to your Flood Early Warning account"
    text = (
        f"Hello {name},\n\nThe administrator {admin} {change} for your account {username}.\n\n"
        "If you did not ask for this, contact your system administrator straight away.\n"
    )
    paragraphs = [
        f"Hello {escape(name)},",
        f"The administrator <strong>{escape(admin)}</strong> {escape(change)} for your account "
        f"<strong>{escape(username)}</strong>.",
        "If you did not ask for this, contact your system administrator straight away.",
    ]
    html = f"""<!doctype html>
<html><body style="margin:0;background:#f4f7fb;font-family:Arial,Helvetica,sans-serif;color:#1f2933">
  <div style="max-width:520px;margin:32px auto;background:#ffffff;border-radius:12px;padding:32px">
    <p style="margin:0 0 8px;font-size:13px;color:#52606d">Flood Early Warning, Nairobi river catchments</p>
    <h1 style="margin:0 0 20px;font-size:22px">{escape(subject)}</h1>
    {"".join(f'<p style="margin:0 0 14px">{p}</p>' for p in paragraphs)}
  </div>
</body></html>"""
    return subject, text, html


def reset_email(full_name, username, link, hours):
    """Subject, plain text and HTML for a password reset."""
    name = full_name or username
    subject = "Reset your Flood Early Warning password"
    footnote = f"This link works once and expires in {hours} hours. If you did not expect it, you can ignore this email and your password stays the same."
    text = (
        f"Hello {name},\n\nAn administrator has sent you a link to choose a new password for the "
        f"account {username}:\n{link}\n\n{footnote}\n"
    )
    html = _html(
        "Choose a new password",
        [f"Hello {escape(name)},",
         f"An administrator has sent you a link to choose a new password for the account <strong>{escape(username)}</strong>."],
        "Choose a new password", link, footnote,
    )
    return subject, text, html
