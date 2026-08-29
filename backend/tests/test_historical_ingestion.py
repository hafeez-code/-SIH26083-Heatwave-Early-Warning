"""Tests for historical weather validation, persistence, and shared features."""

import os
import sys

import pytest
from flask import Flask

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import Area, WeatherObservation, db
from services.historical_ingestion import (
    HistoricalDataError,
    normalise_historical_observation,
    normalise_historical_observations,
    persist_historical_observations,
    prepare_historical_features,
)


def _record(area_id=1, timestamp="2026-07-01T12:00", **overrides):
    return {
        "area_id": area_id,
        "observation_timestamp": timestamp,
        "temperature": 39.0,
        "humidity": 60.0,
        "wind_speed": 10.0,
        "precipitation": 0.0,
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


def test_normalises_valid_records_and_preserves_null_measurements():
    record = normalise_historical_observation(_record(temperature="39", humidity=None))
    assert record.observation_timestamp == "2026-07-01T12:00:00"
    assert record.temperature == 39.0
    assert record.humidity is None


@pytest.mark.parametrize("overrides, message", [
    ({"area_id": None}, "area_id"),
    ({"observation_timestamp": "not-a-time"}, "ISO-8601"),
    ({"temperature": float("nan")}, "finite"),
    ({"humidity": 101}, "between 0 and 100"),
    ({"precipitation": -1}, "cannot be negative"),
])
def test_rejects_missing_invalid_or_nonfinite_data(overrides, message):
    with pytest.raises(HistoricalDataError, match=message):
        normalise_historical_observation(_record(**overrides))


def test_orders_areas_and_uses_shared_features_without_cross_area_leakage():
    records = normalise_historical_observations([
        _record(2, "2026-07-01T13:00", temperature=35),
        _record(1, "2026-07-01T13:00", temperature=42),
        _record(1, "2026-07-01T12:00", temperature=40),
    ])
    assert [(record.area_id, record.observation_timestamp) for record in records] == [
        (1, "2026-07-01T12:00:00"),
        (1, "2026-07-01T13:00:00"),
        (2, "2026-07-01T13:00:00"),
    ]
    features = prepare_historical_features(records)
    assert [item["temperature_change"] for item in features] == [None, 2.0, None]
    assert [item["area_id"] for item in features] == [1, 1, 2]


def test_persistence_is_idempotent_and_uses_area_coordinates(app):
    with app.app_context():
        first = normalise_historical_observation(_record())
        persist_historical_observations([first], db.session)
        db.session.commit()
        update = normalise_historical_observation(_record(temperature=41.0))
        persist_historical_observations([update], db.session)
        db.session.commit()
        stored = WeatherObservation.query.one()
        assert stored.temperature == 41.0
        assert stored.latitude == 28.6
        assert WeatherObservation.query.count() == 1
