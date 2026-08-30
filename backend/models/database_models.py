"""
database_models.py – SQLAlchemy ORM models for SIH26083.

Sprint 2: Database foundation – Area model.
Sprint 3: Weather ingestion – WeatherObservation model added.
v0.19:   AreaDemographics model, solar_radiation field added.
         All new columns nullable for backward compatibility.
         No PII stored – demographics are aggregate area-level only.

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
    forecast_observations = db.relationship(
        "ForecastObservation",
        back_populates="area",
    )
    historical_event_labels = db.relationship(
        "HistoricalEventLabel",
        back_populates="area",
    )
    demographics = db.relationship(
        "AreaDemographics",
        back_populates="area",
        uselist=False,  # one-to-one
        cascade="all, delete-orphan",
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
    # Solar radiation – nullable; never fabricated if provider does not supply it.
    solar_radiation = db.Column(db.Float, nullable=True)  # W/m²

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


class ForecastObservation(db.Model):
    """A provider forecast for one Area at a future provider timestamp."""

    __tablename__ = "forecast_observation"
    __table_args__ = (
        db.UniqueConstraint("area_id", "forecast_timestamp", name="uq_forecast_area_timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"), nullable=False)
    forecast_timestamp = db.Column(db.Text, nullable=False)
    temperature = db.Column(db.Float, nullable=True)
    humidity = db.Column(db.Float, nullable=True)
    wind_speed = db.Column(db.Float, nullable=True)
    precipitation = db.Column(db.Float, nullable=True)
    # Solar radiation forecast – nullable; only populated when provider supplies it.
    solar_radiation = db.Column(db.Float, nullable=True)  # W/m²
    ingested_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
    )

    area = db.relationship("Area", back_populates="forecast_observations")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ForecastObservation id={self.id} area_id={self.area_id} "
            f"timestamp={self.forecast_timestamp!r}>"
        )


class HistoricalEventLabel(db.Model):
    """An independently supplied, validated event label for a historical Area time."""

    __tablename__ = "historical_event_label"
    __table_args__ = (
        db.UniqueConstraint(
            "area_id",
            "event_timestamp",
            "label_name",
            name="uq_historical_label_area_timestamp_name",
        ),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    area_id = db.Column(db.Integer, db.ForeignKey("area.id"), nullable=False)
    event_timestamp = db.Column(db.Text, nullable=False)
    label_name = db.Column(db.String(100), nullable=False)
    label_value = db.Column(db.Integer, nullable=False)
    label_source = db.Column(db.String(255), nullable=False)
    source_reference = db.Column(db.String(255), nullable=False)
    validation_status = db.Column(db.String(50), nullable=False)
    provenance_type = db.Column(db.String(50), nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
    )

    area = db.relationship("Area", back_populates="historical_event_labels")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HistoricalEventLabel id={self.id} area_id={self.area_id} "
            f"timestamp={self.event_timestamp!r} name={self.label_name!r}>"
        )


class AreaDemographics(db.Model):
    """Aggregate area-level demographic vulnerability information.

    IMPORTANT: This model stores ONLY population-level aggregates.
    No personally identifiable information (PII) is stored here.
    Data should come from authoritative public sources (census, local govt).

    One record per Area (one-to-one relationship enforced by unique constraint).
    All demographic fields are nullable – an area can exist without demographics.
    """

    __tablename__ = "area_demographics"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    area_id = db.Column(
        db.Integer,
        db.ForeignKey("area.id"),
        nullable=False,
        unique=True,  # one record per area
    )

    # Aggregate population count – purely optional, used for context only.
    population_total = db.Column(db.Integer, nullable=True)

    # Percentage of population in high-vulnerability age groups (0.0–100.0).
    # These are AGGREGATE statistics, not individual records.
    pct_elderly = db.Column(db.Float, nullable=True)   # % aged ≥65
    pct_children = db.Column(db.Float, nullable=True)  # % aged <18

    # Free-text notes on known local vulnerability factors (e.g. slum density,
    # outdoor worker proportion). Optional field for SIH demo context.
    vulnerability_notes = db.Column(db.Text, nullable=True)

    # Audit timestamp
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    area = db.relationship("Area", back_populates="demographics")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AreaDemographics id={self.id} area_id={self.area_id} "
            f"pct_elderly={self.pct_elderly} pct_children={self.pct_children}>"
        )
