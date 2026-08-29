"""
config.py – Configuration for SIH26083 backend.

Only base settings needed for local development are defined here.
Additional configuration (auth, ML, GIS) will be added in future sprints.
"""

import os

# Absolute path to the directory that contains this file (backend/)
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration."""

    DEBUG = False
    TESTING = False

    # ---------------------------------------------------------------------- #
    # Database – SQLite (local development)                                   #
    # Replace SQLALCHEMY_DATABASE_URI in a subclass to use a different DB.   #
    # ---------------------------------------------------------------------- #
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
        _BASE_DIR, "sih26083.db"
    )
    # Disable Flask-SQLAlchemy's event-tracking overhead (not needed here)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ---------------------------------------------------------------------- #
    # Weather API – values come from environment variables.                   #
    # Never hard-code credentials here.                                       #
    # ---------------------------------------------------------------------- #
    # Base URL for the weather data provider (swap to any compatible API).
    WEATHER_API_BASE_URL: str = os.environ.get(
        "WEATHER_API_BASE_URL",
        "https://api.open-meteo.com/v1",  # open, no-key default for dev
    )
    # Optional API key – leave blank/unset when using keyless endpoints.
    WEATHER_API_KEY: str = os.environ.get("WEATHER_API_KEY", "")
    # Seconds to wait before aborting a weather API request.
    WEATHER_API_TIMEOUT: int = int(os.environ.get("WEATHER_API_TIMEOUT", "10"))
    # Seconds between consecutive weather collection cycles (default 15 min).
    WEATHER_COLLECTION_INTERVAL: int = int(
        os.environ.get("WEATHER_COLLECTION_INTERVAL", "900")
    )

    # ---------------------------------------------------------------------- #
    # Heatwave Risk Thresholds (Prototype v0.6)                              #
    # ---------------------------------------------------------------------- #
    # ---------------------------------------------------------------------- #
    # ML artifacts – generated files are gitignored; never store credentials. #
    # ---------------------------------------------------------------------- #
    ML_ARTIFACT_DIR: str = os.environ.get(
        "ML_ARTIFACT_DIR",
        os.path.join(_BASE_DIR, "artifacts", "models"),
    )
    ML_ARTIFACT_VERSION: str = os.environ.get("ML_ARTIFACT_VERSION", "v0.16")

    # ---------------------------------------------------------------------- #
    # Development CORS (SIH26083 v0.17 prototype only)                       #
    # ---------------------------------------------------------------------- #
    # Enable permissive development CORS for React/Vite frontends running on
    # localhost.  This is clearly marked as prototype/dev behaviour and is
    # not intended for production deployments.  Set explicitly to ``false``
    # to disable.
    DEV_CORS_ENABLED: bool = os.environ.get("DEV_CORS_ENABLED", "true").lower() not in (
        "false",
        "0",
        "no",
        "off",
    )

    # ---------------------------------------------------------------------- #
    # Weather scheduler lifecycle (SIH26083 v0.17 demo glue)                 #
    # ---------------------------------------------------------------------- #
    # When ``true`` the application factory will start one WeatherScheduler
    # per configured Area after the database tables are ready.  Defaults to
    # ``false`` so pytest and other test-style app creations never spawn
    # background threads unexpectedly.  Flask's reloader can double-process
    # start-up; use ``flask run --no-reload`` or rely on the WERKZEUG_RUN_MAIN
    # guard inside create_app() to avoid duplicate scheduler threads.
    WEATHER_SCHEDULER_ENABLED: bool = (
        os.environ.get("WEATHER_SCHEDULER_ENABLED", "false").lower()
        in ("true", "1", "yes", "on")
    )

    # ---------------------------------------------------------------------- #
    # Heatwave Risk Thresholds (Prototype v0.6)                              #
    # ---------------------------------------------------------------------- #
    HEATWAVE_RISK_THRESHOLDS = {
        "TEMP_MIN": 32.0,           # Minimum temp (°C) to start scoring
        "TEMP_MODERATE": 35.0,      # Temp for moderate base risk
        "TEMP_HIGH": 38.0,          # Temp for high base risk
        "TEMP_EXTREME": 42.0,       # Temp for extreme base risk
        "HUMIDITY_HIGH": 60.0,      # Humidity % adding moderate risk
        "HUMIDITY_EXTREME": 80.0,   # Humidity % adding high risk
        "WIND_STAGNANT": 5.0,       # Wind speed (km/h) increasing risk
        "WIND_BREEZE": 20.0,        # Wind speed (km/h) reducing risk
    }

class DevelopmentConfig(Config):
    """Local development configuration."""

    DEBUG = True


# Active configuration mapping
config = {
    "development": DevelopmentConfig,
    "default": DevelopmentConfig,
}
