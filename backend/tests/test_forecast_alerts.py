"""v0.18 forecast-based early warning tests."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from models.database_models import Area, ForecastObservation, db
from routes.forecast import forecast_bp
from services.alert_service import AlertStore, get_default_store
from services.prediction import PredictionResult


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def app():
    """Minimal Flask app for testing forecast alerts."""
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(application)
    application.register_blueprint(forecast_bp)
    with application.app_context():
        db.create_all()
        # Create a test area
        # pyrefly: ignore [unexpected-keyword]
        area = Area(name="Test Area", latitude=28.6, longitude=77.2)
        db.session.add(area)
        db.session.commit()

        get_default_store().clear()
        yield application
        get_default_store().clear()

        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _add_forecast(
    area_id: int,
    ts: str,
    temp: float,
    humidity: float = 50.0,
    wind_speed: float = 10.0,
    precip: float = 0.0,
):
    obs = ForecastObservation(
        # pyrefly: ignore [unexpected-keyword]
        area_id=area_id,
        # pyrefly: ignore [unexpected-keyword]
        forecast_timestamp=ts,
        # pyrefly: ignore [unexpected-keyword]
        temperature=temp,
        # pyrefly: ignore [unexpected-keyword]
        humidity=humidity,
        # pyrefly: ignore [unexpected-keyword]
        wind_speed=wind_speed,
        # pyrefly: ignore [unexpected-keyword]
        precipitation=precip,
    )
    db.session.add(obs)
    db.session.commit()


# --------------------------------------------------------------------------- #
# Unit / Logic Tests                                                            #
# --------------------------------------------------------------------------- #

class TestForecastAlertLogic:

    @patch("services.forecast_alerts.predict")
    def test_safe_forecast_no_alert(self, mock_predict, app):
        """Test 1: Safe forecast -> no alert."""
        _add_forecast(1, "2026-08-30T12:00", temp=30.0) # LOW risk
        mock_predict.return_value = [
            PredictionResult(1, "2026-08-30T12:00", "classification", 0, 0.2, {})
        ]

        with app.app_context():
            from services.forecast_alerts import evaluate_forecast_risk_for_area
            area = db.session.get(Area, 1)
            results = evaluate_forecast_risk_for_area(area, "dummy_dir")

        assert len(results["alerts"]) == 0
        assert len(get_default_store()) == 0

    @patch("services.forecast_alerts.predict")
    def test_dangerous_deterministic_forecast(self, mock_predict, app):
        """Test 2: Deterministic dangerous forecast -> forecast_rule alert."""
        _add_forecast(1, "2026-08-30T12:00", temp=45.0) # EXTREME risk
        mock_predict.return_value = [
            PredictionResult(1, "2026-08-30T12:00", "classification", 0, 0.2, {})
        ]

        with app.app_context():
            from services.forecast_alerts import evaluate_forecast_risk_for_area
            area = db.session.get(Area, 1)
            results = evaluate_forecast_risk_for_area(area, "dummy_dir")

        assert len(results["alerts"]) == 1
        alert = results["alerts"][0]
        assert alert.source == "forecast_rule"
        assert alert.level == "WARNING"
        # Test 5: Forecast alert messages clearly identify forecast origin.
        assert alert.message.startswith("Forecast: Extreme heatwave risk detected")

    @patch("services.forecast_alerts.predict")
    def test_dangerous_ml_forecast(self, mock_predict, app):
        """Test 3: ML dangerous forecast -> ml alert."""
        _add_forecast(1, "2026-08-30T12:00", temp=30.0) # LOW risk rule
        mock_predict.return_value = [
            PredictionResult(1, "2026-08-30T12:00", "classification", 1, 0.85, {})
        ]

        with app.app_context():
            from services.forecast_alerts import evaluate_forecast_risk_for_area
            area = db.session.get(Area, 1)
            results = evaluate_forecast_risk_for_area(area, "dummy_dir")

        assert len(results["alerts"]) == 1
        alert = results["alerts"][0]
        assert alert.source == "ml"
        assert alert.level == "WARNING"
        assert alert.message.startswith("Forecast ML model predicts elevated")

    @patch("services.forecast_alerts.predict")
    def test_both_signals_coexist(self, mock_predict, app):
        """Test 4: Both signals can coexist."""
        _add_forecast(1, "2026-08-30T12:00", temp=45.0) # EXTREME risk rule
        mock_predict.return_value = [
            PredictionResult(1, "2026-08-30T12:00", "classification", 1, 0.85, {})
        ]

        with app.app_context():
            from services.forecast_alerts import evaluate_forecast_risk_for_area
            area = db.session.get(Area, 1)
            results = evaluate_forecast_risk_for_area(area, "dummy_dir")

        assert len(results["alerts"]) == 2
        sources = {a.source for a in results["alerts"]}
        assert sources == {"forecast_rule", "ml"}

    @patch("services.forecast_alerts.predict")
    def test_duplicate_suppression(self, mock_predict, app):
        """Test 6: Duplicate forecast evaluations are suppressed."""
        _add_forecast(1, "2026-08-30T12:00", temp=45.0)
        mock_predict.return_value = [
            PredictionResult(1, "2026-08-30T12:00", "classification", 1, 0.85, {})
        ]

        with app.app_context():
            from services.forecast_alerts import evaluate_forecast_risk_for_area
            area = db.session.get(Area, 1)
            # Evaluate twice
            results1 = evaluate_forecast_risk_for_area(area, "dummy_dir")
            results2 = evaluate_forecast_risk_for_area(area, "dummy_dir")

        assert len(results1["alerts"]) == 2
        # The second evaluation returns the exact same alerts from the store
        assert len(results2["alerts"]) == 2
        assert {a.alert_id for a in results1["alerts"]} == {a.alert_id for a in results2["alerts"]}
        assert len(get_default_store()) == 2

    @patch("services.forecast_alerts.predict")
    def test_multiple_timestamps(self, mock_predict, app):
        """Test 7: Multiple forecast timestamps are handled correctly."""
        _add_forecast(1, "2026-08-30T12:00", temp=45.0) # EXTREME
        _add_forecast(1, "2026-08-30T18:00", temp=40.0) # HIGH

        mock_predict.return_value = [
            PredictionResult(1, "2026-08-30T12:00", "classification", 0, 0.2, {}),
            PredictionResult(1, "2026-08-30T18:00", "classification", 0, 0.2, {}),
        ]

        with app.app_context():
            from services.forecast_alerts import evaluate_forecast_risk_for_area
            area = db.session.get(Area, 1)
            results = evaluate_forecast_risk_for_area(area, "dummy_dir")

        # Two deterministic alerts, one for each distinct 6h bucket
        assert len(results["alerts"]) == 2
        assert len(results["deterministic_risks"]) == 2


# --------------------------------------------------------------------------- #
# Endpoint Tests                                                                #
# --------------------------------------------------------------------------- #

class TestForecastEndpoint:

    @patch("routes.forecast.evaluate_forecast_risk_for_area")
    def test_endpoint_response_shape(self, mock_eval, client):
        """Test 10: Endpoint response shape."""
        # Setup mock return
        from services.heatwave_risk import RiskAssessment
        from services.alert_service import _build_alert

        risk = RiskAssessment("HIGH", 70, ["heat"], "2026-08-30T12:00", 28.6, 77.2)
        alert = _build_alert(
            area_id=1, alert_level="WARNING", risk_level="HIGH", risk_score=70,
            timestamp="2026-08-30T12:00", factors=["heat"], source="forecast_rule"
        )
        pred = PredictionResult(1, "2026-08-30T12:00", "classification", 1, 0.9, {})

        mock_eval.return_value = {
            "area_id": 1,
            "deterministic_risks": [risk],
            "ml_predictions": [pred],
            "alerts": [alert],
        }

        resp = client.get("/api/risk/forecast?area_id=1")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        data = body["data"]
        assert data["area_id"] == 1
        assert len(data["deterministic_risks"]) == 1
        assert data["deterministic_risks"][0]["risk_level"] == "HIGH"
        assert len(data["ml_predictions"]) == 1
        assert data["ml_predictions"][0]["probability"] == 0.9
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["source"] == "forecast_rule"

    def test_no_forecast_data(self, client):
        """Test 8: No forecast data for an area is handled correctly."""
        resp = client.get("/api/risk/forecast?area_id=1")
        assert resp.status_code == 404
        assert resp.get_json()["message"] == "No stored forecast found for this area."

    def test_missing_area_handling(self, client):
        """Test 9: Invalid/missing area handling."""
        resp = client.get("/api/risk/forecast")
        assert resp.status_code == 400

        resp = client.get("/api/risk/forecast?area_id=abc")
        assert resp.status_code == 400

        resp = client.get("/api/risk/forecast?area_id=999")
        assert resp.status_code == 404

    @patch("routes.forecast.evaluate_forecast_risk_for_area", side_effect=RuntimeError("boom"))
    def test_endpoint_error_handling(self, mock_eval, client):
        """Test 11: Endpoint error handling."""
        resp = client.get("/api/risk/forecast?area_id=1")
        assert resp.status_code == 500
        assert resp.get_json()["message"] == "An unexpected internal error occurred."
