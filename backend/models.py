"""
User-related queries against the `users` table (db/init/02_schema.sql),
plus system_logs writes (the System Administration screen's log panel).

Kept separate from db.py so routes_auth.py can import just what it needs
(user lookups) without pulling in the lower-level query helpers directly.
"""

import hashlib
import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

import db

USER_COLUMNS = (
    "id, username, password_hash, role, is_active, created_at, "
    "totp_secret, totp_enabled, email, full_name, organisation"
)


def get_user_by_username(username):
    """Return the user row (dict) for a username, or None if not found.
    Includes totp_secret/totp_enabled (db/add_2fa_columns.py) so
    routes_auth.py can decide whether a login needs a second step, and
    email (db/add_google_signin_columns.py) for the admin-facing user
    list."""
    return db.query_one(
        f"SELECT {USER_COLUMNS} FROM users WHERE username = %s",
        (username,),
    )


def get_user_by_id(user_id):
    """Return the user row (dict) for a user id, or None if not found."""
    return db.query_one(
        f"SELECT {USER_COLUMNS} FROM users WHERE id = %s",
        (user_id,),
    )


def get_user_by_email(email):
    """Return the user row (dict) for a Google-verified email, or None.
    Used only by routes_auth.py's POST /login/google: an email with no
    matching row here means no admin-provisioned account exists for it,
    which is what keeps Google Sign-In from becoming public
    registration."""
    return db.query_one(
        f"SELECT {USER_COLUMNS} FROM users WHERE lower(email) = lower(%s)",
        (email,),
    )


def get_user_by_login(identifier):
    """The user row for a username or an email address (sign-in accepts either), or None."""
    return db.query_one(
        f"SELECT {USER_COLUMNS} FROM users WHERE username = %s OR lower(email) = lower(%s) "
        "ORDER BY (username = %s) DESC LIMIT 1",
        (identifier, identifier, identifier),
    )


def verify_password(user, plain_password):
    """Check a plain-text password against a user row's stored hash. An invited user who
    has not set a password yet never matches."""
    if not user.get("password_hash"):
        return False
    return check_password_hash(user["password_hash"], plain_password)


def _hash_password(plain_password):
    return generate_password_hash(plain_password, method="pbkdf2:sha256")


def _hash_link_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def user_status(row):
    """deactivated, active, invited or invite_expired, from a list_users() row."""
    if not row["is_active"]:
        return "deactivated"
    if row["has_password"]:
        return "active"
    if row.get("invite_expires_at") is None or row.get("invite_expired"):
        return "invite_expired"
    return "invited"


def list_users():
    """Every user for the administration screen, with their last sign-in and any pending invite."""
    return db.query_all(
        "SELECT u.id, u.username, u.full_name, u.email, u.organisation, u.role, u.is_active, "
        "u.created_at, u.totp_enabled, (u.password_hash IS NOT NULL) AS has_password, "
        "(SELECT MAX(l.occurred_at) FROM system_logs l "
        " WHERE l.actor = u.username AND l.action = 'login_success') AS last_sign_in, "
        "inv.expires_at AS invite_expires_at, (inv.expires_at < now()) AS invite_expired "
        "FROM users u "
        "LEFT JOIN LATERAL (SELECT t.expires_at FROM user_tokens t WHERE t.user_id = u.id "
        " AND t.purpose = 'invite' AND t.used_at IS NULL ORDER BY t.created_at DESC LIMIT 1) inv ON true "
        "ORDER BY lower(coalesce(u.full_name, u.username))"
    )


def username_from_email(email):
    """A free username built from the part of the email before the @, e.g. jane.doe or jane.doe2."""
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower()) or "user"
    taken = {r["username"] for r in db.query_all(
        "SELECT username FROM users WHERE username = %s OR username LIKE %s", (base, base + "%"))}
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}{n}", n + 1
    return candidate


def _insert_link(cur, user_id, purpose, hours, created_by):
    """Cancel the user's older unused links of this purpose and store a new one. Returns its code."""
    code = secrets.token_urlsafe(32)
    cur.execute(
        "UPDATE user_tokens SET expires_at = now() "
        "WHERE user_id = %s AND purpose = %s AND used_at IS NULL AND expires_at > now()",
        (user_id, purpose),
    )
    cur.execute(
        "INSERT INTO user_tokens (user_id, purpose, token_hash, expires_at, created_by) "
        "VALUES (%s, %s, %s, now() + %s * interval '1 hour', %s)",
        (user_id, purpose, _hash_link_code(code), hours, created_by),
    )
    return code


def create_invited_user(username, email, full_name, organisation, role, created_by, hours, send):
    """Create an account with no password plus its invite link, then call send(code).
    Everything is saved only if send() succeeds, so a failed email leaves no half-made account."""
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role, email, full_name, organisation) "
                "VALUES (%s, NULL, %s, %s, %s, %s) RETURNING id",
                (username, role, email, full_name, organisation),
            )
            user_id = cur.fetchone()[0]
            code = _insert_link(cur, user_id, "invite", hours, created_by)
        send(code)
        conn.commit()
        return user_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def issue_link(user_id, purpose, hours, created_by, send):
    """A fresh invite or reset link for an existing user (older ones stop working), saved only
    if send(code) succeeds."""
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            code = _insert_link(cur, user_id, purpose, hours, created_by)
        send(code)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def find_link(code):
    """The unused, unexpired link for a code, with its user, or None."""
    return db.query_one(
        "SELECT t.id AS link_id, t.purpose, t.expires_at, u.id AS user_id, u.username, u.full_name, "
        "u.email, u.role, u.is_active FROM user_tokens t JOIN users u ON u.id = t.user_id "
        "WHERE t.token_hash = %s AND t.used_at IS NULL AND t.expires_at > now()",
        (_hash_link_code(code),),
    )


