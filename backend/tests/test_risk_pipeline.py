"""Integration tests for the v0.8 persisted weather-risk pipeline."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest
from flask import Flask

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import db, HeatwaveRiskAssessment, WeatherObservation
from routes.risk import risk_bp
from services.data_ingestion import NormalisedObservation
from services.risk_pipeline import persist_observation_and_risk
from services.weather_scheduler import WeatherScheduler


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(risk_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def observation():
    return NormalisedObservation(
        latitude=28.6139,
        longitude=77.2090,
        timestamp="2026-08-28T12:00",
        temperature=39.0,
        humidity=65.0,
        wind_speed=10.0,
        precipitation=0.0,
    )


def test_pipeline_persists_linked_assessment(app, observation):
    with app.app_context():
        weather, risk = persist_observation_and_risk(observation, db.session)
        db.session.commit()

        persisted_risk = HeatwaveRiskAssessment.query.one()
        assert WeatherObservation.query.count() == 1
        assert persisted_risk.weather_observation_id == weather.id
        assert persisted_risk.id == risk.id
        assert persisted_risk.risk_score == 70
        assert persisted_risk.risk_level == "HIGH"
        assert json.loads(persisted_risk.contributing_factors) == [
            "High heat (39.0°C)",
            "High humidity (65.0%)",
        ]


def test_pipeline_rolls_back_when_risk_calculation_fails(app, observation):
    with app.app_context(), patch(
        "services.risk_pipeline.calculate_risk", side_effect=ValueError("bad temperature")
    ):
        with pytest.raises(ValueError, match="bad temperature"):
            persist_observation_and_risk(observation, db.session)
        db.session.rollback()
        assert WeatherObservation.query.count() == 0
        assert HeatwaveRiskAssessment.query.count() == 0


def test_scheduler_rolls_back_when_risk_persistence_fails(app, observation):
    scheduler = WeatherScheduler(
        latitude=observation.latitude,
        longitude=observation.longitude,
        interval=900,
        base_url="https://api.example.com/v1",
        db_session=db.session,
        app=app,
    )
    original_add = db.session.add

    def fail_risk_add(record):
        if isinstance(record, HeatwaveRiskAssessment):
            raise RuntimeError("risk persistence failed")
        return original_add(record)

    with patch("services.weather_scheduler.fetch_weather", return_value=observation), patch.object(
        db.session, "add", side_effect=fail_risk_add
    ):
        assert scheduler.collect_once() is False

    with app.app_context():
        assert WeatherObservation.query.count() == 0
        assert HeatwaveRiskAssessment.query.count() == 0


def test_scheduler_rolls_back_within_its_background_app_context(app, observation):
    scheduler = WeatherScheduler(
        latitude=observation.latitude,
        longitude=observation.longitude,
        interval=900,
        base_url="https://api.example.com/v1",
        db_session=db.session,
        app=app,
    )
    with patch(
        "services.weather_scheduler.fetch_weather", side_effect=RuntimeError("pipeline failure")
    ), patch.object(db.session, "rollback", wraps=db.session.rollback) as rollback:
        assert scheduler.collect_once() is False
        rollback.assert_called_once()


def test_repeated_scheduler_cycles_create_linked_records(app, observation):
    scheduler = WeatherScheduler(
        latitude=observation.latitude,
        longitude=observation.longitude,
        interval=900,
        base_url="https://api.example.com/v1",
        db_session=db.session,
        app=app,
    )
    observations = [
        observation,
        NormalisedObservation(**{**observation.__dict__, "timestamp": "2026-08-28T12:15"}),
    ]
    with patch("services.weather_scheduler.fetch_weather", side_effect=observations):
        assert scheduler.collect_once() is True
        assert scheduler.collect_once() is True

    with app.app_context():
        assert WeatherObservation.query.count() == 2
        assert HeatwaveRiskAssessment.query.count() == 2
        assert all(row.risk_assessment is not None for row in WeatherObservation.query.all())


def test_stored_risk_api_returns_latest_record(app, observation):
    with app.app_context():
        persist_observation_and_risk(observation, db.session)
        db.session.commit()
        newer = NormalisedObservation(
            **{**observation.__dict__, "timestamp": "2026-08-28T12:15", "temperature": 43.0}
        )
        persist_observation_and_risk(newer, db.session)
        db.session.commit()

    response = app.test_client().get(
        "/api/risk?latitude=28.6139&longitude=77.2090&stored=true"
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["weather"]["timestamp"] == "2026-08-28T12:15"
    assert data["risk"]["score"] == 90
    assert data["risk"]["level"] == "EXTREME"
    assert data["risk"]["contributing_factors"] == [
        "Extreme heat (43.0°C)",
        "High humidity (65.0%)",
    ]


def test_stored_risk_api_returns_404_when_no_record_exists(app):
    response = app.test_client().get(
        "/api/risk?latitude=28.6139&longitude=77.2090&stored=true"
    )
    assert response.status_code == 404
    assert "No stored risk assessment" in response.get_json()["message"]
