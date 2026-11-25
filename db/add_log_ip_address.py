"""
Migration adding the client address to the activity log (a fresh database gets it from
db/init/02_schema.sql). Safe to re-run. From db/:

    python add_log_ip_address.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402


def add_log_ip_address():
    db.execute("ALTER TABLE system_logs ADD COLUMN IF NOT EXISTS ip_address TEXT")
    print("system_logs.ip_address: present.")


if __name__ == "__main__":
    add_log_ip_address()
