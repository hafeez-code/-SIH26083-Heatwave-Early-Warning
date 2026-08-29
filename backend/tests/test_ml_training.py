"""Tests for reproducible baseline ML training."""

import os
import sys

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.ml_dataset import prepare_forecast_ml_dataset
from services.ml_training import TrainingError, train_baseline


def _records(count=24, *, target_name="validated_event"):
    return [{
        "area_id": 1,
        "forecast_timestamp": f"2026-08-{index + 1:02d}T12:00",
        "temperature": 30.0 + index,
        "humidity": 45.0 + (index % 4),
        "wind_speed": 10.0 + (index % 3),
        "precipitation": float(index % 2),
        target_name: index % 2,
    } for index in range(count)]


def test_classification_baseline_is_reproducible_and_reports_split_metrics():
    dataset = prepare_forecast_ml_dataset(_records(), target_column="validated_event")
    first = train_baseline(dataset, task="classification")
    second = train_baseline(dataset, task="classification")
    assert first.metrics == second.metrics
    assert first.model.named_steps["scaler"] is not None
    for partition in ("train", "validation", "test"):
        assert set(first.metrics[partition]) == {
            "accuracy", "precision", "recall", "f1", "confusion_matrix"
        }


def test_regression_baseline_reports_only_regression_metrics():
    records = _records(target_name="validated_impact")
    for index, record in enumerate(records):
        record["validated_impact"] = float(index) / 10
    dataset = prepare_forecast_ml_dataset(records, target_column="validated_impact")
    result = train_baseline(dataset, task="regression")
    assert result.task == "regression"
    assert set(result.metrics["test"]) == {"mae", "rmse", "r2"}


def test_training_rejects_insufficient_or_invalid_targets():
    one_class = _records()
    for record in one_class:
        record["validated_event"] = "only-class"
    dataset = prepare_forecast_ml_dataset(one_class, target_column="validated_event")
    with pytest.raises(TrainingError, match="two target classes"):
        train_baseline(dataset, task="classification")

    insufficient = prepare_forecast_ml_dataset(_records(5), target_column="validated_event")
    with pytest.raises(TrainingError, match="at least two chronological training rows"):
        train_baseline(insufficient, task="classification")

    with pytest.raises(TrainingError, match="task must"):
        train_baseline(dataset, task="unsupported")
