"""
One-off migration that files every system_logs row under its Activity log area, for a
database created before 02_schema.sql had the category column. Safe to run more than once.
Run from the db/ directory: python add_log_categories.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
import db  # noqa: E402

db.execute("ALTER TABLE system_logs ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'accounts'")
# Same rules as backend/models.py log_category()
db.execute(
    "UPDATE system_logs SET category = CASE "
    "WHEN action LIKE 'login\\_%%' OR action LIKE 'totp\\_%%' OR action IN ('password_reset_completed', 'password_changed', 'password_change_failure') THEN 'sign_in' "
    "WHEN action LIKE 'alert\\_%%' THEN 'alerts' "
    "WHEN action LIKE 'reading\\_%%' THEN 'pipeline' "
    "ELSE 'accounts' END"
)
db.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_category ON system_logs (category, id DESC)")
for row in db.query_all("SELECT category, COUNT(*) AS n FROM system_logs GROUP BY 1 ORDER BY 1"):
    print(f"{row['category']}: {row['n']}")
