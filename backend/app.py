"""
Flask app factory for the backend.

Run directly for local development:
    cd backend
    pip install -r requirements.txt
    python app.py
"""

import datetime
import os

from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

import config
import security
from routes_auth import auth_bp
from routes_anomalies import anomalies_bp
from routes_dashboard import dashboard_bp
from routes_detection import detection_bp
from routes_users import users_bp
from routes_logs import logs_bp
from routes_incidents import incidents_bp
from routes_notifications import notifications_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY
    app.config.update(
        # HttpOnly keeps the cookie away from page scripts; SameSite=Strict means the browser never
        # sends it with a request started by another site; Secure keeps it off plain HTTP.
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=config.SECURE_COOKIES,
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=config.SESSION_HOURS),
        RATE_LIMITS=config.RATE_LIMITS,
        MAX_CONTENT_LENGTH=1024 * 1024,  # no request here needs more than a few kilobytes
    )
    if config.TRUSTED_PROXIES:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=config.TRUSTED_PROXIES)
    app.before_request(security.require_json)

    # supports_credentials so the React dev server can send/receive the
    # session cookie set by routes_auth.py's /login.
    CORS(app, supports_credentials=True, origins=config.FRONTEND_ORIGINS)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(anomalies_bp)
    app.register_blueprint(detection_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(incidents_bp)
    app.register_blueprint(notifications_bp)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    # Local development only (production runs Gunicorn). The debugger can run code, so the server
    # listens on this computer alone; set FLASK_DEBUG=0 to turn the debugger off.
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", host="127.0.0.1", port=config.API_PORT)
