"""
User-related queries against the `users` table (db/init/02_schema.sql),
plus system_logs writes (the System Administration screen's log panel).

Kept separate from db.py so routes_auth.py can import just what it needs
(user lookups) without pulling in the lower-level query helpers directly.
"""

from werkzeug.security import check_password_hash, generate_password_hash

import db


def get_user_by_username(username):
    """Return the user row (dict) for a username, or None if not found."""
    return db.query_one(
        "SELECT id, username, password_hash, role, is_active, created_at "
        "FROM users WHERE username = %s",
        (username,),
    )


def get_user_by_id(user_id):
    """Return the user row (dict) for a user id, or None if not found."""
    return db.query_one(
        "SELECT id, username, password_hash, role, is_active, created_at "
        "FROM users WHERE id = %s",
        (user_id,),
    )


def verify_password(user, plain_password):
    """Check a plain-text password against a user row's stored hash."""
    return check_password_hash(user["password_hash"], plain_password)


def create_user(username, plain_password, role):
    """Insert a new user with a hashed password. Returns the new user's id."""
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
                "INSERT INTO users (username, password_hash, role) "
                "VALUES (%s, %s, %s) RETURNING id",
                (username, password_hash, role),
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
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


def log_event(actor, action, detail=None):
    """Append one row to system_logs (the System Administration screen's
    log panel, proposal 3.4.6). actor is a username, or None for a
    login attempt that never resolved to a real account."""
    db.execute(
        "INSERT INTO system_logs (actor, action, detail) VALUES (%s, %s, %s)",
        (actor, action, detail),
    )
