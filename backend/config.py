import os

# Matches db/docker-compose.yml's defaults; override with real values in
# production via environment variables, never commit real credentials here.
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "flood_pipeline")
DB_USER = os.environ.get("DB_USER", "flood_pipeline")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "flood_pipeline_dev")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-before-deploying")

# Not 5000: macOS's AirPlay Receiver (System Settings, General, AirDrop
# and Handoff) also listens on 127.0.0.1:5000 and answers with its own
# 403 page before Flask ever sees the request, which looks like an auth
# failure but is not one. Override via env if 5001 is also taken.
API_PORT = int(os.environ.get("API_PORT", "5001"))

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
FRONTEND_ORIGINS = os.environ.get(
    "FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000"
).split(",")