def set_password_with_link(link_id, user_id, plain_password):
    """Use a link once: set the password and mark the link used in one transaction.
    Returns False if the link was used in the meantime."""
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE user_tokens SET used_at = now() WHERE id = %s AND used_at IS NULL AND expires_at > now()",
                (link_id,),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return False
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s",
                        (_hash_password(plain_password), user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def update_user_details(user_id, full_name, organisation):
    """Change a user's display name and organisation."""
    db.execute("UPDATE users SET full_name = %s, organisation = %s WHERE id = %s",
               (full_name, organisation, user_id))


def create_user(username, plain_password, role, email=None):
    """Insert a new user with a hashed password. Returns the new user's
    id. email is optional and lets this account also sign in via Google
    (routes_auth.py's POST /login/google), still only after an admin has
    set it here, never through self-registration."""
    # Explicit pbkdf2 method: Werkzeug's default ("scrypt") needs
    # hashlib.scrypt, which is missing on a Python built against LibreSSL
    # rather than OpenSSL 1.1+ (notably the Python that ships with Xcode
    # Command Line Tools on macOS), raising AttributeError at hash time.
    # pbkdf2 uses hashlib.pbkdf2_hmac instead, which has no such
    # dependency. check_password_hash() reads the method back out of the
    # stored hash string itself, so verify_password() needs no change.
    password_hash = generate_password_hash(plain_password, method="pbkdf2:sha256")
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash, role, email) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (username, password_hash, role, email),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    finally:
        conn.close()


def set_user_email(user_id, email):
    """Attach (or clear, with email=None) a Gmail address to an
    already-provisioned account, so it can sign in via Google as well
    as its password. Returns True if a matching user was found and
    updated."""
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET email = %s WHERE id = %s", (email, user_id))
            updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def update_password(username, new_password):
    """Update an existing user's password hash in place. Returns True if
    a matching user was found and updated, False if no such username
    exists. Uses the same pbkdf2:sha256 method as create_user() (see
    that function's comment on why, not Werkzeug's scrypt default)."""
    password_hash = generate_password_hash(new_password, method="pbkdf2:sha256")
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (password_hash, username),
            )
            updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def update_user_role(user_id, new_role):
    """Change an existing user's role in place. Returns True if a
    matching user was found and updated, False otherwise. The caller
    (routes_dashboard.py) is responsible for checking new_role against
    config.ROLES first; this function trusts what it's given, same
    division of responsibility create_user.py's CLI script already
    has with models.create_user()."""
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
            updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def set_user_active(user_id, is_active):
    """Activate or deactivate a user in place (the System Administration
    screen's "deactivate" control). A deactivated account still exists,
    so its alert/reading history stays intact, it just can't sign in
    (see routes_auth.py's login()). Returns True if a matching user was
    found and updated, False otherwise."""
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET is_active = %s WHERE id = %s", (is_active, user_id))
            updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def set_totp_secret(user_id, secret):
    """Store a freshly generated TOTP secret for a user, ahead of them
    confirming it (see enable_totp). Called by the /totp/setup route
    each time it's hit, so re-running setup before confirming simply
    replaces the pending secret."""
    db.execute(
        "UPDATE users SET totp_secret = %s WHERE id = %s",
        (secret, user_id),
    )


def enable_totp(user_id):
    """Turn on 2FA for a user once they've proven they can generate a
    valid code from the secret set_totp_secret() stored. Returns True
    if a matching user was found and updated."""
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET totp_enabled = true WHERE id = %s", (user_id,))
            updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


def disable_totp(user_id):
    """Turn off 2FA and clear the stored secret, so a later re-enrolment
    starts from a fresh secret rather than reusing the old one."""
    db.execute(
        "UPDATE users SET totp_enabled = false, totp_secret = NULL WHERE id = %s",
        (user_id,),
    )


LOG_CATEGORIES = ("sign_in", "accounts", "alerts", "pipeline")


def log_category(action):
    """Which Activity log area an event belongs to: sign-ins and security, user accounts,
    alerts or the data pipeline. db/add_log_categories.py applies the same rules to old rows."""
    if action.startswith(("login_", "totp_")) or action == "password_reset_completed":
        return "sign_in"
    if action.startswith("alert_") or action == "rainfall_warning":
        return "alerts"
    if action.startswith(("reading_", "source_")):
        return "pipeline"
    return "accounts"


def log_event(actor, action, detail=None):
    """Append one row to system_logs, filed under its area. actor is a username, or None
    for a sign-in attempt that never matched a real account."""
    db.execute(
        "INSERT INTO system_logs (actor, action, detail, category) VALUES (%s, %s, %s, %s)",
        (actor, action, detail, log_category(action)),
    )
