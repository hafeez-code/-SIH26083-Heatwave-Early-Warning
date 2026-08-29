"""Validation, persistence, and feature preparation for historical weather data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Iterable, Mapping, Optional

from models.database_models import Area, WeatherObservation
from services.forecast_features import build_forecast_features


class HistoricalDataError(ValueError):
    """Raised when a historical weather record is incomplete or implausible."""


@dataclass(frozen=True)
class NormalisedHistoricalObservation:
    """Provider-neutral historical weather data associated with one Area."""

    area_id: int
    observation_timestamp: str
    temperature: Optional[float]
    humidity: Optional[float]
    wind_speed: Optional[float]
    precipitation: Optional[float]

    @property
    def forecast_timestamp(self) -> str:
        """Compatibility alias used by the shared v0.11 feature service."""
        return self.observation_timestamp


def _value(record: object, name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def _canonical_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise HistoricalDataError("observation_timestamp must be a non-empty ISO-8601 string.")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalDataError("observation_timestamp must be a valid ISO-8601 timestamp.") from exc
    return timestamp.isoformat()


def _optional_measurement(value: object, field: str) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise HistoricalDataError(f"{field} must be numeric when provided.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalDataError(f"{field} must be numeric when provided.") from exc
    if not isfinite(result):
        raise HistoricalDataError(f"{field} must be finite when provided.")
    return result


def normalise_historical_observation(record: object) -> NormalisedHistoricalObservation:
    """Validate and normalise one provider-neutral historical observation.

    Measurements may be null because historical sources can be incomplete; no
    value is imputed.  Conservative physical checks reject invalid humidity,
    negative wind/precipitation, and temperatures outside a global weather
    range while allowing ordinary extreme heat observations.
    """
    area_id = _value(record, "area_id")
    if isinstance(area_id, bool) or not isinstance(area_id, int) or area_id < 1:
        raise HistoricalDataError("area_id must be a positive integer.")
    timestamp = _canonical_timestamp(_value(record, "observation_timestamp"))
    temperature = _optional_measurement(_value(record, "temperature"), "temperature")
    humidity = _optional_measurement(_value(record, "humidity"), "humidity")
    wind_speed = _optional_measurement(_value(record, "wind_speed"), "wind_speed")
    precipitation = _optional_measurement(_value(record, "precipitation"), "precipitation")
    if temperature is not None and not -90.0 <= temperature <= 70.0:
        raise HistoricalDataError("temperature is outside the accepted physical range.")
    if humidity is not None and not 0.0 <= humidity <= 100.0:
        raise HistoricalDataError("humidity must be between 0 and 100.")
    if wind_speed is not None and wind_speed < 0.0:
        raise HistoricalDataError("wind_speed cannot be negative.")
    if precipitation is not None and precipitation < 0.0:
        raise HistoricalDataError("precipitation cannot be negative.")
    return NormalisedHistoricalObservation(
        area_id=area_id,
        observation_timestamp=timestamp,
        temperature=temperature,
        humidity=humidity,
        wind_speed=wind_speed,
        precipitation=precipitation,
    )


def normalise_historical_observations(records: Iterable[object]) -> list[NormalisedHistoricalObservation]:
    """Return area-isolated observations in stable chronological order."""
    return sorted(
        (normalise_historical_observation(record) for record in records),
        key=lambda record: (record.area_id, record.observation_timestamp),
    )


def persist_historical_observations(
    records: Iterable[NormalisedHistoricalObservation], db_session
) -> list[WeatherObservation]:
    """Idempotently stage historical observations using ``(area_id, timestamp)``.

    Existing rows are updated in place; the caller owns the transaction.  The
    existing ``WeatherObservation`` schema has no source field, so source
    provenance remains the importer caller's responsibility rather than being
    invented or stored in an unrelated column.
    """
    persisted = []
    cache: dict[tuple[int, str], WeatherObservation] = {}
    for observation in normalise_historical_observations(records):
        key = (observation.area_id, observation.observation_timestamp)
        record = cache.get(key)
        if record is None:
            area = db_session.get(Area, observation.area_id)
            if area is None:
                raise HistoricalDataError(f"Area {observation.area_id} does not exist.")
            record = (
                WeatherObservation.query.filter_by(
                    area_id=observation.area_id,
                    timestamp=observation.observation_timestamp,
                )
                .order_by(WeatherObservation.id.asc())
                .first()
            )
            if record is None:
                record = WeatherObservation(
                    area_id=area.id,
                    latitude=area.latitude,
                    longitude=area.longitude,
                    timestamp=observation.observation_timestamp,
                )
                db_session.add(record)
            cache[key] = record
        record.temperature = observation.temperature
        record.humidity = observation.humidity
        record.wind_speed = observation.wind_speed
        record.precipitation = observation.precipitation
        persisted.append(record)
    return persisted


def prepare_historical_features(records: Iterable[object]) -> list[dict]:
    """Create v0.11-derived features for historical records without duplication."""
    normalised = normalise_historical_observations(records)
    features = build_forecast_features(normalised)
    return [
        {**feature, "area_id": observation.area_id}
        for feature, observation in zip(features, normalised)
    ]
