"""
test_early_warning_api.py – Integration tests for the unified early-warning endpoint.

GET /api/areas/<area_id>/early-warning

Covers:
  • Valid area with weather data → complete response shape
  • Missing area → 404
  • Area without weather data → 404
  • Response schema validation
  • GIS-ready fields (lat/lon)
  • Thermal stress in response
  • Mortality/vulnerability in response
  • Demographics integration
  • Overall status field
  • Alert integration
  • Full pipeline integration test
"""

import json
import os
import sys

import pytest
from flask import Flask

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import Area, AreaDemographics, WeatherObservation, ForecastObservation, db
from routes.areas import areas_bp
from routes.alerts import alerts_bp
from services.alert_service import get_default_store


@pytest.fixture(autouse=True)
def clear_alerts():
    """Clear alert store before each test to prevent cross-test contamination."""
    get_default_store().clear()
    yield
    get_default_store().clear()


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
    app.register_blueprint(alerts_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _create_area(app, name="Hyderabad", lat=17.385, lon=78.4867):
    with app.app_context():
        area = Area(name=name, latitude=lat, longitude=lon)
        db.session.add(area)
        db.session.commit()
        return area.id


def _add_observation(app, area_id, temperature=38.0, humidity=60.0, wind_speed=10.0,
                     precipitation=0.0, solar_radiation=None,
                     timestamp="2026-08-28T12:00"):
    with app.app_context():
        obs = WeatherObservation(
            area_id=area_id,
            latitude=17.385,
            longitude=78.4867,
            timestamp=timestamp,
            temperature=temperature,
            humidity=humidity,
            wind_speed=wind_speed,
            precipitation=precipitation,
            solar_radiation=solar_radiation,
        )
        db.session.add(obs)
        db.session.commit()
        return obs.id


def _add_demographics(app, area_id, pct_elderly=10.0, pct_children=20.0):
    with app.app_context():
        demo = AreaDemographics(
            area_id=area_id,
            pct_elderly=pct_elderly,
            pct_children=pct_children,
        )
        db.session.add(demo)
        db.session.commit()


# ---------------------------------------------------------------------------
# Not found cases
# ---------------------------------------------------------------------------

class TestNotFound:
    def test_missing_area_returns_404(self, client):
        resp = client.get("/api/areas/9999/early-warning")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["status"] == "error"

    def test_area_with_no_weather_data_returns_404(self, app, client):
        area_id = _create_area(app)
        resp = client.get(f"/api/areas/{area_id}/early-warning")
        assert resp.status_code == 404
        body = resp.get_json()
        assert body["status"] == "error"
        assert "weather" in body["message"].lower() or "data" in body["message"].lower()


# ---------------------------------------------------------------------------
# Successful response shape
# ---------------------------------------------------------------------------

class TestResponseShape:
    def test_successful_response_has_success_status(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id)
        resp = client.get(f"/api/areas/{area_id}/early-warning")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

    def test_response_contains_area_info(self, app, client):
        area_id = _create_area(app, name="Hyderabad")
        _add_observation(app, area_id)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["area_id"] == area_id
        assert data["area"]["name"] == "Hyderabad"

    def test_response_contains_gis_coordinates(self, app, client):
        area_id = _create_area(app, lat=17.385, lon=78.4867)
        _add_observation(app, area_id)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["area"]["latitude"] == 17.385
        assert data["area"]["longitude"] == 78.4867

    def test_response_contains_weather_section(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, humidity=65.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert "weather" in data
        assert data["weather"]["temperature"] == 38.0
        assert data["weather"]["humidity"] == 65.0

    def test_response_contains_heatwave_risk(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert "heatwave_risk" in data
        assert "level" in data["heatwave_risk"]
        assert "score" in data["heatwave_risk"]
        assert "contributing_factors" in data["heatwave_risk"]

    def test_response_contains_thermal_stress(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, humidity=65.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert "thermal_stress" in data
        thermal = data["thermal_stress"]
        assert thermal is not None
        assert "level" in thermal
        assert "score" in thermal
        assert "contributing_factors" in thermal
        assert "methodology_note" in thermal

    def test_response_contains_mortality_vulnerability(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, humidity=65.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert "mortality_vulnerability" in data
        mv = data["mortality_vulnerability"]
        assert mv is not None
        assert "level" in mv
        assert "score" in mv
        assert "vulnerability_factor" in mv
        assert "methodology_note" in mv

    def test_response_contains_overall_status(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert "overall_status" in data
        assert data["overall_status"] in ("NORMAL", "WATCH", "WARNING", "CRITICAL")

    def test_response_contains_alerts_list(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert "alerts" in data
        assert isinstance(data["alerts"], list)

    def test_response_contains_highest_risk_level(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert "highest_risk_level" in data

    def test_response_contains_has_active_alerts_flag(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert "has_active_alerts" in data
        assert isinstance(data["has_active_alerts"], bool)


# ---------------------------------------------------------------------------
# Solar radiation propagation
# ---------------------------------------------------------------------------

class TestSolarRadiation:
    def test_solar_radiation_in_weather_section_when_present(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, solar_radiation=750.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["weather"]["solar_radiation"] == 750.0

    def test_solar_radiation_null_when_not_available(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, solar_radiation=None)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["weather"]["solar_radiation"] is None


# ---------------------------------------------------------------------------
# Demographics integration
# ---------------------------------------------------------------------------

class TestDemographicsIntegration:
    def test_demographics_in_response_when_available(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, humidity=65.0)
        _add_demographics(app, area_id, pct_elderly=15.0, pct_children=20.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["demographics"] is not None
        assert data["demographics"]["pct_elderly"] == 15.0

    def test_demographics_null_when_not_available(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, humidity=65.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["demographics"] is None

    def test_demographics_amplify_vulnerability_factor(self, app, client):
        # Without demographics
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, humidity=65.0)
        data_no_demo = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]

        # With demographics for same area (add demographics)
        _add_demographics(app, area_id, pct_elderly=25.0, pct_children=30.0)
        data_with_demo = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]

        # Vulnerability factor should be higher with demographics
        vf_no_demo = data_no_demo["mortality_vulnerability"]["vulnerability_factor"]
        vf_with_demo = data_with_demo["mortality_vulnerability"]["vulnerability_factor"]
        assert vf_with_demo > vf_no_demo


# ---------------------------------------------------------------------------
# Risk level correctness
# ---------------------------------------------------------------------------

class TestRiskLevelCorrectness:
    def test_low_temperature_gives_lower_risk(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=25.0, humidity=40.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["heatwave_risk"]["level"] == "LOW"

    def test_high_temperature_gives_high_risk(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=43.0, humidity=70.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["heatwave_risk"]["level"] in ("HIGH", "EXTREME")
        assert data["overall_status"] in ("WARNING", "CRITICAL")

    def test_normal_status_for_mild_conditions(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=25.0, humidity=40.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["overall_status"] in ("NORMAL", "WATCH")

    def test_alert_generation_does_not_crash_pipeline(self, app, client):
        area_id = _create_area(app, name="Hyderabad")
        _add_observation(app, area_id, temperature=45.0, humidity=80.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["overall_status"] == "CRITICAL"


# ---------------------------------------------------------------------------
# ML Prediction Integration
# ---------------------------------------------------------------------------

def _add_forecast_history(app, area_id):
    with app.app_context():
        for i in range(3):
            obs = ForecastObservation(
                area_id=area_id,
                forecast_timestamp=f"2026-08-28T1{2+i}:00",
                temperature=38.0,
                humidity=60.0,
                wind_speed=10.0,
                precipitation=0.0,
                solar_radiation=0.0
            )
            db.session.add(obs)
        db.session.commit()

class TestMLIntegration:
    def test_early_warning_with_ml_prediction(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id)
        _add_forecast_history(app, area_id)
        
        resp = client.get(f"/api/areas/{area_id}/early-warning")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        
        assert "ml_prediction" in data
        ml = data["ml_prediction"]
        assert ml["available"] is True
        assert ml["prototype"] is True
        assert ml["model_version"] == "v0.16"
        assert "prediction" in ml
        assert "probability" in ml
        assert "label" in ml

    def test_early_warning_no_stored_forecast(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id)
        # We don't add forecast
        
        resp = client.get(f"/api/areas/{area_id}/early-warning")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        
        # Deterministic risk still returned
        assert "heatwave_risk" in data
        assert "thermal_stress" in data
        
        assert "ml_prediction" in data
        ml = data["ml_prediction"]
        assert ml["available"] is False
        assert "No stored forecast" in ml["reason"]

    def test_early_warning_ml_prediction_failure_handled(self, app, client, monkeypatch):
        area_id = _create_area(app)
        _add_observation(app, area_id)
        _add_forecast_history(app, area_id)
        
        from services.prediction import PredictionError
        def mock_predict(*args, **kwargs):
            raise PredictionError("Mocked failure")
        monkeypatch.setattr("services.prediction.predict", mock_predict)
        
        resp = client.get(f"/api/areas/{area_id}/early-warning")
        assert resp.status_code == 200  # does not crash with 500
        data = resp.get_json()["data"]
        
        # Deterministic risk still returned
        assert "heatwave_risk" in data
        
        assert "ml_prediction" in data
        ml = data["ml_prediction"]
        assert ml["available"] is False
        assert ml["reason"] == "ML Service Unavailable"


# ---------------------------------------------------------------------------
# Latest observation used
# ---------------------------------------------------------------------------

class TestLatestObservation:
    def test_uses_most_recent_observation(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=30.0, timestamp="2026-08-28T10:00")
        _add_observation(app, area_id, temperature=45.0, timestamp="2026-08-28T14:00")
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        assert data["weather"]["temperature"] == 45.0
        assert data["weather"]["timestamp"] == "2026-08-28T14:00"


# ---------------------------------------------------------------------------
# Methodology notes (prototype disclaimer)
# ---------------------------------------------------------------------------

class TestMethodologyNotes:
    def test_thermal_stress_has_prototype_disclaimer(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, humidity=65.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        note = data["thermal_stress"]["methodology_note"]
        assert "prototype" in note.lower() or "not" in note.lower()

    def test_mortality_vulnerability_has_prototype_disclaimer(self, app, client):
        area_id = _create_area(app)
        _add_observation(app, area_id, temperature=38.0, humidity=65.0)
        data = client.get(f"/api/areas/{area_id}/early-warning").get_json()["data"]
        note = data["mortality_vulnerability"]["methodology_note"]
        assert "prototype" in note.lower() or "not" in note.lower()
