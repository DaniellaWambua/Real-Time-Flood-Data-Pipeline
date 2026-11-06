"""
Flask app factory for the backend.

Run directly for local development:
    cd backend
    pip install -r requirements.txt
    python app.py
"""

from flask import Flask
from flask_cors import CORS

import config
from routes_auth import auth_bp
from routes_dashboard import dashboard_bp
from routes_detection import detection_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    # supports_credentials so the React dev server can send/receive the
    # session cookie set by routes_auth.py's /login.
    CORS(app, supports_credentials=True, origins=config.FRONTEND_ORIGINS)

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(detection_bp)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=config.API_PORT)
