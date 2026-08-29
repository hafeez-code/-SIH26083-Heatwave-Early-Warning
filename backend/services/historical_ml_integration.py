"""Integrate historical weather, independent labels, and the v0.12 ML dataset.

This module does not reimplement v0.11 feature formulas, v0.12 dataset
preparation, or v0.13 validation.  It never reads ``HeatwaveRiskAssessment``
and never invents labels for unmatched observations.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from models.database_models import Area, HistoricalEventLabel, WeatherObservation
from services.historical_ingestion import (
    persist_historical_observations,
    prepare_historical_features,
)
from services.label_preparation import (
    DEFAULT_LABEL_NAME,
    INDEPENDENT_PROVENANCE_TYPES,
    LabelPreparationError,
    attach_independent_labels,
    persist_independent_labels,
    prepare_independent_labels,
)
from services.ml_dataset import (
    PreparedDataset,
    TargetValidationError,
    prepare_ml_dataset,
)


class HistoricalMLIntegrationError(ValueError):
    """Raised when labelled historical data cannot be prepared for ML."""


def _observation_record(observation: WeatherObservation) -> dict[str, Any]:
    return {
        "area_id": observation.area_id,
        "observation_timestamp": observation.timestamp,
        "temperature": observation.temperature,
        "humidity": observation.humidity,
        "wind_speed": observation.wind_speed,
        "precipitation": observation.precipitation,
    }


def _label_record(label: HistoricalEventLabel) -> dict[str, Any]:
    return {
        "area_id": label.area_id,
        "event_timestamp": label.event_timestamp,
        "label_value": label.label_value,
        "label_source": label.label_source,
        "source_reference": label.source_reference,
        "validation_status": label.validation_status,
        "provenance_type": label.provenance_type,
        "label_name": label.label_name,
    }


def ingest_historical_weather(records: Iterable[object], db_session) -> list[WeatherObservation]:
    """Validate provider-neutral historical records and persist them idempotently.

    Persistence uses the existing ``WeatherObservation`` model and the v0.13
    ``(area_id, timestamp)`` logical key.  This path does not calculate or
    store heatwave risk.
    """
    return persist_historical_observations(records, db_session)


def ingest_independent_labels(records: Iterable[object], db_session) -> list[HistoricalEventLabel]:
    """Validate independently observed/validated labels and persist them."""
    prepared = prepare_independent_labels(records)
    for label in prepared:
        if db_session.get(Area, label.area_id) is None:
            raise LabelPreparationError(f"Area {label.area_id} does not exist.")
    return persist_independent_labels(prepared, db_session)


def match_historical_records_to_labels(
    weather_records: Iterable[object],
    label_records: Iterable[object],
) -> list[dict[str, Any]]:
    """Attach independent labels using exact ``(area_id, timestamp)`` matches.

    Unmatched observations remain present with a null label value.  Labels at
    a different timestamp, including later times, are not applied.
    """
    features = prepare_historical_features(weather_records)
    labels = prepare_independent_labels(label_records)
    if not features:
        return []
    if not labels:
        return [dict(feature) for feature in features]
    return attach_independent_labels(features, labels)


def prepare_labelled_historical_ml_dataset(
    matched_records: Iterable[dict[str, Any]],
    *,
    target_column: str = DEFAULT_LABEL_NAME,
) -> PreparedDataset:
    """Build a v0.12 dataset from exact matches only.

    Rows without an independent label are excluded rather than synthesised.
    """
    if target_column in ("risk_score", "risk_level"):
        raise TargetValidationError(
            f"{target_column!r} is a deterministic rule output and cannot be an ML target."
        )
    labelled = [dict(record) for record in matched_records if record.get(target_column) is not None]
    if not labelled:
        raise HistoricalMLIntegrationError(
            "No exact area/timestamp matches exist between historical weather and independent labels."
        )
    return prepare_ml_dataset(labelled, target_column=target_column)


def load_labelled_historical_ml_dataset(
    db_session,
    *,
    area_ids: Optional[Sequence[int]] = None,
    target_column: str = DEFAULT_LABEL_NAME,
) -> PreparedDataset:
    """Prepare an ML dataset from persisted historical weather and validated labels."""
    observation_query = db_session.query(WeatherObservation).filter(WeatherObservation.area_id.isnot(None))
    label_query = db_session.query(HistoricalEventLabel).filter(
        HistoricalEventLabel.validation_status == "validated",
        HistoricalEventLabel.provenance_type.in_(tuple(INDEPENDENT_PROVENANCE_TYPES)),
        HistoricalEventLabel.label_name == target_column,
    )
    if area_ids is not None:
        observation_query = observation_query.filter(WeatherObservation.area_id.in_(area_ids))
        label_query = label_query.filter(HistoricalEventLabel.area_id.in_(area_ids))

    observations = observation_query.order_by(
        WeatherObservation.area_id.asc(),
        WeatherObservation.timestamp.asc(),
        WeatherObservation.id.asc(),
    ).all()
    labels = label_query.order_by(
        HistoricalEventLabel.area_id.asc(),
        HistoricalEventLabel.event_timestamp.asc(),
        HistoricalEventLabel.id.asc(),
    ).all()
    weather_records = [
        _observation_record(observation)
        for observation in observations
        if observation.area_id is not None
    ]
    matched = match_historical_records_to_labels(
        weather_records,
        [_label_record(label) for label in labels],
    )
    return prepare_labelled_historical_ml_dataset(matched, target_column=target_column)
