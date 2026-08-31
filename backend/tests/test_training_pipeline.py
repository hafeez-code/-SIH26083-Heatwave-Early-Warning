"""Tests for the v0.15 historical ML training pipeline and artifacts."""

import json
import os
import subprocess
import sys

import pytest
from flask import Flask
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import Area, db
from services.historical_ml_integration import ingest_historical_weather, ingest_independent_labels
from services.label_preparation import DEFAULT_LABEL_NAME
from services.ml_dataset import MODEL_FEATURE_COLUMNS, prepare_forecast_ml_dataset
from services.ml_training import TrainingError
from services.model_artifacts import load_training_artifact
from services.training_pipeline import (
    train_from_database,
    train_from_historical_records,
    train_prepared_dataset,
)


def _weather(area_id, timestamp, **overrides):
    return {
        "area_id": area_id,
        "observation_timestamp": timestamp,
        "temperature": 34.0,
        "humidity": 55.0,
        "wind_speed": 8.0,
        "precipitation": 0.0,
        **overrides,
    }


def _label(area_id, timestamp, **overrides):
    return {
        "area_id": area_id,
        "event_timestamp": timestamp,
        "label_value": 1,
        "label_source": "district health register",
        "source_reference": "DHR-TEST-001",
        "validation_status": "validated",
        "provenance_type": "independent_validated",
        **overrides,
    }


def _labelled_history(count=24):
    weather = []
    labels = []
    for index in range(count):
        timestamp = f"2026-06-01T{index:02d}:00"
        weather.append(_weather(1, timestamp, temperature=32.0 + (index % 8), precipitation=float(index % 2)))
        labels.append(_label(1, timestamp, label_value=index % 2, source_reference=f"DHR-{index}"))
    return weather, labels


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        # pyrefly: ignore [unexpected-keyword]
        db.session.add(Area(name="Delhi", latitude=28.6, longitude=77.2))
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def test_classification_training_is_chronological_reproducible_and_saves_pipeline(tmp_path):
    weather, labels = _labelled_history()
    first = train_from_historical_records(
        weather, labels, task="classification", artifact_dir=tmp_path, artifact_version="test-v0.15"
    )
    second = train_from_historical_records(
        weather, labels, task="classification", artifact_dir=tmp_path, artifact_version="test-v0.15"
    )
    assert first.metrics == second.metrics
    assert first.n_train + first.n_validation + first.n_test == second.n_train + second.n_validation + second.n_test
    assert first.train_timestamp_range[1] < first.validation_timestamp_range[0]
    assert first.validation_timestamp_range[1] < first.test_timestamp_range[0]
    assert first.feature_names == MODEL_FEATURE_COLUMNS
    assert "area_id" not in first.feature_names
    assert "forecast_timestamp" not in first.feature_names
    assert first.target_column == DEFAULT_LABEL_NAME
    assert set(first.pipeline.named_steps) == {"scaler", "model"}
    assert isinstance(first.pipeline.named_steps["scaler"], StandardScaler)
    assert isinstance(first.pipeline.named_steps["model"], LogisticRegression)

    loaded = load_training_artifact(first.artifact_path)
    assert set(loaded["sklearn_pipeline"].named_steps) == {"scaler", "model"}
    assert loaded["feature_names"] == list(MODEL_FEATURE_COLUMNS)
    assert loaded["task"] == "classification"
    weather_row = [[float(index) for index in range(len(MODEL_FEATURE_COLUMNS))]]
    assert list(first.pipeline.predict(weather_row)) == list(loaded["sklearn_pipeline"].predict(weather_row))


def test_regression_training_saves_ridge_pipeline(tmp_path):
    records = [{
        "area_id": 1,
        "forecast_timestamp": f"2026-08-{index + 1:02d}T12:00",
        "temperature": 30.0 + index,
        "humidity": 45.0 + (index % 4),
        "wind_speed": 10.0,
        "precipitation": float(index % 2),
        "independent_impact": float(index) / 10.0,
    } for index in range(24)]
    dataset = prepare_forecast_ml_dataset(records, target_column="independent_impact")
    result = train_prepared_dataset(
        dataset, task="regression", artifact_dir=tmp_path, artifact_version="test-v0.15"
    )
    assert result.task == "regression"
    assert isinstance(result.pipeline.named_steps["model"], Ridge)
    assert set(result.metrics["test"]) == {"mae", "rmse", "r2"}
    loaded = load_training_artifact(result.artifact_path)
    assert isinstance(loaded["sklearn_pipeline"].named_steps["scaler"], StandardScaler)


def test_database_training_uses_independent_labels_not_risk_fields(app, tmp_path):
    weather, labels = _labelled_history()
    with app.app_context():
        ingest_historical_weather(weather, db.session)
        ingest_independent_labels(labels, db.session)
        db.session.commit()
        result = train_from_database(
            db.session, task="classification", artifact_dir=tmp_path, artifact_version="test-v0.15"
        )
        assert result.n_train >= 2
        assert result.n_validation >= 1
        assert result.n_test >= 1
        meta = json.loads((tmp_path / "test-v0.15__classification__validated_heatwave_event.meta.json").read_text())
        assert meta["target_column"] == DEFAULT_LABEL_NAME
        assert meta["n_train"] == result.n_train


def test_insufficient_data_and_missing_labels_do_not_write_artifacts(tmp_path):
    weather, labels = _labelled_history(count=4)
    with pytest.raises(TrainingError):
        train_from_historical_records(
            weather, labels, task="classification", artifact_dir=tmp_path, artifact_version="fail"
        )
    with pytest.raises(TrainingError, match="exact area/timestamp matches"):
        train_from_historical_records(
            [_weather(1, "2026-06-01T00:00")],
            [_label(1, "2026-06-01T12:00")],
            task="classification",
            artifact_dir=tmp_path,
            artifact_version="fail",
        )
    assert list(tmp_path.glob("*")) == []


def test_rule_derived_targets_are_rejected(tmp_path):
    weather, labels = _labelled_history()
    with pytest.raises(TrainingError, match="deterministic rule output"):
        train_from_historical_records(
            weather, labels, task="classification", artifact_dir=tmp_path, target_column="risk_score"
        )
    with pytest.raises(TrainingError, match="deterministic rule output"):
        train_from_historical_records(
            weather, labels, task="classification", artifact_dir=tmp_path, target_column="risk_level"
        )
    assert list(tmp_path.glob("*")) == []


def test_generated_artifacts_are_ignored_by_git():
    sample = os.path.join(_REPO_ROOT, "backend", "artifacts", "models", "example.joblib")
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", sample],
        cwd=_REPO_ROOT,
        check=False,
    )
    assert ignored.returncode == 0
