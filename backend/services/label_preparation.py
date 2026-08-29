"""Preparation and provenance safeguards for independent historical labels."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from models.database_models import HistoricalEventLabel


DEFAULT_LABEL_NAME = "validated_heatwave_event"
INDEPENDENT_PROVENANCE_TYPES = {"independent_observed", "independent_validated"}
REJECTED_LABEL_NAMES = {"risk_score", "risk_level"}
WEATHER_FEATURE_FIELDS = {
    "temperature",
    "humidity",
    "wind_speed",
    "precipitation",
    "temperature_humidity_interaction",
    "temperature_change",
    "temperature_rolling_mean_3",
    "temperature_rolling_max_3",
    "precipitation_indicator",
    "high_temperature_indicator",
}


class LabelPreparationError(ValueError):
    """Raised when a label lacks independent, validated provenance."""


@dataclass(frozen=True)
class IndependentEventLabel:
    """A binary label supplied by an independent observed or validated source."""

    area_id: int
    event_timestamp: str
    label_value: int
    label_source: str
    source_reference: str
    validation_status: str = "validated"
    provenance_type: str = "independent_validated"
    label_name: str = DEFAULT_LABEL_NAME


def _value(record: object, name: str, default: Any = None) -> Any:
    if isinstance(record, Mapping):
        return record.get(name, default)
    return getattr(record, name, default)


def _canonical_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise LabelPreparationError("event_timestamp must be a non-empty ISO-8601 string.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError as exc:
        raise LabelPreparationError("event_timestamp must be a valid ISO-8601 timestamp.") from exc


def prepare_independent_label(record: object) -> IndependentEventLabel:
    """Validate one external label without deriving it from weather features."""
    area_id = _value(record, "area_id")
    if isinstance(area_id, bool) or not isinstance(area_id, int) or area_id < 1:
        raise LabelPreparationError("area_id must be a positive integer.")
    label_name = _value(record, "label_name", DEFAULT_LABEL_NAME)
    if label_name in REJECTED_LABEL_NAMES:
        raise LabelPreparationError(f"{label_name!r} is a rule-derived risk value, not an independent label.")
    if not isinstance(label_name, str) or not label_name:
        raise LabelPreparationError("label_name must be a non-empty string.")
    derived_from = _value(record, "derived_from", ())
    if isinstance(derived_from, str):
        derived_from = (derived_from,)
    if set(derived_from or ()) & WEATHER_FEATURE_FIELDS:
        raise LabelPreparationError("Labels derived from model weather features are not allowed.")
    provenance_type = _value(record, "provenance_type", "independent_validated")
    if provenance_type not in INDEPENDENT_PROVENANCE_TYPES:
        raise LabelPreparationError("provenance_type must identify an independent observed or validated source.")
    validation_status = _value(record, "validation_status", "validated")
    if validation_status != "validated":
        raise LabelPreparationError("validation_status must be 'validated'.")
    label_value = _value(record, "label_value")
    if isinstance(label_value, bool):
        label_value = int(label_value)
    if label_value not in (0, 1):
        raise LabelPreparationError("label_value must be binary (0 or 1).")
    label_source = _value(record, "label_source")
    source_reference = _value(record, "source_reference")
    if not isinstance(label_source, str) or not label_source:
        raise LabelPreparationError("label_source is required for provenance.")
    if not isinstance(source_reference, str) or not source_reference:
        raise LabelPreparationError("source_reference is required for provenance.")
    return IndependentEventLabel(
        area_id=area_id,
        event_timestamp=_canonical_timestamp(_value(record, "event_timestamp")),
        label_value=label_value,
        label_source=label_source,
        source_reference=source_reference,
        validation_status=validation_status,
        provenance_type=provenance_type,
        label_name=label_name,
    )


def prepare_independent_labels(records: Iterable[object]) -> list[IndependentEventLabel]:
    """Validate labels and return a deterministic area/timestamp order."""
    return sorted(
        (prepare_independent_label(record) for record in records),
        key=lambda label: (label.area_id, label.event_timestamp, label.label_name),
    )


def persist_independent_labels(
    labels: Iterable[IndependentEventLabel], db_session
) -> list[HistoricalEventLabel]:
    """Idempotently stage independently validated labels; caller owns commit."""
    persisted = []
    for label in prepare_independent_labels(labels):
        record = HistoricalEventLabel.query.filter_by(
            area_id=label.area_id,
            event_timestamp=label.event_timestamp,
            label_name=label.label_name,
        ).one_or_none()
        if record is None:
            record = HistoricalEventLabel(
                area_id=label.area_id,
                event_timestamp=label.event_timestamp,
                label_name=label.label_name,
            )
            db_session.add(record)
        record.label_value = label.label_value
        record.label_source = label.label_source
        record.source_reference = label.source_reference
        record.validation_status = label.validation_status
        record.provenance_type = label.provenance_type
        persisted.append(record)
    return persisted


def attach_independent_labels(
    features: Iterable[Mapping[str, Any]], labels: Iterable[IndependentEventLabel]
) -> list[dict]:
    """Attach exact area/timestamp labels without creating labels for unmatched data."""
    index = {
        (label.area_id, label.event_timestamp, label.label_name): label
        for label in prepare_independent_labels(labels)
    }
    attached = []
    for feature in features:
        item = dict(feature)
        for label_name in {label.label_name for label in index.values()}:
            label = index.get((item.get("area_id"), item.get("forecast_timestamp"), label_name))
            item[label_name] = None if label is None else label.label_value
        attached.append(item)
    return attached
