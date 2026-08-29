"""
database_models.py – SQLAlchemy ORM models for SIH26083.

Sprint 2: Database foundation – Area model.
Sprint 3: Weather ingestion – WeatherObservation model added.

Only models needed by the current sprint are defined here.
"""

from flask_sqlalchemy import SQLAlchemy

# Shared SQLAlchemy extension instance.
# Imported by app.py for initialisation and by models for db.Model.
db = SQLAlchemy()


class Area(db.Model):
    """A geographic area monitored for heatwave risk."""

    __tablename__ = "area"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    observations = db.relationship(
        "WeatherObservation",
        back_populates="area",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Area id={self.id} name={self.name!r}>"


class WeatherObservation(db.Model):
    """A single normalised weather observation for a geographic point.

    Fields map directly to the NormalisedObservation dataclass produced
    by the data_ingestion service.  All measurement columns are nullable
    because a real-world API response may omit any individual field.
    """

    __tablename__ = "weather_observation"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # The monitored Area, when this observation was collected for one.
    # It is nullable so existing coordinate-only ingestion remains supported.
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"), nullable=True)
    area = db.relationship("Area", back_populates="observations")

    # Location of the observation (from the API response, not the request)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    # ISO-8601 timestamp string as returned by the provider.
    # Stored as Text so the format is preserved exactly regardless of
    # timezone handling differences across SQLite and future DB backends.
    timestamp = db.Column(db.Text, nullable=False)

    # Meteorological measurements (all optional – provider may omit any)
    temperature = db.Column(db.Float, nullable=True)   # °C
    humidity = db.Column(db.Float, nullable=True)       # %
    wind_speed = db.Column(db.Float, nullable=True)     # km/h
    precipitation = db.Column(db.Float, nullable=True)  # mm

    # Audit field: when this row was written to our DB
    ingested_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
    )

    # One deterministic assessment is produced for each successfully
    # persisted observation.  The database constraint prevents duplicate
    # assessments when a collection cycle is retried.
    risk_assessment = db.relationship(
        "HeatwaveRiskAssessment",
        back_populates="weather_observation",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<WeatherObservation id={self.id} "
            f"lat={self.latitude} lon={self.longitude} "
            f"ts={self.timestamp!r}>"
        )


class HeatwaveRiskAssessment(db.Model):
    """The deterministic heatwave risk calculated from one observation."""

    __tablename__ = "heatwave_risk_assessment"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    weather_observation_id = db.Column(
        db.Integer,
        db.ForeignKey("weather_observation.id"),
        nullable=False,
        unique=True,
    )
    risk_score = db.Column(db.Integer, nullable=False)
    risk_level = db.Column(db.String(20), nullable=False)
    # JSON text keeps the schema portable to the project's SQLite database.
    contributing_factors = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
    )

    weather_observation = db.relationship(
        "WeatherObservation",
        back_populates="risk_assessment",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HeatwaveRiskAssessment id={self.id} "
            f"observation_id={self.weather_observation_id} "
            f"level={self.risk_level!r}>"
        )
