"""
config.py – Configuration for SIH26083 backend.

Only base settings needed for local development are defined here.
Additional configuration (auth, external APIs, ML, GIS)
will be added in future sprints.
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


class DevelopmentConfig(Config):
    """Local development configuration."""

    DEBUG = True


# Active configuration mapping
config = {
    "development": DevelopmentConfig,
    "default": DevelopmentConfig,
}
