"""Tests for the v0.16 ML inference service and API."""

import os
import sys

import pytest
from flask import Flask
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app import create_app
from models.database_models import Area, ForecastObservation, db
from services.label_preparation import DEFAULT_LABEL_NAME
from services.ml_dataset import MODEL_FEATURE_COLUMNS, prepare_forecast_ml_dataset
from services.ml_training import TrainingError
from services.model_artifacts import (
    ArtifactError,
    artifact_paths,
    list_artifacts,
    resolve_artifact_path,
    save_training_artifact,
)
from services.prediction import (
    PredictionError,
    build_inference_features,
    load_prediction_artifact,
    predict,
)
from services.training_pipeline import train_from_historical_records


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


def _labelled_history(count=24, *, area_id=1):
    weather = []
    labels = []
    for index in range(count):
        timestamp = f"2026-06-01T{index:02d}:00"
        weather.append(
            _weather(
                area_id,
                timestamp,
                temperature=32.0 + (index % 8),
                precipitation=float(index % 2),
            )
        )
        labels.append(
            _label(
                area_id,
                timestamp,
                label_value=index % 2,
                source_reference=f"DHR-{index}",
            )
        )
    return weather, labels


def _records_for_inference(count=8, *, area_id=1):
    return [
        {
            "area_id": area_id,
            "forecast_timestamp": f"2026-06-02T{index:02d}:00",
            "temperature": 33.0 + (index % 6),
            "humidity": 50.0 + (index % 4),
            "wind_speed": 9.0,
            "precipitation": float(index % 3),
        }
        for index in range(count)
    ]


def _train_classification_artifact(tmp_path, *, version="v0.16"):
    weather, labels = _labelled_history()
    return train_from_historical_records(
        weather,
        labels,
        task="classification",
        artifact_dir=tmp_path,
        artifact_version=version,
    )


def _train_regression_artifact(tmp_path, *, version="v0.16", target="independent_impact"):
    records = [
        {
            "area_id": 1,
            "forecast_timestamp": f"2026-08-{index + 1:02d}T12:00",
            "temperature": 30.0 + index,
            "humidity": 45.0 + (index % 4),
            "wind_speed": 10.0,
            "precipitation": float(index % 2),
            target: float(index) / 10.0,
        }
        for index in range(24)
    ]
    dataset = prepare_forecast_ml_dataset(records, target_column=target)
    from services.training_pipeline import train_prepared_dataset
    return train_prepared_dataset(
        dataset,
        task="regression",
        artifact_dir=tmp_path,
        artifact_version=version,
    )


# --------------------------------------------------------------------------- #
# 1. Artifact resolution and listing                                          #
# --------------------------------------------------------------------------- #


def test_resolve_artifact_path_prefers_requested_version(tmp_path):
    _train_classification_artifact(tmp_path, version="v0.16")
    _train_classification_artifact(tmp_path, version="v0.15")
    resolved = resolve_artifact_path(
        tmp_path,
        version="v0.16",
        task="classification",
        target_column=DEFAULT_LABEL_NAME,
    )
    expected, _ = artifact_paths(
        tmp_path,
        version="v0.16",
        task="classification",
        target_column=DEFAULT_LABEL_NAME,
    )
    assert resolved == expected


def test_resolve_artifact_path_falls_back_to_v015_when_requested(tmp_path):
    _train_classification_artifact(tmp_path, version="v0.15")
    resolved = resolve_artifact_path(
        tmp_path,
        version="v0.16",
        task="classification",
        target_column=DEFAULT_LABEL_NAME,
        fallback_version="v0.15",
    )
    expected, _ = artifact_paths(
        tmp_path,
        version="v0.15",
        task="classification",
        target_column=DEFAULT_LABEL_NAME,
    )
    assert resolved == expected


def test_resolve_artifact_path_raises_without_match(tmp_path):
    with pytest.raises(ArtifactError, match="No artifact found"):
        resolve_artifact_path(
            tmp_path,
            version="v0.16",
            task="classification",
            target_column=DEFAULT_LABEL_NAME,
        )


