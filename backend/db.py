"""
Database connection helper for the backend.

Thin wrapper around psycopg2 so the rest of the backend never has to know
connection details directly. Uses RealDictCursor so query results come back
as dicts (easier to work with in routes and templates than plain tuples).
"""

import psycopg2
import psycopg2.extras

import config


def get_connection():
    """Open a new connection to the flood_pipeline database."""
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def query_one(sql, params=None):
    """Run a query and return a single row as a dict, or None if no match."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return dict(row) if row is not None else None
    finally:
        conn.close()


def query_all(sql, params=None):
    """Run a query and return all matching rows as a list of dicts."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def execute(sql, params=None):
    """Run an INSERT/UPDATE/DELETE statement and commit."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    finally:
        conn.close()
