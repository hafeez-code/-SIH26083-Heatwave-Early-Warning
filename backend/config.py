"""
config.py – Minimal configuration for SIH26083 backend.

Only base settings needed for local development are defined here.
Additional configuration (database, auth, external APIs, ML, GIS)
will be added in future sprints.
"""


class Config:
    """Base configuration."""

    DEBUG = False
    TESTING = False


class DevelopmentConfig(Config):
    """Local development configuration."""

    DEBUG = True


# Active configuration mapping
config = {
    "development": DevelopmentConfig,
    "default": DevelopmentConfig,
}
