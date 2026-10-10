"""
User-related queries against the `users` table (db/init/02_schema.sql).

Kept separate from db.py so routes_auth.py can import just what it needs
(user lookups) without pulling in the lower-level query helpers directly.
"""

from werkzeug.security import check_password_hash, generate_password_hash

import db


def get_user_by_username(username):
    """Return the user row (dict) for a username, or None if not found."""
    return db.query_one(
        "SELECT id, username, password_hash, role, created_at "
        "FROM users WHERE username = %s",
        (username,),
    )


def get_user_by_id(user_id):
    """Return the user row (dict) for a user id, or None if not found."""
    return db.query_one(
        "SELECT id, username, password_hash, role, created_at "
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