def test_list_artifacts_summarises_directory(tmp_path):
    assert list_artifacts(tmp_path) == []
    _train_classification_artifact(tmp_path, version="v0.16")
    entries = list_artifacts(tmp_path)
    assert len(entries) == 1
    assert entries[0]["artifact_version"] == "v0.16"
    assert entries[0]["task"] == "classification"
    assert entries[0]["target_column"] == DEFAULT_LABEL_NAME
    assert entries[0]["meta_path"] is not None


# --------------------------------------------------------------------------- #
# 2. Service layer: load/build/predict                                        #
# --------------------------------------------------------------------------- #


def test_load_prediction_artifact_validates_feature_contract(tmp_path):
    _train_classification_artifact(tmp_path, version="v0.16")
    loaded = load_prediction_artifact(
        str(tmp_path),
        version="v0.16",
        task="classification",
        target_column=DEFAULT_LABEL_NAME,
    )
    assert tuple(loaded["feature_names"]) == tuple(MODEL_FEATURE_COLUMNS)


def test_load_prediction_artifact_rejects_mismatched_feature_names(tmp_path):
    pipeline = Pipeline([("scaler", StandardScaler()), ("model", Ridge())])
    joblib_path, _ = artifact_paths(
        tmp_path,
        version="broken",
        task="regression",
        target_column="independent_impact",
    )
    joblib_path.parent.mkdir(parents=True, exist_ok=True)
    import joblib
    pipeline.fit([[1.0, 2.0], [3.0, 4.0]], [0.0, 1.0])
    joblib.dump(
        {
            "sklearn_pipeline": pipeline,
            "feature_names": ["temperature", "humidity"],
            "target_column": "independent_impact",
            "task": "regression",
            "artifact_version": "broken",
        },
        joblib_path,
    )
    with pytest.raises(PredictionError, match="feature_names do not match"):
        load_prediction_artifact(
            str(tmp_path),
            version="broken",
            task="regression",
            target_column="independent_impact",
        )


def test_build_inference_features_drops_incomplete_rows():
    records = _records_for_inference(6)
    records[3]["humidity"] = None
    rows = build_inference_features(records)
    assert len(rows) < len(records)
    for row in rows:
        for column in MODEL_FEATURE_COLUMNS:
            assert isinstance(row[column], float)
            assert row[column] == row[column]


def test_classification_predict_returns_label_and_probability(tmp_path):
    training = _train_classification_artifact(tmp_path, version="v0.16")
    records = _records_for_inference(10)
    results = predict(
        records,
        artifact_dir=str(tmp_path),
        task="classification",
        artifact_version="v0.16",
    )
    assert len(results) >= 1
    for result in results:
        assert result.task == "classification"
        assert isinstance(result.prediction, int)
        assert result.prediction in (0, 1)
        assert isinstance(result.probability, float)
        assert 0.0 <= result.probability <= 1.0
        assert tuple(result.feature_values.keys()) == tuple(MODEL_FEATURE_COLUMNS)
        assert "area_id" not in result.feature_values
        assert "forecast_timestamp" not in result.feature_values
        assert isinstance(result.area_id, int)
        assert isinstance(result.forecast_timestamp, str)


def test_regression_predict_returns_numeric_and_no_probability(tmp_path):
    training = _train_regression_artifact(tmp_path, version="v0.16")
    records = _records_for_inference(10)
    results = predict(
        records,
        artifact_dir=str(tmp_path),
        task="regression",
        target_column="independent_impact",
        artifact_version="v0.16",
    )
    assert len(results) >= 1
    for result in results:
        assert result.task == "regression"
        assert isinstance(result.prediction, float)
        assert result.probability is None


def test_predict_rejects_rule_derived_target(tmp_path):
    _train_classification_artifact(tmp_path)
    with pytest.raises(PredictionError, match="deterministic rule output"):
        predict(
            _records_for_inference(5),
            artifact_dir=str(tmp_path),
            task="classification",
            target_column="risk_score",
        )


def test_predict_reports_missing_artifact(tmp_path):
    with pytest.raises(PredictionError, match="No artifact found"):
        predict(
            _records_for_inference(5),
            artifact_dir=str(tmp_path),
            task="classification",
            artifact_version="v0.99",
            fallback_version=None,
        )


