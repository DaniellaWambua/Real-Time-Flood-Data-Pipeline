"""
Minimal database connection helper for the ingestion/stream processing
layer. Deliberately self-contained (not shared with backend/db.py): both
live in a folder with their own config.py, and importing across folders
by manipulating sys.path caused the two config modules to shadow each
other. Same small query_one/query_all/execute pattern as backend/db.py,
just kept local to this layer.
"""

import psycopg2
import psycopg2.extras

import config


def get_connection():
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def query_one(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            row = cur.fetchone()
            return dict(row) if row is not None else None
    finally:
        conn.close()


def query_all(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    finally:
        conn.close()


def execute(sql, params=None):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
        conn.commit()
    finally:
        conn.close()
