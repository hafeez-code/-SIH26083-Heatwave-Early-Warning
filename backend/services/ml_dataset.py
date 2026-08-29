"""Leakage-safe dataset preparation for future supervised heatwave models.

The project does not currently contain an independently observed heatwave
outcome.  In particular, ``HeatwaveRiskAssessment`` must not be used as a
target: it is calculated from the same weather fields by a deterministic rule.
Callers must therefore supply a separately validated target column (for
example, an independently curated impact or heatwave-event label).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping

from services.forecast_features import build_forecast_features


MODEL_FEATURE_COLUMNS = (
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
)
METADATA_COLUMNS = ("area_id", "forecast_timestamp")
RULE_DERIVED_TARGET_COLUMNS = ("risk_score", "risk_level")


class DatasetValidationError(ValueError):
    """Raised when records cannot form a safe, usable ML dataset."""


class TargetValidationError(DatasetValidationError):
    """Raised when a target is missing or is known to be rule-derived."""


@dataclass(frozen=True)
class PreparedDataset:
    """Tabular features, independent targets, and non-model metadata."""

    feature_names: tuple[str, ...]
    X: tuple[tuple[float, ...], ...]
    y: tuple[Any, ...]
    metadata: tuple[dict[str, Any], ...]
    target_column: str


@dataclass(frozen=True)
class ChronologicalSplit:
    """Past, later, and latest dataset partitions."""

    train: PreparedDataset
    validation: PreparedDataset
    test: PreparedDataset


def _record_value(record: object, name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def _record_has_key(record: Mapping[str, Any], name: str) -> bool:
    return name in record


def _record_has_field(record: object, name: str) -> bool:
    if isinstance(record, Mapping):
        return name in record
    return hasattr(record, name)


def _sort_key(record: Mapping[str, Any], index: int) -> tuple[object, ...]:
    """Sort metadata without treating it as a predictive feature."""
    return (str(record["forecast_timestamp"]), str(record["area_id"]), index)


def _validate_target_column(target_column: str) -> None:
    if not target_column:
        raise TargetValidationError("A non-empty independent target column is required.")
    if target_column in RULE_DERIVED_TARGET_COLUMNS:
        raise TargetValidationError(
            f"{target_column!r} is a deterministic rule output and cannot be an ML target."
        )


def prepare_ml_dataset(
    records: Iterable[Mapping[str, Any]],
    *,
    target_column: str,
) -> PreparedDataset:
    """Select model features and preserve metadata from engineered records.

    Every selected feature must be present.  Rows with a null or non-finite
    selected feature are dropped deterministically rather than imputed.  A
    target must be present and non-null for every input row: unlike weather
    measurements, labels are not silently discarded because that can conceal
    a data-quality or provenance problem.
    """
    _validate_target_column(target_column)
    materialized = list(records)
    if not materialized:
        raise DatasetValidationError("Cannot prepare an ML dataset from empty input.")

    required_columns = set(MODEL_FEATURE_COLUMNS + METADATA_COLUMNS + (target_column,))
    for index, record in enumerate(materialized):
        missing = sorted(column for column in required_columns if not _record_has_key(record, column))
        if missing:
            raise DatasetValidationError(f"Record {index} is missing required columns: {', '.join(missing)}.")
        if record[target_column] is None:
            raise TargetValidationError(f"Record {index} has a null target value.")
        if not record["forecast_timestamp"]:
            raise DatasetValidationError(f"Record {index} has an empty forecast_timestamp.")

    ordered_records = sorted(
        enumerate(materialized), key=lambda item: _sort_key(item[1], item[0])
    )
    X: list[tuple[float, ...]] = []
    y: list[Any] = []
    metadata: list[dict[str, Any]] = []
    for _, record in ordered_records:
        feature_values = tuple(record[column] for column in MODEL_FEATURE_COLUMNS)
        if any(
            value is None or not isinstance(value, (int, float)) or not isfinite(value)
            for value in feature_values
        ):
            continue
        X.append(tuple(float(value) for value in feature_values))
        y.append(record[target_column])
        metadata.append({column: record[column] for column in METADATA_COLUMNS})

    if not X:
        raise DatasetValidationError("No complete rows remain after applying the missing-value policy.")
    return PreparedDataset(
        feature_names=MODEL_FEATURE_COLUMNS,
        X=tuple(X),
        y=tuple(y),
        metadata=tuple(metadata),
        target_column=target_column,
    )


def prepare_forecast_ml_dataset(
    records: Iterable[object],
    *,
    target_column: str,
) -> PreparedDataset:
    """Adapt v0.11 forecast features to a labelled ML dataset contract.

    This is intentionally a thin adapter: all weather feature calculations
    remain in ``build_forecast_features``.  It expects the independent target
    to be supplied alongside each source forecast record and does not query or
    derive targets from ``HeatwaveRiskAssessment``.
    """
    _validate_target_column(target_column)
    source_records = list(records)
    if not source_records:
        raise DatasetValidationError("Cannot prepare an ML dataset from empty input.")
    for index, record in enumerate(source_records):
        missing = [
            column for column in ("area_id", "forecast_timestamp", "temperature", "humidity", "wind_speed", "precipitation")
            if not _record_has_field(record, column)
        ]
        if missing:
            raise DatasetValidationError(
                f"Record {index} is missing required forecast columns: {', '.join(missing)}."
            )
        if _record_value(record, target_column) is None:
            raise TargetValidationError(f"Record {index} has no independent {target_column!r} target.")
        if _record_value(record, "area_id") is None:
            raise DatasetValidationError(f"Record {index} is missing area_id metadata.")

    # Match v0.11's deterministic area/timestamp ordering without recreating
    # any of its weather-feature calculations.
    ordered_source = sorted(
        enumerate(source_records),
        key=lambda item: (
            (_record_value(item[1], "area_id") is not None, str(_record_value(item[1], "area_id"))),
            str(_record_value(item[1], "forecast_timestamp")),
            item[0],
        ),
    )
    engineered = build_forecast_features(source_records)
    enriched_records = []
    for features, (_, source) in zip(engineered, ordered_source):
        enriched_records.append({
            **features,
            "area_id": _record_value(source, "area_id"),
            target_column: _record_value(source, target_column),
        })
    return prepare_ml_dataset(enriched_records, target_column=target_column)


def _partition(dataset: PreparedDataset, indexes: list[int]) -> PreparedDataset:
    return PreparedDataset(
        feature_names=dataset.feature_names,
        X=tuple(dataset.X[index] for index in indexes),
        y=tuple(dataset.y[index] for index in indexes),
        metadata=tuple(dataset.metadata[index] for index in indexes),
        target_column=dataset.target_column,
    )


def chronological_split(dataset: PreparedDataset) -> ChronologicalSplit:
    """Split by whole timestamps into approximately 70%/15%/15% partitions.

    Keeping every record for a timestamp in one partition prevents concurrent
    observations from being used both for fitting and for later evaluation.
    At least three distinct timestamps are required for past/later/latest
    partitions.
    """
    timestamp_groups: list[list[int]] = []
    ordered_indexes = sorted(
        range(len(dataset.metadata)),
        key=lambda index: (
            str(dataset.metadata[index]["forecast_timestamp"]),
            str(dataset.metadata[index]["area_id"]),
            index,
        ),
    )
    for index in ordered_indexes:
        metadata = dataset.metadata[index]
        timestamp = str(metadata["forecast_timestamp"])
        if not timestamp_groups or timestamp != str(dataset.metadata[timestamp_groups[-1][0]]["forecast_timestamp"]):
            timestamp_groups.append([])
        timestamp_groups[-1].append(index)
    if len(timestamp_groups) < 3:
        raise DatasetValidationError("At least three distinct timestamps are required for chronological splitting.")

    total_rows = len(dataset.X)
    cumulative = []
    count = 0
    for group in timestamp_groups:
        count += len(group)
        cumulative.append(count)
    train_boundary = min(
        range(1, len(timestamp_groups) - 1),
        key=lambda boundary: (abs(cumulative[boundary - 1] - total_rows * 0.70), boundary),
    )
    validation_boundary = min(
        range(train_boundary + 1, len(timestamp_groups)),
        key=lambda boundary: (
            abs(cumulative[boundary - 1] - cumulative[train_boundary - 1] - total_rows * 0.15),
            boundary,
        ),
    )
    return ChronologicalSplit(
        train=_partition(dataset, [index for group in timestamp_groups[:train_boundary] for index in group]),
        validation=_partition(dataset, [index for group in timestamp_groups[train_boundary:validation_boundary] for index in group]),
        test=_partition(dataset, [index for group in timestamp_groups[validation_boundary:] for index in group]),
    )