# --------------------------------------------------------------------------- #
# 3. Flask API layer via create_app                                           #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def app(tmp_path):
    app = create_app("default")
    with app.app_context():
        db.drop_all()
        db.create_all()
        area = Area(name="Delhi", latitude=28.6, longitude=77.2)
        db.session.add(area)
        db.session.commit()
        app.config["ML_ARTIFACT_DIR"] = str(tmp_path)
        app.config["ML_ARTIFACT_VERSION"] = "v0.16"
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _seed_forecasts(app, *, area_id=1, count=10):
    with app.app_context():
        rows = []
        for index in range(count):
            row = ForecastObservation(
                area_id=area_id,
                forecast_timestamp=f"2026-07-01T{index:02d}:00",
                temperature=32.0 + (index % 5),
                humidity=48.0 + (index % 4),
                wind_speed=7.0,
                precipitation=float(index % 3),
            )
            db.session.add(row)
            rows.append(row)
        db.session.commit()
        return rows


def test_post_prediction_endpoint_accepts_raw_records(tmp_path, client, app):
    _train_classification_artifact(tmp_path, version="v0.16")
    records = _records_for_inference(8)
    response = client.post(
        "/api/prediction",
        json={
            "records": records,
            "artifact_version": "v0.16",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    data = payload["data"]
    assert data["task"] == "classification"
    assert data["artifact_version"] == "v0.16"
    assert isinstance(data["n_skipped"], int)
    assert data["n_skipped"] >= 0
    assert len(data["predictions"]) + data["n_skipped"] == len(records)
    for item in data["predictions"]:
        assert item["task"] == "classification"
        assert item["prediction"] in (0, 1)
        assert 0.0 <= item["probability"] <= 1.0


def test_post_prediction_endpoint_404_without_artifact(tmp_path, client):
    response = client.post(
        "/api/prediction",
        json={"records": _records_for_inference(4), "artifact_version": "v0.99"},
    )
    assert response.status_code == 404
    assert "No artifact found" in response.get_json()["message"]


def test_stored_forecast_api_pipeline(tmp_path, app, client):
    _train_classification_artifact(tmp_path, version="v0.16")
    with app.app_context():
        area = db.session.get(Area, 1)
        area_id = area.id
    _seed_forecasts(app, area_id=area_id, count=12)
    response = client.get(
        f"/api/prediction/forecast?area_id={area_id}&stored=true"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "success"
    data = payload["data"]
    assert data["area_id"] == area_id
    assert len(data["predictions"]) + data["n_skipped"] == 12
    for item in data["predictions"]:
        assert "forecast_timestamp" in item
        assert item["task"] == "classification"
        assert isinstance(item["prediction"], int)


def test_stored_forecast_api_requires_stored_true(client, app):
    with app.app_context():
        area = db.session.get(Area, 1)
        area_id = area.id
    response = client.get(f"/api/prediction/forecast?area_id={area_id}")
    assert response.status_code == 400
    assert "requires stored=true" in response.get_json()["message"]


def test_stored_forecast_api_404_for_missing_forecasts(tmp_path, client, app):
    _train_classification_artifact(tmp_path, version="v0.16")
    with app.app_context():
        area = db.session.get(Area, 1)
        area_id = area.id
    response = client.get(
        f"/api/prediction/forecast?area_id={area_id}&stored=true&artifact_version=v0.16"
    )
    assert response.status_code == 404
    assert "No stored forecast" in response.get_json()["message"]


def test_post_prediction_endpoint_rejects_invalid_records(tmp_path, client):
    response = client.post(
        "/api/prediction",
        json={"records": [{"area_id": "not-an-int"}]},
    )
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_post_prediction_endpoint_rejects_empty_records_array(tmp_path, client):
    response = client.post("/api/prediction", json={"records": []})
    assert response.status_code == 400
    assert "non-empty" in response.get_json()["message"]


# --------------------------------------------------------------------------- #
# 4. Sanity: v0.15 default artifact fallback via predict() service helper     #
# --------------------------------------------------------------------------- #


def test_predict_uses_v015_fallback_when_v016_absent(tmp_path):
    _train_classification_artifact(tmp_path, version="v0.15")
    records = _records_for_inference(10)
    results = predict(
        records,
        artifact_dir=str(tmp_path),
        task="classification",
        artifact_version="v0.16",
        fallback_version="v0.15",
    )
    assert len(results) >= 1
    assert all(item.task == "classification" for item in results)
