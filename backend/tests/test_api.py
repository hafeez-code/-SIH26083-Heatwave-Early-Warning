"""
test_api.py – Unit tests for REST API endpoints.

Sprint 7 (v0.7): Risk API endpoint.
"""

import sys
import os
import pytest
from unittest.mock import patch

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app import create_app
from services.data_ingestion import (
    NormalisedObservation, 
    WeatherAPITimeoutError,
    WeatherAPIError,
    WeatherDataError
)

@pytest.fixture
def client():
    app = create_app("default")
    with app.test_client() as client:
        yield client

def test_risk_missing_latitude(client):
    response = client.get("/api/risk?longitude=78.4")
    assert response.status_code == 400
    assert "Missing latitude" in response.get_json()["message"]

def test_risk_missing_longitude(client):
    response = client.get("/api/risk?latitude=17.3")
    assert response.status_code == 400
    assert "Missing latitude or longitude" in response.get_json()["message"]

def test_risk_non_numeric_latitude(client):
    response = client.get("/api/risk?latitude=abc&longitude=78.4")
    assert response.status_code == 400
    assert "numeric" in response.get_json()["message"]

def test_risk_non_numeric_longitude(client):
    response = client.get("/api/risk?latitude=17.3&longitude=xyz")
    assert response.status_code == 400
    assert "numeric" in response.get_json()["message"]

def test_risk_out_of_range_latitude(client):
    response = client.get("/api/risk?latitude=91.0&longitude=78.4")
    assert response.status_code == 400
    assert "between -90 and 90" in response.get_json()["message"]

def test_risk_out_of_range_longitude(client):
    response = client.get("/api/risk?latitude=17.3&longitude=181.0")
    assert response.status_code == 400
    assert "between -180 and 180" in response.get_json()["message"]

@patch("routes.risk.fetch_weather")
def test_risk_weather_api_timeout(mock_fetch, client):
    mock_fetch.side_effect = WeatherAPITimeoutError("timeout")
    response = client.get("/api/risk?latitude=17.3&longitude=78.4")
    assert response.status_code == 504
    assert "timed out" in response.get_json()["message"]

@patch("routes.risk.fetch_weather")
def test_risk_weather_api_error(mock_fetch, client):
    mock_fetch.side_effect = WeatherAPIError("Bad response")
    response = client.get("/api/risk?latitude=17.3&longitude=78.4")
    assert response.status_code == 502
    assert "Weather API error" in response.get_json()["message"]

@patch("routes.risk.fetch_weather")
def test_risk_successful_request(mock_fetch, client):
    mock_obs = NormalisedObservation(
        latitude=17.385,
        longitude=78.4867,
        timestamp="2026-08-28T12:00",
        temperature=38.5,
        humidity=65.0,
        wind_speed=12.0,
        precipitation=0.0
    )
    mock_fetch.return_value = mock_obs

    response = client.get("/api/risk?latitude=17.3850&longitude=78.4867")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    
    res_data = data["data"]
    assert res_data["location"]["latitude"] == 17.385
    assert res_data["location"]["longitude"] == 78.4867
    
    assert res_data["weather"]["temperature"] == 38.5
    
    # Check that risk score is calculated and structured properly
    assert "score" in res_data["risk"]
    assert "level" in res_data["risk"]
    assert "contributing_factors" in res_data["risk"]
    assert len(res_data["risk"]["contributing_factors"]) > 0

@patch("routes.risk.fetch_weather")
def test_risk_malformed_weather_data(mock_fetch, client):
    # Temperature None will raise ValueError from calculate_risk
    mock_obs = NormalisedObservation(
        latitude=17.385,
        longitude=78.4867,
        timestamp="2026-08-28T12:00",
        temperature=None,
        humidity=65.0,
        wind_speed=12.0,
        precipitation=0.0
    )
    mock_fetch.return_value = mock_obs

    response = client.get("/api/risk?latitude=17.3850&longitude=78.4867")
    assert response.status_code == 422
    assert "Data processing error" in response.get_json()["message"]

@patch("routes.risk.fetch_weather")
def test_unexpected_internal_error(mock_fetch, client):
    mock_fetch.side_effect = Exception("Unexpected BOOM!")
    response = client.get("/api/risk?latitude=17.3850&longitude=78.4867")
    assert response.status_code == 500
    assert "unexpected internal error" in response.get_json()["message"]
