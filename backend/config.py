import os
from pathlib import Path

from dotenv import load_dotenv

# Settings come from backend/.env when it exists (kept out of git), then from the
# environment; backend/.env.example lists every setting.
load_dotenv(Path(__file__).resolve().parent / ".env")


def _env(name, default=""):
    """A setting's value, or the default when it is unset or left blank in backend/.env."""
    return os.environ.get(name) or default


def _required(name):
    """A secret with no default: refuse to start when it is missing."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set; add it to backend/.env (see backend/.env.example)")
    return value

DB_HOST = _env("DB_HOST", "localhost")
DB_PORT = _env("DB_PORT", "5432")
DB_NAME = _env("DB_NAME", "flood_pipeline")
DB_USER = _env("DB_USER", "flood_pipeline")
DB_PASSWORD = _required("DB_PASSWORD")

SECRET_KEY = _required("SECRET_KEY")
INTERNAL_API_TOKEN = _required("INTERNAL_API_TOKEN")

# Not 5000: the macOS AirPlay Receiver listens there and answers with its own 403.
API_PORT = int(_env("API_PORT", "5001"))

# Actor roles
ROLES = [
    "disaster_management_agency",
    "emergency_responder",
    "government_official",
    "system_administrator",
]

# Origins allowed to call the API (the Vite and Create React App dev servers by default).
FRONTEND_ORIGINS = _env(
    "FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

# OAuth client ID from Google Cloud Console; must match the frontend's VITE_GOOGLE_CLIENT_ID.
# Google sign-in is off while it is unset.
GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID", "")

# Email (invites and password resets), sent through an SMTP account such as Gmail
# with an app password. Inviting or resetting fails clearly while these are unset.
SMTP_HOST = _env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_env("SMTP_PORT", "587"))
SMTP_USERNAME = _env("SMTP_USERNAME", "")
SMTP_PASSWORD = _env("SMTP_PASSWORD", "").replace(" ", "")
MAIL_FROM_NAME = _env("MAIL_FROM_NAME", "Flood Early Warning")
MAIL_FROM_ADDRESS = _env("MAIL_FROM_ADDRESS", "") or SMTP_USERNAME

# Where the links in emails point (the React app), and how long they last
FRONTEND_URL = _env("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# Web Push keys (python generate_vapid_keys.py). Without them notifications still appear in the app.
VAPID_PUBLIC_KEY = _env("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = _env("VAPID_PRIVATE_KEY", "")
# Field roles are told about a verified incident only if its last day is this recent, so verifying a
# replayed year does not notify anyone
NOTIFY_WITHIN_DAYS = int(_env("NOTIFY_WITHIN_DAYS", "60"))
VAPID_SUBJECT = _env("VAPID_SUBJECT", "mailto:" + (_env("MAIL_FROM_ADDRESS", "") or "admin@example.org"))
INVITE_LINK_HOURS = int(_env("INVITE_LINK_HOURS", "72"))
RESET_LINK_HOURS = int(_env("RESET_LINK_HOURS", "2"))
