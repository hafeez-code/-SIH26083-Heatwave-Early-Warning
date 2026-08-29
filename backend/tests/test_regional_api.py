"""Integration tests for v0.9 Area and historical-data APIs."""

import json
import os
import sys

import pytest
from flask import Flask

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import Area, HeatwaveRiskAssessment, WeatherObservation, db
from routes.areas import areas_bp
from routes.risk import risk_bp
from routes.weather import weather_bp
from services.data_ingestion import NormalisedObservation
from services.risk_pipeline import persist_observation_and_risk


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(areas_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(risk_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _create_area(client, name="Delhi"):
    response = client.post(
        "/api/areas", json={"name": name, "latitude": 28.6139, "longitude": 77.2090}
    )
    assert response.status_code == 201
    return response.get_json()["data"]


def _add_observation(app, area_id, timestamp, temperature=39.0):
    with app.app_context():
        observation = WeatherObservation(
            area_id=area_id,
            latitude=28.6139,
            longitude=77.2090,
            timestamp=timestamp,
            temperature=temperature,
            humidity=65.0,
            wind_speed=10.0,
            precipitation=0.0,
        )
        db.session.add(observation)
        db.session.flush()
        risk = HeatwaveRiskAssessment(
            weather_observation=observation,
            risk_score=70 if temperature < 42 else 90,
            risk_level="HIGH" if temperature < 42 else "EXTREME",
            contributing_factors=json.dumps(["test"]),
        )
        db.session.add(risk)
        db.session.commit()
        return observation.id, risk.id


def test_area_creation_validation_and_retrieval(client):
    assert client.post("/api/areas", json={"latitude": 1, "longitude": 2}).status_code == 400
    assert client.post("/api/areas", json={"name": "x", "latitude": 91, "longitude": 2}).status_code == 400
    assert client.post("/api/areas", json={"name": "x", "latitude": 1, "longitude": 181}).status_code == 400

    area = _create_area(client)
    assert client.get("/api/areas").get_json()["data"] == [area]
    assert client.get(f"/api/areas/{area['id']}").get_json()["data"] == area
    assert client.get("/api/areas/999").status_code == 404


def test_weather_history_filters_orders_and_preserves_relationship(app, client):
    area = _create_area(client)
    _add_observation(app, area["id"], "2026-08-28T13:00")
    first_id, _ = _add_observation(app, area["id"], "2026-08-28T12:00")
    _add_observation(app, area["id"], "2026-08-28T14:00")

    response = client.get(f"/api/weather?area_id={area['id']}&start=2026-08-28T12:00&end=2026-08-28T13:00&limit=2")
    assert response.status_code == 200
    observations = response.get_json()["data"]["observations"]
    assert [item["timestamp"] for item in observations] == ["2026-08-28T12:00", "2026-08-28T13:00"]
    assert observations[0]["id"] == first_id

    with app.app_context():
        assert db.session.get(Area, area["id"]).observations[0].area_id == area["id"]
        assert db.session.get(WeatherObservation, first_id).risk_assessment is not None


def test_pipeline_persists_area_relationship_and_risk_chain(app, client):
    area = _create_area(client)
    observation = NormalisedObservation(
        latitude=28.6139,
        longitude=77.2090,
        timestamp="2026-08-28T12:00",
        temperature=39.0,
        humidity=65.0,
        wind_speed=10.0,
        precipitation=0.0,
    )
    with app.app_context():
        weather, risk = persist_observation_and_risk(
            observation, db.session, area_id=area["id"]
        )
        db.session.commit()
        assert weather.area_id == area["id"]
        assert db.session.get(Area, area["id"]).observations == [weather]
        assert risk.weather_observation is weather


def test_weather_history_empty_and_unknown_area(client):
    area = _create_area(client)
    assert client.get(f"/api/weather?area_id={area['id']}").get_json()["data"]["observations"] == []
    assert client.get("/api/weather?area_id=999").status_code == 404


def test_area_stored_risk_uses_provider_timestamp_and_history(app, client):
    area = _create_area(client)
    # Insert the newer timestamp first so insertion order cannot choose it.
    _add_observation(app, area["id"], "2026-08-28T14:00", temperature=43.0)
    _, earlier_risk_id = _add_observation(app, area["id"], "2026-08-28T12:00")

    latest = client.get(f"/api/risk?area_id={area['id']}&stored=true")
    assert latest.status_code == 200
    assert latest.get_json()["data"]["weather"]["timestamp"] == "2026-08-28T14:00"

    history = client.get(f"/api/risk/history?area_id={area['id']}")
    risks = history.get_json()["data"]["risks"]
    assert [item["weather"]["timestamp"] for item in risks] == ["2026-08-28T12:00", "2026-08-28T14:00"]
    assert risks[0]["id"] == earlier_risk_id


def test_area_risk_not_found_and_missing_stored_risk(client):
    area = _create_area(client)
    assert client.get("/api/risk?area_id=999&stored=true").status_code == 404
    missing = client.get(f"/api/risk?area_id={area['id']}&stored=true")
    assert missing.status_code == 404
    assert "No stored risk assessment" in missing.get_json()["message"]
