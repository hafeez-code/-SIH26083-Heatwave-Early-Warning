"""
forecast_alerts.py – Forecast-based heatwave risk orchestration.

v0.18: Evaluates upcoming forecast data for an area using both
deterministic rules and ML predictions, projecting the results into
distinct forecast alerts.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

from models.database_models import Area, ForecastObservation
from services.alert_service import (
    Alert,
    evaluate_forecast_alert_from_prediction,
    evaluate_forecast_alert_from_risk_assessment,
)
from services.data_ingestion import NormalisedObservation
from services.heatwave_risk import RiskAssessment, calculate_risk
from services.prediction import PredictionResult, predict, PredictionError


def evaluate_forecast_risk_for_area(
    area: Area,
    artifact_dir: str,
    artifact_version: str = "v0.16",
    task: str = "classification",
    target_column: str = "validated_heatwave_event",
) -> dict[str, Any]:
    """Evaluate all stored ForecastObservations for an Area.

    Performs both deterministic rule evaluation and ML prediction.
    Outputs are projected into the existing AlertStore without replacing
    current-weather alerts.
    """
    forecast_records = (
        ForecastObservation.query.filter_by(area_id=area.id)
        .order_by(
            ForecastObservation.forecast_timestamp.asc(),
            ForecastObservation.id.asc(),
        )
        .all()
    )

    if not forecast_records:
        return {
            "area_id": area.id,
            "deterministic_risks": [],
            "ml_predictions": [],
            "alerts": [],
        }

    # 1. Deterministic Rule Evaluation
    deterministic_risks: list[RiskAssessment] = []
    generated_alerts: list[Alert] = []

    for record in forecast_records:
        # A forecast must have a temperature to be evaluated.
        if record.temperature is None:
            continue

        # Convert to NormalisedObservation for the rule engine.
        # Note: We pass the forecast timestamp as the observation timestamp.
        obs = NormalisedObservation(
            latitude=float(area.latitude),
            longitude=float(area.longitude),
            timestamp=record.forecast_timestamp,
            temperature=record.temperature,
            humidity=record.humidity,
            wind_speed=record.wind_speed,
            precipitation=record.precipitation,
        )

        try:
            risk = calculate_risk(obs)
            deterministic_risks.append(risk)

            # Project into the alert system
            alert = evaluate_forecast_alert_from_risk_assessment(
                area_id=area.id,
                risk_level=risk.risk_level,
                risk_score=risk.risk_score,
                timestamp=risk.timestamp,
                factors=risk.contributing_factors,
            )
            if alert is not None:
                generated_alerts.append(alert)
        except ValueError as exc:
            logger.warning(
                "Deterministic evaluation skipped for area %s at %s: %s",
                area.id,
                record.forecast_timestamp,
                exc,
            )

    # 2. ML Prediction Evaluation
    records_dicts = [
        {
            "area_id": record.area_id,
            "forecast_timestamp": record.forecast_timestamp,
            "temperature": record.temperature,
            "humidity": record.humidity,
            "wind_speed": record.wind_speed,
            "precipitation": record.precipitation,
        }
        for record in forecast_records
    ]

    ml_predictions: list[PredictionResult] = []
    try:
        predictions = predict(
            records_dicts,
            artifact_dir=artifact_dir,
            task=task,
            target_column=target_column,
            artifact_version=artifact_version,
        )
        ml_predictions = predictions

        # Project ML predictions into the alert system
        for pred in predictions:
            ml_alert = evaluate_forecast_alert_from_prediction(pred)
            if ml_alert is not None:
                generated_alerts.append(ml_alert)

    except PredictionError as exc:
        logger.warning("ML prediction skipped for area %s: %s", area.id, exc)

    # Return a structured summary of what was evaluated
    return {
        "area_id": area.id,
        "deterministic_risks": deterministic_risks,
        "ml_predictions": ml_predictions,
        "alerts": generated_alerts,
    }
