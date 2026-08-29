"""v0.17 alert service and API tests for SIH26083.

Tests
-----
 1. HIGH risk → WARNING alert.
 2. EXTREME risk → WARNING alert.
 3. MODERATE risk → WATCH alert.
 4. LOW risk → no alert.
 5. Duplicate suppression within the same 6h bucket.
 6. GET /api/alerts returns alerts.
 7. POST /api/alerts/<id>/resolve resolves an alert.
 8. Unknown alert_id returns 404.
 9. area_id filtering works.
10. active_only filtering works.
11. ML classification above warning threshold → ML alert.
12. ML prediction below watch threshold → no alert.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import db
from routes.alerts import alerts_bp
from services.alert_service import (
    Alert,
    AlertStore,
    alert_to_dict,
    evaluate_alert,
    evaluate_alert_from_prediction,
    evaluate_alert_from_risk_assessment,
    get_default_store,
    list_alerts,
)
from services.data_ingestion import NormalisedObservation
from services.heatwave_risk import RiskAssessment
from services.prediction import PredictionResult


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def store():
    """Isolated AlertStore instance for unit tests."""
    return AlertStore()


@pytest.fixture()
def app():
    """Minimal Flask app with the alerts blueprint for HTTP tests."""
    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(application)
    application.register_blueprint(alerts_bp)
    with application.app_context():
        db.create_all()
        # Clear the global store before each test to prevent cross-test leakage.
        get_default_store().clear()
        yield application
        get_default_store().clear()
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


# --------------------------------------------------------------------------- #
# Helper factories                                                              #
# --------------------------------------------------------------------------- #


def _risk(level: str, score: int, ts: str = "2026-08-28T12:00") -> RiskAssessment:
    return RiskAssessment(
        risk_level=level,
        risk_score=score,
        contributing_factors=[f"{level} heat (42.0°C)"],
        timestamp=ts,
        latitude=28.6,
        longitude=77.2,
    )


def _ml_prediction(
    probability: float,
    area_id: int = 1,
    ts: str = "2026-08-29T06:00",
) -> PredictionResult:
    return PredictionResult(
        area_id=area_id,
        forecast_timestamp=ts,
        task="classification",
        prediction=1,
        probability=probability,
        feature_values={"temp": 42.0},
    )


# --------------------------------------------------------------------------- #
# 1–4: Risk level → alert mapping                                              #
# --------------------------------------------------------------------------- #


class TestRiskLevelMapping:

    def test_high_risk_creates_warning_alert(self, store):
        """Test 1: HIGH risk → WARNING alert."""
        alert = evaluate_alert(1, _risk("HIGH", 70), store=store)
        assert alert is not None
        assert alert.level == "WARNING"
        assert alert.risk_level == "HIGH"
        assert alert.active is True

    def test_extreme_risk_creates_warning_alert(self, store):
        """Test 2: EXTREME risk → WARNING alert."""
        alert = evaluate_alert(1, _risk("EXTREME", 95), store=store)
        assert alert is not None
        assert alert.level == "WARNING"
        assert alert.risk_level == "EXTREME"

    def test_moderate_risk_creates_watch_alert(self, store):
        """Test 3: MODERATE risk → WATCH alert."""
        alert = evaluate_alert(1, _risk("MODERATE", 45), store=store)
        assert alert is not None
        assert alert.level == "WATCH"
        assert alert.risk_level == "MODERATE"

    def test_low_risk_creates_no_alert(self, store):
        """Test 4: LOW risk → no alert."""
        alert = evaluate_alert(1, _risk("LOW", 10), store=store)
        assert alert is None
        assert len(store) == 0


# --------------------------------------------------------------------------- #
# 5: Deduplication                                                              #
# --------------------------------------------------------------------------- #


class TestDeduplication:

    def test_same_area_severity_6h_bucket_no_duplicate(self, store):
        """Test 5: Same area + level + 6h bucket → same alert returned."""
        first = evaluate_alert(1, _risk("HIGH", 70, "2026-08-28T12:00"), store=store)
        second = evaluate_alert(1, _risk("HIGH", 75, "2026-08-28T14:00"), store=store)
        assert first is not None
        assert second is not None
        assert first.alert_id == second.alert_id
        assert len(store) == 1

    def test_different_6h_bucket_creates_new_alert(self, store):
        """Different 6h bucket → distinct alert."""
        first = evaluate_alert(1, _risk("HIGH", 70, "2026-08-28T00:00"), store=store)
        second = evaluate_alert(1, _risk("HIGH", 70, "2026-08-28T06:00"), store=store)
        assert first.alert_id != second.alert_id
        assert len(store) == 2

    def test_different_area_same_bucket_creates_new_alert(self, store):
        """Different area_id → distinct alert even in same 6h bucket."""
        first = evaluate_alert(1, _risk("HIGH", 70), store=store)
        second = evaluate_alert(2, _risk("HIGH", 70), store=store)
        assert first.alert_id != second.alert_id
        assert len(store) == 2


# --------------------------------------------------------------------------- #
# 6–10: REST API endpoint tests                                                 #
# --------------------------------------------------------------------------- #


class TestAlertsAPI:

    def test_list_alerts_returns_empty_initially(self, client):
        """Test 6a: GET /api/alerts returns empty list when no alerts exist."""
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["data"] == []
        assert body["count"] == 0

    def test_list_alerts_returns_alerts(self, client):
        """Test 6b: GET /api/alerts returns alerts after evaluation."""
        store = get_default_store()
        evaluate_alert(1, _risk("HIGH", 70), store=store)
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        assert body["data"][0]["level"] == "WARNING"

    def test_resolve_alert(self, client):
        """Test 7: POST /api/alerts/<id>/resolve marks alert inactive."""
        store = get_default_store()
        alert = evaluate_alert(1, _risk("HIGH", 70), store=store)
        resp = client.post(f"/api/alerts/{alert.alert_id}/resolve")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["data"]["active"] is False

    def test_resolve_unknown_alert_returns_404(self, client):
        """Test 8: Unknown alert_id → 404."""
        resp = client.post("/api/alerts/nonexistent-id/resolve")
        assert resp.status_code == 404
        assert resp.get_json()["status"] == "error"

    def test_filter_by_area_id(self, client):
        """Test 9: area_id filtering works."""
        store = get_default_store()
        evaluate_alert(1, _risk("HIGH", 70), store=store)
        evaluate_alert(2, _risk("MODERATE", 45), store=store)
        resp = client.get("/api/alerts?area_id=1")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        assert body["data"][0]["area_id"] == 1

    def test_active_only_filtering(self, client):
        """Test 10: active_only filtering works."""
        store = get_default_store()
        alert = evaluate_alert(1, _risk("HIGH", 70), store=store)
        evaluate_alert(2, _risk("MODERATE", 45), store=store)
        # Resolve one
        store.resolve(alert.alert_id)
        resp = client.get("/api/alerts?active_only=true")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["count"] == 1
        assert body["data"][0]["area_id"] == 2

    def test_clear_alerts(self, client):
        """POST /api/alerts/clear empties the store."""
        store = get_default_store()
        evaluate_alert(1, _risk("HIGH", 70), store=store)
        resp = client.post("/api/alerts/clear")
        assert resp.status_code == 200
        assert get_default_store().all() == []


# --------------------------------------------------------------------------- #
# 11–12: ML prediction alerts                                                   #
# --------------------------------------------------------------------------- #


class TestMLAlerts:

    def test_ml_above_warning_threshold_creates_alert(self, store):
        """Test 11: ML classification above warning threshold → WARNING alert."""
        pred = _ml_prediction(probability=0.85)
        alert = evaluate_alert_from_prediction(pred, store=store)
        assert alert is not None
        assert alert.level == "WARNING"
        assert alert.source == "ml"
        assert "ML probability" in alert.factors[0]

    def test_ml_above_watch_below_warning_creates_watch(self, store):
        """ML probability between watch and warning → WATCH alert."""
        pred = _ml_prediction(probability=0.60)
        alert = evaluate_alert_from_prediction(pred, store=store)
        assert alert is not None
        assert alert.level == "WATCH"
        assert alert.source == "ml"

    def test_ml_below_watch_threshold_no_alert(self, store):
        """Test 12: ML prediction below watch threshold → no alert."""
        pred = _ml_prediction(probability=0.30)
        alert = evaluate_alert_from_prediction(pred, store=store)
        assert alert is None
        assert len(store) == 0

    def test_ml_regression_task_no_alert(self, store):
        """ML regression predictions do not generate alerts."""
        pred = PredictionResult(
            area_id=1,
            forecast_timestamp="2026-08-29T06:00",
            task="regression",
            prediction=42.0,
            probability=None,
            feature_values={"temp": 42.0},
        )
        alert = evaluate_alert_from_prediction(pred, store=store)
        assert alert is None


# --------------------------------------------------------------------------- #
# Convenience wrapper: evaluate_alert_from_risk_assessment                      #
# --------------------------------------------------------------------------- #


class TestEvaluateFromStoredRow:

    def test_projects_stored_risk_into_alert(self, store):
        """The scheduler convenience wrapper produces correct alerts."""
        alert = evaluate_alert_from_risk_assessment(
            area_id=1,
            risk_level="HIGH",
            risk_score=70,
            timestamp="2026-08-28T12:00",
            factors=["High heat (39.0°C)"],
            store=store,
        )
        assert alert is not None
        assert alert.level == "WARNING"
        assert alert.risk_score == 70

    def test_low_risk_from_stored_row_no_alert(self, store):
        """LOW risk via convenience wrapper → no alert."""
        alert = evaluate_alert_from_risk_assessment(
            area_id=1,
            risk_level="LOW",
            risk_score=10,
            timestamp="2026-08-28T12:00",
            store=store,
        )
        assert alert is None


# --------------------------------------------------------------------------- #
# Scheduler integration: alert generated during collect_once                    #
# --------------------------------------------------------------------------- #


class TestSchedulerAlertIntegration:

    @pytest.fixture()
    def scheduler_app(self):
        """Minimal Flask app for scheduler integration tests."""
        application = Flask(__name__)
        application.config.update(
            TESTING=True,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(application)
        with application.app_context():
            db.create_all()
            yield application
            db.session.remove()
            db.drop_all()

    def test_scheduler_collect_evaluates_alert_for_high_risk(self, scheduler_app):
        """End-to-end: scheduler collect with HIGH risk → alert in store."""
        from services.weather_scheduler import WeatherScheduler

        isolated_store = AlertStore()
        obs = NormalisedObservation(
            latitude=28.6,
            longitude=77.2,
            timestamp="2026-08-28T12:00",
            temperature=39.0,  # HIGH risk with default thresholds
            humidity=65.0,
            wind_speed=10.0,
            precipitation=0.0,
        )

        scheduler = WeatherScheduler(
            latitude=obs.latitude,
            longitude=obs.longitude,
            interval=900,
            base_url="https://api.example.com/v1",
            db_session=db.session,
            app=scheduler_app,
            area_id=1,
        )

        with patch("services.weather_scheduler.fetch_weather", return_value=obs), \
             patch("services.alert_service.get_default_store", return_value=isolated_store):
            result = scheduler.collect_once()

        assert result is True
        alerts = isolated_store.all()
        assert len(alerts) == 1
        assert alerts[0].level == "WARNING"
        assert alerts[0].risk_level == "HIGH"

    def test_scheduler_collect_no_alert_for_low_risk(self, scheduler_app):
        """Scheduler collect with LOW risk → no alert."""
        from services.weather_scheduler import WeatherScheduler

        isolated_store = AlertStore()
        obs = NormalisedObservation(
            latitude=28.6,
            longitude=77.2,
            timestamp="2026-08-28T12:00",
            temperature=30.0,  # LOW risk (below TEMP_MIN threshold)
            humidity=40.0,
            wind_speed=10.0,
            precipitation=0.0,
        )

        scheduler = WeatherScheduler(
            latitude=obs.latitude,
            longitude=obs.longitude,
            interval=900,
            base_url="https://api.example.com/v1",
            db_session=db.session,
            app=scheduler_app,
            area_id=1,
        )

        with patch("services.weather_scheduler.fetch_weather", return_value=obs), \
             patch("services.alert_service.get_default_store", return_value=isolated_store):
            result = scheduler.collect_once()

        assert result is True
        assert len(isolated_store) == 0

    def test_scheduler_collect_without_area_id_skips_alert(self, scheduler_app):
        """Scheduler without area_id does not evaluate alerts."""
        from services.weather_scheduler import WeatherScheduler

        isolated_store = AlertStore()
        obs = NormalisedObservation(
            latitude=28.6,
            longitude=77.2,
            timestamp="2026-08-28T12:00",
            temperature=45.0,  # EXTREME risk
            humidity=85.0,
            wind_speed=2.0,
            precipitation=0.0,
        )

        scheduler = WeatherScheduler(
            latitude=obs.latitude,
            longitude=obs.longitude,
            interval=900,
            base_url="https://api.example.com/v1",
            db_session=db.session,
            app=scheduler_app,
            # area_id is None
        )

        with patch("services.weather_scheduler.fetch_weather", return_value=obs), \
             patch("services.alert_service.get_default_store", return_value=isolated_store):
            result = scheduler.collect_once()

        assert result is True
        # No area_id → no alert evaluation
        assert len(isolated_store) == 0

    def test_alert_failure_does_not_fail_collection(self, scheduler_app):
        """Alert evaluation error must not cause collect_once to return False."""
        from services.weather_scheduler import WeatherScheduler

        obs = NormalisedObservation(
            latitude=28.6,
            longitude=77.2,
            timestamp="2026-08-28T12:00",
            temperature=45.0,
            humidity=85.0,
            wind_speed=2.0,
            precipitation=0.0,
        )

        scheduler = WeatherScheduler(
            latitude=obs.latitude,
            longitude=obs.longitude,
            interval=900,
            base_url="https://api.example.com/v1",
            db_session=db.session,
            app=scheduler_app,
            area_id=1,
        )

        with patch("services.weather_scheduler.fetch_weather", return_value=obs), \
             patch(
                 "services.alert_service.evaluate_alert_from_risk_assessment",
                 side_effect=RuntimeError("alert boom"),
             ):
            result = scheduler.collect_once()

        # Observation + risk were persisted; alert failure is non-fatal.
        assert result is True


# --------------------------------------------------------------------------- #
# alert_to_dict serialisation                                                   #
# --------------------------------------------------------------------------- #


class TestAlertSerialization:

    def test_alert_to_dict_fields(self, store):
        """alert_to_dict produces all expected keys."""
        alert = evaluate_alert(1, _risk("HIGH", 70), store=store)
        d = alert_to_dict(alert)
        expected_keys = {
            "alert_id", "area_id", "level", "risk_level", "risk_score",
            "message", "timestamp", "raised_at_utc", "active", "factors",
            "source",
        }
        assert set(d.keys()) == expected_keys
        assert d["level"] == "WARNING"
        assert d["active"] is True
        assert isinstance(d["factors"], list)
