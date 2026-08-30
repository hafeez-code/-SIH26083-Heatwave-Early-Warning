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

    # ---------------------------------------------------------------------- #
    # Human Thermal Stress Index Thresholds (SIH26083 v0.19)                 #
    # Based on Rothfusz Heat Index methodology (NWS standard).               #
    # Heat index values in °C; scores map to 0–100 environmental indicator.  #
    # PROTOTYPE: Not a clinically validated medical diagnosis.                #
    # ---------------------------------------------------------------------- #
    THERMAL_STRESS_THRESHOLDS = {
        "HI_LOW": 27.0,        # Heat index (°C) below which stress is LOW
        "HI_MODERATE": 32.0,   # Heat index (°C) for MODERATE stress onset
        "HI_HIGH": 41.0,       # Heat index (°C) for HIGH stress onset
        "HI_VERY_HIGH": 54.0,  # Heat index (°C) for VERY HIGH stress onset
        # Score boundaries for each stress band (0–100 scale)
        "SCORE_LOW": 15,
        "SCORE_MODERATE": 35,
        "SCORE_HIGH": 60,
        "SCORE_VERY_HIGH": 80,
        "SCORE_EXTREME": 95,
        # Wind cooling: subtract from score when wind > threshold
        "WIND_COOLING_THRESHOLD": 20.0,  # km/h
        "WIND_COOLING_BONUS": 5,         # score points subtracted
        # Solar radiation: add to score when radiation > threshold
        "SOLAR_HIGH_THRESHOLD": 600.0,   # W/m²
        "SOLAR_SCORE_BONUS": 5,          # score points added
    }

    # ---------------------------------------------------------------------- #
    # Mortality / Vulnerability Risk Index (SIH26083 v0.19)                  #
    # Explicit weights for the transparent weighted-combination formula.      #
    # PROTOTYPE: not a medically validated mortality probability.             #
    # ---------------------------------------------------------------------- #
    MORTALITY_RISK_WEIGHTS = {
        # Contribution of thermal stress score to the base risk score
        "W_THERMAL": 0.5,
        # Contribution of heatwave risk score to the base risk score
        "W_HEATWAVE": 0.5,
        # Vulnerability amplification per percentage point of elderly population
        "W_ELDERLY": 0.8,
        # Vulnerability amplification per percentage point of children population
        "W_CHILDREN": 0.4,
    }

    MORTALITY_RISK_THRESHOLDS = {
        "SCORE_LOW": 30,       # Scores below this → LOW
        "SCORE_MODERATE": 55,  # Scores below this → MODERATE
        "SCORE_HIGH": 75,      # Scores below this → HIGH
        # Scores at or above HIGH threshold → EXTREME
    }

class DevelopmentConfig(Config):
    """Local development configuration."""

    DEBUG = True


# Active configuration mapping
config = {
    "development": DevelopmentConfig,
    "default": DevelopmentConfig,
}
