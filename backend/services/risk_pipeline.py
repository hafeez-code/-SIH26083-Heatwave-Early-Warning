"""Persistence orchestration for the weather-to-risk pipeline."""

from __future__ import annotations

import json

from models.database_models import HeatwaveRiskAssessment, WeatherObservation
from services.data_ingestion import NormalisedObservation, save_observation
from services.heatwave_risk import calculate_risk


def _as_normalised_observation(record: WeatherObservation) -> NormalisedObservation:
    """Build the scoring input from the persisted observation values."""
    return NormalisedObservation(
        latitude=record.latitude,
        longitude=record.longitude,
        timestamp=record.timestamp,
        temperature=record.temperature,
        humidity=record.humidity,
        wind_speed=record.wind_speed,
        precipitation=record.precipitation,
    )


def persist_observation_and_risk(
    observation: NormalisedObservation,
    db_session,
    thresholds: dict | None = None,
    area_id: int | None = None,
) -> tuple[WeatherObservation, HeatwaveRiskAssessment]:
    """Stage a weather observation and its deterministic assessment.

    This function deliberately does not commit.  Its caller owns one atomic
    transaction so an observation is never retained without its risk record.
    """
    weather_record = save_observation(observation, db_session, area_id=area_id)
    db_session.flush()

    assessment = calculate_risk(
        _as_normalised_observation(weather_record), thresholds=thresholds
    )
    risk_record = HeatwaveRiskAssessment(
        weather_observation=weather_record,
        risk_score=assessment.risk_score,
        risk_level=assessment.risk_level,
        contributing_factors=json.dumps(assessment.contributing_factors),
    )
    db_session.add(risk_record)
    return weather_record, risk_record
