"""
app.py – Flask application entry point for SIH26083.

Sprint 1: Minimal backend foundation with health-check endpoint.
Sprint 2: Database foundation (Flask-SQLAlchemy + SQLite, Area model).
"""

from flask import Flask, jsonify

from config import config
from models.database_models import db


def create_app(config_name="default"):
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ------------------------------------------------------------------ #
    # Extensions                                                           #
    # ------------------------------------------------------------------ #
    db.init_app(app)

    # Create tables if they do not exist yet (local dev / first run).
    # Replace with Flask-Migrate in a later sprint before going to production.
    with app.app_context():
        db.create_all()

    # ------------------------------------------------------------------ #
    # Routes                                                               #
    # ------------------------------------------------------------------ #
    from routes.risk import risk_bp
    app.register_blueprint(risk_bp)

    # ------------------------------------------------------------------ #
    # Health-check endpoint                                                #
    # ------------------------------------------------------------------ #
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify(
            {
                "status": "success",
                "message": "SIH26083 backend is running",
            }
        )

    return app


# Local development entry point
if __name__ == "__main__":
    app = create_app("development")
    app.run(host="127.0.0.1", port=5000)
