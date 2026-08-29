"""Tests for leakage-safe ML dataset preparation."""

import os
import sys

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.ml_dataset import (
    DatasetValidationError,
    MODEL_FEATURE_COLUMNS,
    TargetValidationError,
    chronological_split,
    prepare_forecast_ml_dataset,
    prepare_ml_dataset,
)


def _records(count=20):
    return [{
        "area_id": 2 if index % 2 else 1,
        "forecast_timestamp": f"2026-08-{index + 1:02d}T12:00",
        "temperature": 34.0 + index,
        "humidity": 50.0 + (index % 5),
        "wind_speed": 8.0,
        "precipitation": 0.5 if index % 3 == 0 else 0.0,
        "validated_event": index % 2,
    } for index in range(count)]


def test_forecast_adapter_selects_features_separates_target_and_preserves_metadata():
    dataset = prepare_forecast_ml_dataset(_records(), target_column="validated_event")
    assert dataset.feature_names == MODEL_FEATURE_COLUMNS
    assert len(dataset.X) == 16  # First two rows lack a complete 3-step rolling window per area.
    assert dataset.y[0] in (0, 1)
    assert set(dataset.metadata[0]) == {"area_id", "forecast_timestamp"}
    assert "area_id" not in dataset.feature_names
    assert "forecast_timestamp" not in dataset.feature_names


def test_dataset_is_chronological_deterministic_and_split_without_future_leakage():
    first = prepare_forecast_ml_dataset(list(reversed(_records())), target_column="validated_event")
    second = prepare_forecast_ml_dataset(list(reversed(_records())), target_column="validated_event")
    assert first == second
    timestamps = [item["forecast_timestamp"] for item in first.metadata]
    assert timestamps == sorted(timestamps)

    split = chronological_split(first)
    assert len(split.train.X) + len(split.validation.X) + len(split.test.X) == len(first.X)
    assert max(item["forecast_timestamp"] for item in split.train.metadata) < min(
        item["forecast_timestamp"] for item in split.validation.metadata
    )
    assert max(item["forecast_timestamp"] for item in split.validation.metadata) < min(
        item["forecast_timestamp"] for item in split.test.metadata
    )


def test_required_columns_missing_values_empty_input_and_target_validation_are_explicit():
    with pytest.raises(DatasetValidationError, match="empty input"):
        prepare_ml_dataset([], target_column="validated_event")
    with pytest.raises(TargetValidationError, match="deterministic rule output"):
        prepare_forecast_ml_dataset(_records(), target_column="risk_score")

    incomplete = _records(4)
    incomplete[0].pop("humidity")
    with pytest.raises(DatasetValidationError, match="humidity"):
        prepare_forecast_ml_dataset(incomplete, target_column="validated_event")

    null_target = _records(4)
    null_target[0]["validated_event"] = None
    with pytest.raises(TargetValidationError, match="independent"):
        prepare_forecast_ml_dataset(null_target, target_column="validated_event")


def test_missing_selected_features_are_dropped_without_imputation():
    records = _records(8)
    records[4]["humidity"] = None
    dataset = prepare_forecast_ml_dataset(records, target_column="validated_event")
    assert len(dataset.X) < 8
    assert all(all(value is not None for value in row) for row in dataset.X)
