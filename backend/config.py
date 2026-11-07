import os
from pathlib import Path

from dotenv import load_dotenv

# Settings come from backend/.env when it exists (kept out of git), then from the
# environment; backend/.env.example lists every setting.
load_dotenv(Path(__file__).resolve().parent / ".env")


def _env(name, default=""):
    """A setting's value, or the default when it is unset or left blank in backend/.env."""
    return os.environ.get(name) or default

# Matches db/docker-compose.yml's defaults; override with real values in
# production via environment variables, never commit real credentials here.
DB_HOST = _env("DB_HOST", "localhost")
DB_PORT = _env("DB_PORT", "5432")
DB_NAME = _env("DB_NAME", "flood_pipeline")
DB_USER = _env("DB_USER", "flood_pipeline")
DB_PASSWORD = _env("DB_PASSWORD", "flood_pipeline_dev")

SECRET_KEY = _env("SECRET_KEY", "dev-secret-change-before-deploying")
INTERNAL_API_TOKEN = _env("INTERNAL_API_TOKEN", "dev-internal-token-change-before-deploying")

# Not 5000: macOS's AirPlay Receiver (System Settings, General, AirDrop
# and Handoff) also listens on 127.0.0.1:5000 and answers with its own
# 403 page before Flask ever sees the request, which looks like an auth
# failure but is not one. Override via env if 5001 is also taken.
API_PORT = int(_env("API_PORT", "5001"))

# Actor roles, per Chapter 3's use case diagram.
ROLES = [
    "disaster_management_agency",
    "emergency_responder",
    "government_official",
    "system_administrator",
]

# The dashboard's React dev server. Vite's default port (5173) and
# Create React App's default port (3000) are both allowed out of the
# box; override via env if the frontend ends up running elsewhere.
FRONTEND_ORIGINS = _env(
    "FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")

# Google Sign-In (routes_auth.py's POST /login/google): the OAuth 2.0
# Client ID from Google Cloud Console (APIs & Services, Credentials),
# needed to verify that an incoming ID token was actually issued for
# this app, not some other one. Must match the frontend's
# VITE_GOOGLE_CLIENT_ID exactly, since that is the client id Google
# Identity Services stamps into the token's audience claim. Login with
# Google is disabled (the endpoint returns an error) while this is unset.
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
INVITE_LINK_HOURS = int(_env("INVITE_LINK_HOURS", "72"))
RESET_LINK_HOURS = int(_env("RESET_LINK_HOURS", "2"))
