"""Persistence orchestration for the weather-to-risk pipeline.

v0.19: Extended with Human Thermal Stress and Mortality/Vulnerability
       risk integration.  The existing persist_observation_and_risk()
       function is unchanged for backward compatibility.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from models.database_models import HeatwaveRiskAssessment, WeatherObservation
from services.data_ingestion import NormalisedObservation, save_observation
from services.heatwave_risk import RiskAssessment, calculate_risk
from services.thermal_stress import ThermalStressAssessment, calculate_thermal_stress
from services.mortality_risk import (
    DemographicVulnerability,
    MortalityVulnerabilityAssessment,
    calculate_mortality_vulnerability_risk,
)


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
        solar_radiation=getattr(record, "solar_radiation", None),
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


@dataclass
class FullRiskAssessment:
    """Combined risk output from the full v0.19 pipeline.

    All layers are optional so callers can handle partial failures gracefully
    without breaking the overall response.
    """

    observation: NormalisedObservation
    heatwave_risk: RiskAssessment
    thermal_stress: Optional[ThermalStressAssessment]
    mortality_vulnerability: Optional[MortalityVulnerabilityAssessment]
    thermal_stress_error: Optional[str] = None
    mortality_error: Optional[str] = None


def run_full_risk_pipeline(
    observation: NormalisedObservation,
    demographics: Optional[DemographicVulnerability] = None,
    heatwave_thresholds: Optional[dict] = None,
    thermal_thresholds: Optional[dict] = None,
    mortality_weights: Optional[dict] = None,
    mortality_thresholds: Optional[dict] = None,
) -> FullRiskAssessment:
    """Run all risk layers for one observation without touching the database.

    This is the read-only orchestrator used by the unified early-warning
    endpoint.  It does NOT persist anything – the existing
    ``persist_observation_and_risk`` function is the persistence entry point.

    Flow:
        weather observation
             ↓
        heatwave risk (always computed; raises ValueError if temp missing)
             ↓
        human thermal stress (computed when temp available)
             ↓
        mortality/vulnerability risk (computed when both upstream scores available)

    Parameters
    ----------
    observation:
        The weather data to evaluate.
    demographics:
        Optional area-level demographic data for vulnerability amplification.
    heatwave_thresholds, thermal_thresholds, mortality_weights, mortality_thresholds:
        Optional overrides; fall back to Config values.

    Returns
    -------
    FullRiskAssessment
        Contains each layer's result or an error string explaining why it
        was skipped.  Callers should inspect ``thermal_stress_error`` and
        ``mortality_error`` to detect partial failures.
    """
    # 1. Heatwave risk (required – will raise ValueError if temp is None)
    heatwave = calculate_risk(observation, thresholds=heatwave_thresholds)

    # 2. Thermal stress (best-effort)
    thermal: Optional[ThermalStressAssessment] = None
    thermal_error: Optional[str] = None
    try:
        thermal = calculate_thermal_stress(observation, thresholds=thermal_thresholds)
    except ValueError as exc:
        thermal_error = str(exc)

    # 3. Mortality/vulnerability risk (only when both upstream scores are available)
    mortality: Optional[MortalityVulnerabilityAssessment] = None
    mortality_error: Optional[str] = None
    if thermal is not None:
        try:
            mortality = calculate_mortality_vulnerability_risk(
                thermal_stress_score=thermal.thermal_stress_score,
                heatwave_risk_score=heatwave.risk_score,
                timestamp=observation.timestamp,
                latitude=observation.latitude,
                longitude=observation.longitude,
                demographics=demographics,
                weights=mortality_weights,
                thresholds=mortality_thresholds,
            )
        except Exception as exc:  # noqa: BLE001
            mortality_error = str(exc)
    else:
        mortality_error = "Mortality risk skipped: thermal stress could not be computed."

    return FullRiskAssessment(
        observation=observation,
        heatwave_risk=heatwave,
        thermal_stress=thermal,
        mortality_vulnerability=mortality,
        thermal_stress_error=thermal_error,
        mortality_error=mortality_error,
    )
