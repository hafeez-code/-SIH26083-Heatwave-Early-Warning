"""
app.py – Flask application entry point for SIH26083.

Sprint 1: Minimal backend foundation with health-check endpoint.
Sprint 2: Database foundation (Flask-SQLAlchemy + SQLite, Area model).
"""

from flask import Flask, jsonify
from sqlalchemy import inspect

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
        # create_all does not add columns to an existing SQLite database.
        # This non-destructive upgrade keeps local v0.8 databases usable.
        if db.engine.dialect.name == "sqlite":
            columns = {column["name"] for column in inspect(db.engine).get_columns("weather_observation")}
            if "area_id" not in columns:
                with db.engine.begin() as connection:
                    connection.exec_driver_sql(
                        "ALTER TABLE weather_observation ADD COLUMN area_id INTEGER REFERENCES area(id)"
                    )

    # ------------------------------------------------------------------ #
    # Routes                                                               #
    # ------------------------------------------------------------------ #
    from routes.risk import risk_bp
    from routes.areas import areas_bp
    from routes.weather import weather_bp
    from routes.prediction import prediction_bp
    app.register_blueprint(risk_bp)
    app.register_blueprint(areas_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(prediction_bp)

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
