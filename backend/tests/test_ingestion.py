"""
test_ingestion.py – Unit tests for the weather data ingestion service.

Sprint 3: Weather ingestion foundation.

All HTTP calls are mocked – no real network requests are made.
All database operations use an in-memory SQLite instance – no real DB file
is required or modified.

Test coverage
-------------
1. Successful response → NormalisedObservation with all fields populated.
2. Partial response (some measurement fields absent) → NormalisedObservation
   with those fields as None, no crash.
3. Malformed / non-JSON response → WeatherDataError.
4. Missing required field (no 'current_weather') → WeatherDataError.
5. Missing required field (no 'time') → WeatherDataError.
6. HTTP error (4xx / 5xx) → WeatherAPIError.
7. Network timeout → WeatherAPITimeoutError.
8. Network / connection error → WeatherAPINetworkError.
9. save_observation() writes a row with correct field values.
"""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup – ensure the backend/ directory is importable regardless of how
# pytest is invoked (from project root or from backend/).
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.data_ingestion import (  # noqa: E402
    NormalisedObservation,
    WeatherAPIError,
    WeatherAPINetworkError,
    WeatherAPITimeoutError,
    WeatherDataError,
    _normalise_response,
    _safe_float,
    fetch_weather,
    save_observation,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

BASE_URL = "https://api.example.com/v1"
LAT, LON = 28.6139, 77.2090  # New Delhi


def _make_ok_payload(
    lat=LAT,
    lon=LON,
    time="2026-08-28T12:00",
    temperature=38.5,
    windspeed=15.2,
    relativehumidity_2m=55.0,
    precipitation=0.0,
) -> dict:
    """Return a minimal valid Open-Meteo-style response payload."""
    return {
        "latitude": lat,
        "longitude": lon,
        "current_weather": {
            "time": time,
            "temperature": temperature,
            "windspeed": windspeed,
            "relativehumidity_2m": relativehumidity_2m,
            "precipitation": precipitation,
        },
    }


def _mock_response(status_code: int = 200, json_data: object = None, text: str = "") -> MagicMock:
    """Return a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.ok = 200 <= status_code < 300
    mock.text = text
    if json_data is not None:
        mock.json.return_value = json_data
    else:
        mock.json.side_effect = ValueError("No JSON")
    return mock


# ---------------------------------------------------------------------------
# _safe_float helper
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_valid_int(self):
        assert _safe_float(42, "f") == 42.0

    def test_valid_string(self):
        assert _safe_float("3.14", "f") == pytest.approx(3.14)

    def test_none_returns_none(self):
        assert _safe_float(None, "f") is None

    def test_invalid_string_returns_none(self):
        assert _safe_float("not-a-number", "f") is None

    def test_invalid_dict_returns_none(self):
        assert _safe_float({}, "f") is None


# ---------------------------------------------------------------------------
# _normalise_response – pure unit tests (no HTTP, no DB)
# ---------------------------------------------------------------------------

class TestNormaliseResponse:

    def test_full_payload_normalised_correctly(self):
        """Test 1 – Successful response normalises all fields."""
        payload = _make_ok_payload()
        obs = _normalise_response(payload, LAT, LON)

        assert isinstance(obs, NormalisedObservation)
        assert obs.latitude == pytest.approx(LAT)
        assert obs.longitude == pytest.approx(LON)
        assert obs.timestamp == "2026-08-28T12:00"
        assert obs.temperature == pytest.approx(38.5)
        assert obs.humidity == pytest.approx(55.0)
        assert obs.wind_speed == pytest.approx(15.2)
        assert obs.precipitation == pytest.approx(0.0)

    def test_missing_optional_fields_become_none(self):
        """Test 2 – Partial payload: optional measurement fields → None."""
        payload = {
            "latitude": LAT,
            "longitude": LON,
            "current_weather": {
                "time": "2026-08-28T12:00",
                "temperature": 36.0,
                # windspeed, relativehumidity_2m, precipitation all absent
            },
        }
        obs = _normalise_response(payload, LAT, LON)

        assert obs.temperature == pytest.approx(36.0)
        assert obs.humidity is None
        assert obs.wind_speed is None
        assert obs.precipitation is None

    def test_missing_current_weather_raises(self):
        """Test 4 – Response without 'current_weather' → WeatherDataError."""
        with pytest.raises(WeatherDataError, match="current_weather"):
            _normalise_response({"latitude": LAT, "longitude": LON}, LAT, LON)

    def test_missing_time_raises(self):
        """Test 5 – 'current_weather' present but 'time' absent → WeatherDataError."""
        payload = {
            "latitude": LAT,
            "longitude": LON,
            "current_weather": {"temperature": 35.0},
        }
        with pytest.raises(WeatherDataError, match="time"):
            _normalise_response(payload, LAT, LON)

    def test_non_dict_response_raises(self):
        """Test 3 – Non-dict payload (e.g. a list) → WeatherDataError."""
        with pytest.raises(WeatherDataError, match="JSON object"):
            _normalise_response([1, 2, 3], LAT, LON)

    def test_api_coords_override_request_coords(self):
        """API grid-snapped coordinates should override the request coordinates."""
        payload = _make_ok_payload(lat=28.62, lon=77.21)
        obs = _normalise_response(payload, LAT, LON)
        assert obs.latitude == pytest.approx(28.62)
        assert obs.longitude == pytest.approx(77.21)

    def test_invalid_measurement_value_stored_as_none(self):
        """Non-numeric measurement values should become None, not raise."""
        payload = _make_ok_payload()
        payload["current_weather"]["temperature"] = "n/a"
        obs = _normalise_response(payload, LAT, LON)
        assert obs.temperature is None


# ---------------------------------------------------------------------------
# fetch_weather – mocked HTTP
# ---------------------------------------------------------------------------

class TestFetchWeather:

    @patch("services.data_ingestion.requests.get")
    def test_successful_fetch_returns_observation(self, mock_get):
        """Test 1 – Happy path: 200 OK with full payload."""
        mock_get.return_value = _mock_response(200, _make_ok_payload())

        obs = fetch_weather(LAT, LON, BASE_URL)

        assert isinstance(obs, NormalisedObservation)
        assert obs.temperature == pytest.approx(38.5)
        mock_get.assert_called_once()

    @patch("services.data_ingestion.requests.get")
    def test_api_key_sent_as_bearer_header(self, mock_get):
        """If an api_key is provided it must appear in the Authorization header."""
        mock_get.return_value = _mock_response(200, _make_ok_payload())
        fetch_weather(LAT, LON, BASE_URL, api_key="SECRET123")

        _, kwargs = mock_get.call_args
        assert kwargs["headers"].get("Authorization") == "Bearer SECRET123"

    @patch("services.data_ingestion.requests.get")
    def test_no_api_key_omits_auth_header(self, mock_get):
        """When api_key is empty the Authorization header must NOT be sent."""
        mock_get.return_value = _mock_response(200, _make_ok_payload())
        fetch_weather(LAT, LON, BASE_URL, api_key="")

        _, kwargs = mock_get.call_args
        assert "Authorization" not in kwargs["headers"]

    @patch("services.data_ingestion.requests.get")
    def test_http_error_raises_weather_api_error(self, mock_get):
        """Test 6 – Non-2xx HTTP status → WeatherAPIError."""
        mock_get.return_value = _mock_response(503, text="Service Unavailable")

        with pytest.raises(WeatherAPIError, match="503"):
            fetch_weather(LAT, LON, BASE_URL)

    @patch("services.data_ingestion.requests.get")
    def test_404_raises_weather_api_error(self, mock_get):
        """404 is a common API misconfiguration – must raise WeatherAPIError."""
        mock_get.return_value = _mock_response(404, text="Not Found")

        with pytest.raises(WeatherAPIError, match="404"):
            fetch_weather(LAT, LON, BASE_URL)

    @patch("services.data_ingestion.requests.get")
    def test_non_json_response_raises_weather_data_error(self, mock_get):
        """Test 3 – 200 OK but body is not JSON → WeatherDataError."""
        mock_response = _mock_response(200)
        mock_response.ok = True
        mock_response.json.side_effect = ValueError("No JSON object")
        mock_get.return_value = mock_response

        with pytest.raises(WeatherDataError):
            fetch_weather(LAT, LON, BASE_URL)

    @patch("services.data_ingestion.requests.get")
    def test_timeout_raises_weather_api_timeout_error(self, mock_get):
        """Test 7 – ReadTimeout → WeatherAPITimeoutError."""
        from requests.exceptions import ReadTimeout
        mock_get.side_effect = ReadTimeout()

        with pytest.raises(WeatherAPITimeoutError):
            fetch_weather(LAT, LON, BASE_URL, timeout=1)

    @patch("services.data_ingestion.requests.get")
    def test_connection_error_raises_weather_api_network_error(self, mock_get):
        """Test 8 – ConnectionError → WeatherAPINetworkError."""
        from requests.exceptions import ConnectionError as ReqConnErr
        mock_get.side_effect = ReqConnErr("refused")

        with pytest.raises(WeatherAPINetworkError):
            fetch_weather(LAT, LON, BASE_URL)

    @patch("services.data_ingestion.requests.get")
    def test_generic_request_exception_raises_network_error(self, mock_get):
        """Any other RequestException → WeatherAPINetworkError."""
        from requests.exceptions import RequestException
        mock_get.side_effect = RequestException("unknown")

        with pytest.raises(WeatherAPINetworkError):
            fetch_weather(LAT, LON, BASE_URL)

    @patch("services.data_ingestion.requests.get")
    def test_partial_response_does_not_raise(self, mock_get):
        """Test 2 – Partial payload (missing optional fields) must not raise."""
        partial = {
            "latitude": LAT,
            "longitude": LON,
            "current_weather": {"time": "2026-08-28T12:00", "temperature": 40.0},
        }
        mock_get.return_value = _mock_response(200, partial)

        obs = fetch_weather(LAT, LON, BASE_URL)
        assert obs.humidity is None
        assert obs.wind_speed is None
        assert obs.precipitation is None


# ---------------------------------------------------------------------------
# save_observation – in-memory SQLite, no Flask app context needed
# ---------------------------------------------------------------------------

class TestSaveObservation:
    """Test 9 – save_observation() writes the correct row to the database."""

    @pytest.fixture()
    def in_memory_db(self):
        """Provide a minimal Flask app + in-memory SQLite for DB tests."""
        import flask
        from models.database_models import db, WeatherObservation

        app = flask.Flask(__name__)
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
        app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
        db.init_app(app)

        with app.app_context():
            db.create_all()
            yield db, WeatherObservation

        # Tables are dropped automatically when the in-memory DB connection closes.

    def test_save_observation_persists_all_fields(self, in_memory_db):
        db_ext, WeatherObservation = in_memory_db

        obs = NormalisedObservation(
            latitude=LAT,
            longitude=LON,
            timestamp="2026-08-28T12:00",
            temperature=38.5,
            humidity=55.0,
            wind_speed=15.2,
            precipitation=0.0,
        )

        save_observation(obs, db_ext.session)
        db_ext.session.commit()

        rows = WeatherObservation.query.all()
        assert len(rows) == 1

        row = rows[0]
        assert row.latitude == pytest.approx(LAT)
        assert row.longitude == pytest.approx(LON)
        assert row.timestamp == "2026-08-28T12:00"
        assert row.temperature == pytest.approx(38.5)
        assert row.humidity == pytest.approx(55.0)
        assert row.wind_speed == pytest.approx(15.2)
        assert row.precipitation == pytest.approx(0.0)

    def test_save_observation_with_null_fields(self, in_memory_db):
        """Nullable measurement columns must accept None without error."""
        db_ext, WeatherObservation = in_memory_db

        obs = NormalisedObservation(
            latitude=LAT,
            longitude=LON,
            timestamp="2026-08-28T13:00",
            temperature=None,
            humidity=None,
            wind_speed=None,
            precipitation=None,
        )

        save_observation(obs, db_ext.session)
        db_ext.session.commit()

        row = WeatherObservation.query.first()
        assert row.temperature is None
        assert row.humidity is None
        assert row.wind_speed is None
        assert row.precipitation is None
