"""Tests for v0.14 historical weather, independent-label, and ML integration."""

import json
import os
import sys

import pytest
from flask import Flask

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import Area, HeatwaveRiskAssessment, HistoricalEventLabel, WeatherObservation, db
from services.historical_ingestion import HistoricalDataError
from services.historical_ml_integration import (
    HistoricalMLIntegrationError,
    ingest_historical_weather,
    ingest_independent_labels,
    load_labelled_historical_ml_dataset,
    match_historical_records_to_labels,
    prepare_labelled_historical_ml_dataset,
)
from services.label_preparation import DEFAULT_LABEL_NAME, LabelPreparationError
from services.ml_dataset import MODEL_FEATURE_COLUMNS, TargetValidationError


def _weather(area_id=1, timestamp="2026-07-01T12:00", **overrides):
    return {
        "area_id": area_id,
        "observation_timestamp": timestamp,
        "temperature": 39.0,
        "humidity": 60.0,
        "wind_speed": 10.0,
        "precipitation": 0.0,
        **overrides,
    }


def _label(area_id=1, timestamp="2026-07-01T12:00", **overrides):
    return {
        "area_id": area_id,
        "event_timestamp": timestamp,
        "label_value": 1,
        "label_source": "district health register",
        "source_reference": "DHR-2026-001",
        "validation_status": "validated",
        "provenance_type": "independent_validated",
        **overrides,
    }


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Area(name="Delhi", latitude=28.6, longitude=77.2),
            Area(name="Mumbai", latitude=19.0, longitude=72.8),
        ])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def test_valid_historical_ingestion_persists_area_and_timestamp(app):
    with app.app_context():
        records = ingest_historical_weather([_weather(humidity=None)], db.session)
        db.session.commit()
        stored = WeatherObservation.query.one()
        assert records[0] is stored
        assert stored.area_id == 1
        assert stored.timestamp == "2026-07-01T12:00:00"
        assert stored.latitude == 28.6
        assert stored.humidity is None
        assert HeatwaveRiskAssessment.query.count() == 0


def test_invalid_historical_data_is_rejected(app):
    with app.app_context():
        with pytest.raises(HistoricalDataError, match="humidity"):
            ingest_historical_weather([_weather(humidity=140)], db.session)
        db.session.rollback()
        assert WeatherObservation.query.count() == 0


def test_historical_persistence_is_idempotent(app):
    with app.app_context():
        ingest_historical_weather([_weather()], db.session)
        db.session.commit()
        ingest_historical_weather([_weather(temperature=41.5, humidity=None)], db.session)
        db.session.commit()
        stored = WeatherObservation.query.one()
        assert stored.temperature == 41.5
        assert stored.humidity is None
        assert WeatherObservation.query.count() == 1


def test_independent_label_validation_requires_provenance(app):
    with app.app_context():
        stored = ingest_independent_labels([_label()], db.session)
        db.session.commit()
        assert stored[0].label_source == "district health register"
        assert stored[0].source_reference == "DHR-2026-001"
        assert stored[0].validation_status == "validated"
        assert stored[0].provenance_type == "independent_validated"
        with pytest.raises(LabelPreparationError, match="source_reference"):
            ingest_independent_labels([_label(source_reference="")], db.session)


def test_rule_derived_labels_are_rejected(app):
    with app.app_context():
        with pytest.raises(LabelPreparationError, match="rule-derived"):
            ingest_independent_labels([_label(label_name="risk_score")], db.session)
        with pytest.raises(LabelPreparationError, match="rule-derived"):
            ingest_independent_labels([_label(label_name="risk_level")], db.session)
        with pytest.raises(LabelPreparationError, match="weather features"):
            ingest_independent_labels([_label(derived_from=["temperature"])], db.session)
        assert HistoricalEventLabel.query.count() == 0


def test_exact_area_timestamp_matching_and_unmatched_remain_unlabeled():
    weather = [
        _weather(1, "2026-07-01T12:00", temperature=40),
        _weather(1, "2026-07-01T13:00", temperature=41),
        _weather(2, "2026-07-01T12:00", temperature=38),
    ]
    labels = [
        _label(1, "2026-07-01T12:00", label_value=1),
        _label(1, "2026-07-01T14:00", label_value=1, source_reference="DHR-later"),
    ]
    matched = match_historical_records_to_labels(weather, labels)
    by_key = {(row["area_id"], row["forecast_timestamp"]): row[DEFAULT_LABEL_NAME] for row in matched}
    assert by_key[(1, "2026-07-01T12:00:00")] == 1
    assert by_key[(1, "2026-07-01T13:00:00")] is None
    assert by_key[(2, "2026-07-01T12:00:00")] is None
    assert len(matched) == 3


def test_ml_ready_output_uses_independent_labels_not_risk_assessments(app):
    hours = [
        "2026-07-01T12:00",
        "2026-07-01T13:00",
        "2026-07-01T14:00",
        "2026-07-01T15:00",
    ]
    with app.app_context():
        ingest_historical_weather(
            [_weather(1, timestamp, temperature=40.0 + index) for index, timestamp in enumerate(hours)],
            db.session,
        )
        db.session.commit()
        for observation in WeatherObservation.query.all():
            db.session.add(
                HeatwaveRiskAssessment(
                    weather_observation=observation,
                    risk_score=90,
                    risk_level="EXTREME",
                    contributing_factors=json.dumps(["temperature"]),
                )
            )
        db.session.commit()
        ingest_independent_labels(
            [_label(1, timestamp, label_value=index % 2, source_reference=f"DHR-{index}") for index, timestamp in enumerate(hours)],
            db.session,
        )
        db.session.commit()

        dataset = load_labelled_historical_ml_dataset(db.session)
        assert dataset.feature_names == MODEL_FEATURE_COLUMNS
        assert dataset.target_column == DEFAULT_LABEL_NAME
        assert set(dataset.y) <= {0, 1}
        assert 90 not in dataset.y
        assert "EXTREME" not in dataset.y
        assert all(set(item) == {"area_id", "forecast_timestamp"} for item in dataset.metadata)
        assert "risk_score" not in dataset.feature_names
        assert "risk_level" not in dataset.feature_names

        with pytest.raises(TargetValidationError, match="deterministic rule output"):
            prepare_labelled_historical_ml_dataset(
                match_historical_records_to_labels(
                    [_weather(1, hour) for hour in hours],
                    [_label(1, hour) for hour in hours],
                ),
                target_column="risk_score",
            )


def test_unmatched_observations_cannot_form_a_training_dataset():
    matched = match_historical_records_to_labels(
        [_weather(1, "2026-07-01T12:00")],
        [_label(1, "2026-07-01T13:00")],
    )
    assert matched[0][DEFAULT_LABEL_NAME] is None
    with pytest.raises(HistoricalMLIntegrationError, match="exact area/timestamp matches"):
        prepare_labelled_historical_ml_dataset(matched)
