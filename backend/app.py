"""
Flask app factory for the backend.

Run directly for local development:
    cd backend
    pip install -r requirements.txt
    python app.py
"""

from flask import Flask

import config
from routes_auth import auth_bp


def create_app():
    app = Flask(__name__)
    app.secret_key = config.SECRET_KEY

    app.register_blueprint(auth_bp)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
