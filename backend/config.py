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


class DevelopmentConfig(Config):
    """Local development configuration."""

    DEBUG = True


# Active configuration mapping
config = {
    "development": DevelopmentConfig,
    "default": DevelopmentConfig,
}
