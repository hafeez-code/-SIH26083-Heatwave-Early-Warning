"""Tests for the v0.10 area-centric forecast pipeline."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from requests.exceptions import ReadTimeout

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import Area, ForecastObservation, db
from routes.areas import areas_bp
from routes.weather import weather_bp
from services.data_ingestion import WeatherAPIError, WeatherAPITimeoutError, WeatherDataError
from services.forecast_ingestion import (
    NormalisedForecast,
    _normalise_forecast_response,
    fetch_forecast,
    persist_forecasts,
    prepare_forecast_features,
)


def _payload(times=None):
    times = times or ["2026-08-29T12:00", "2026-08-29T13:00"]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [39.0, 40.0],
            "relative_humidity_2m": [60.0, 61.0],
            "wind_speed_10m": [10.0, 11.0],
            "precipitation": [0.0, 0.2],
            "shortwave_radiation": [50.0, 60.0],
        }
    }


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        WEATHER_API_BASE_URL="https://provider.example/v1",
        WEATHER_API_KEY="",
        WEATHER_API_TIMEOUT=7,
    )
    db.init_app(app)
    app.register_blueprint(areas_bp)
    app.register_blueprint(weather_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _area(app, name, lat, lon):
    with app.app_context():
        area = Area(name=name, latitude=lat, longitude=lon)
        db.session.add(area)
        db.session.commit()
        return area.id


def test_normalises_open_meteo_hourly_data_and_rejects_malformed_payloads():
    forecasts = _normalise_forecast_response(_payload())
    assert forecasts == [
        NormalisedForecast("2026-08-29T12:00", 39.0, 60.0, 10.0, 0.0, 50.0),
        NormalisedForecast("2026-08-29T13:00", 40.0, 61.0, 11.0, 0.2, 60.0),
    ]
    with pytest.raises(WeatherDataError, match="hourly"):
        _normalise_forecast_response({})
    with pytest.raises(WeatherDataError, match="temperature_2m"):
        _normalise_forecast_response({"hourly": {"time": ["2026-08-29T12:00"]}})


@patch("services.forecast_ingestion.requests.get")
def test_fetch_forecast_uses_hourly_schema_and_typed_errors(mock_get):
    response = MagicMock(ok=True)
    response.json.return_value = _payload()
    mock_get.return_value = response
    assert len(fetch_forecast(12.3, 45.6, "https://provider.example/v1", timeout=4)) == 2
    _, kwargs = mock_get.call_args
    assert kwargs["params"]["latitude"] == 12.3
    assert "temperature_2m" in kwargs["params"]["hourly"]

    mock_get.side_effect = ReadTimeout()
    with pytest.raises(WeatherAPITimeoutError):
        fetch_forecast(12.3, 45.6, "https://provider.example/v1")

    failed = MagicMock(ok=False, status_code=503, text="down")
    mock_get.side_effect = None
    mock_get.return_value = failed
    with pytest.raises(WeatherAPIError, match="503"):
        fetch_forecast(12.3, 45.6, "https://provider.example/v1")


def test_persistence_is_area_linked_idempotent_and_generates_features(app):
    first_area = _area(app, "Delhi", 28.6, 77.2)
    second_area = _area(app, "Mumbai", 19.0, 72.8)
    forecasts = _normalise_forecast_response(_payload())
    with app.app_context():
        persist_forecasts(forecasts, first_area, db.session)
        persist_forecasts([forecasts[0]], second_area, db.session)
        db.session.commit()
        persist_forecasts([NormalisedForecast(forecasts[0].forecast_timestamp, 41, 62, 12, 0, 70)], first_area, db.session)
        db.session.commit()
        first_records = ForecastObservation.query.filter_by(area_id=first_area).all()
        assert len(first_records) == 2
        assert ForecastObservation.query.filter_by(area_id=second_area).count() == 1
        assert first_records[0].area_id == first_area
        assert ForecastObservation.query.filter_by(area_id=first_area, forecast_timestamp=forecasts[0].forecast_timestamp).one().temperature == 41
        assert prepare_forecast_features(forecasts) == [
            {"forecast_timestamp": "2026-08-29T12:00", "temperature": 39.0, "humidity": 60.0, "wind_speed": 10.0, "precipitation": 0.0},
            {"forecast_timestamp": "2026-08-29T13:00", "temperature": 40.0, "humidity": 61.0, "wind_speed": 11.0, "precipitation": 0.2},
        ]


@patch("routes.weather.fetch_forecast")
def test_forecast_api_uses_area_coordinates_and_stored_retrieval(mock_fetch, app):
    area_id = _area(app, "Delhi", 28.6139, 77.2090)
    mock_fetch.return_value = list(reversed(_normalise_forecast_response(_payload())))
    client = app.test_client()

    response = client.get(f"/api/weather/forecast?area_id={area_id}&latitude=0&longitude=0")
    assert response.status_code == 200
    mock_fetch.assert_called_once_with(
        latitude=28.6139,
        longitude=77.2090,
        base_url="https://provider.example/v1",
        api_key="",
        timeout=7,
    )
    assert [item["forecast_timestamp"] for item in response.get_json()["data"]["forecasts"]] == [
        "2026-08-29T12:00", "2026-08-29T13:00"
    ]

    stored = client.get(f"/api/weather/forecast?area_id={area_id}&stored=true")
    assert stored.status_code == 200
    assert mock_fetch.call_count == 1
    assert len(stored.get_json()["data"]["features"]) == 2


def test_forecast_api_validates_area_and_keeps_areas_separate(app):
    first_area = _area(app, "Delhi", 28.6, 77.2)
    second_area = _area(app, "Mumbai", 19.0, 72.8)
    client = app.test_client()
    assert client.get("/api/weather/forecast").status_code == 400
    assert client.get("/api/weather/forecast?area_id=nope").status_code == 400
    assert client.get("/api/weather/forecast?area_id=999").status_code == 404
    assert client.get(f"/api/weather/forecast?area_id={first_area}&stored=true").status_code == 404

    with app.app_context():
        persist_forecasts([NormalisedForecast("2026-08-29T12:00", 39, 60, 10, 0, 50)], first_area, db.session)
        persist_forecasts([NormalisedForecast("2026-08-29T12:00", 35, 70, 8, 1, 40)], second_area, db.session)
        db.session.commit()
    first = client.get(f"/api/weather/forecast?area_id={first_area}&stored=true").get_json()
    second = client.get(f"/api/weather/forecast?area_id={second_area}&stored=true").get_json()
    assert first["data"]["forecasts"][0]["temperature"] == 39
    assert second["data"]["forecasts"][0]["temperature"] == 35


@patch("routes.weather.fetch_forecast")
def test_forecast_api_reports_provider_errors(mock_fetch, app):
    area_id = _area(app, "Delhi", 28.6, 77.2)
    client = app.test_client()
    mock_fetch.side_effect = WeatherAPITimeoutError("late")
    assert client.get(f"/api/weather/forecast?area_id={area_id}").status_code == 504
    mock_fetch.side_effect = WeatherDataError("bad hourly")
    response = client.get(f"/api/weather/forecast?area_id={area_id}")
    assert response.status_code == 502
    assert "Forecast provider error" in response.get_json()["message"]
