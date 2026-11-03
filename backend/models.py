"""
User-related queries against the `users` table (db/init/02_schema.sql),
plus system_logs writes (the System Administration screen's log panel).

Kept separate from db.py so routes_auth.py can import just what it needs
(user lookups) without pulling in the lower-level query helpers directly.
"""

from werkzeug.security import check_password_hash, generate_password_hash

import db


def get_user_by_username(username):
    """Return the user row (dict) for a username, or None if not found.
    Includes totp_secret/totp_enabled (db/add_2fa_columns.py) so
    routes_auth.py can decide whether a login needs a second step, and
    email (db/add_google_signin_columns.py) for the admin-facing user
    list."""
    return db.query_one(
        "SELECT id, username, password_hash, role, is_active, created_at, "
        "       totp_secret, totp_enabled, email "
        "FROM users WHERE username = %s",
        (username,),
    )


def get_user_by_id(user_id):
    """Return the user row (dict) for a user id, or None if not found."""
    return db.query_one(
        "SELECT id, username, password_hash, role, is_active, created_at, "
        "       totp_secret, totp_enabled, email "
        "FROM users WHERE id = %s",
        (user_id,),
    )


def get_user_by_email(email):
    """Return the user row (dict) for a Google-verified email, or None.
    Used only by routes_auth.py's POST /login/google: an email with no
    matching row here means no admin-provisioned account exists for it,
    which is what keeps Google Sign-In from becoming public
    registration."""
    return db.query_one(
        "SELECT id, username, password_hash, role, is_active, created_at, "
        "       totp_secret, totp_enabled, email "
        "FROM users WHERE email = %s",
        (email,),
    )


def verify_password(user, plain_password):
    """Check a plain-text password against a user row's stored hash."""
    return check_password_hash(user["password_hash"], plain_password)


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


def log_event(actor, action, detail=None):
    """Append one row to system_logs (the System Administration screen's
    log panel, proposal 3.4.6). actor is a username, or None for a
    login attempt that never resolved to a real account."""
    db.execute(
        "INSERT INTO system_logs (actor, action, detail) VALUES (%s, %s, %s)",
        (actor, action, detail),
    )
