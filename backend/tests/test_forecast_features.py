"""Tests for deterministic forecast feature engineering."""

import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.forecast_features import build_forecast_features
from services.forecast_ingestion import NormalisedForecast, prepare_forecast_features


def _forecast(timestamp, temperature, humidity=50.0, wind_speed=10.0, precipitation=0.0):
    return NormalisedForecast(timestamp, temperature, humidity, wind_speed, precipitation)


def test_builds_raw_and_derived_features():
    features = build_forecast_features([_forecast("2026-08-29T12:00", 41.0, 60.0, 12.0, 0.2)])
    assert features == [{
        "forecast_timestamp": "2026-08-29T12:00",
        "temperature": 41.0,
        "humidity": 60.0,
        "wind_speed": 12.0,
        "precipitation": 0.2,
        "temperature_humidity_interaction": 2460.0,
        "temperature_change": None,
        "temperature_rolling_mean_3": None,
        "temperature_rolling_max_3": None,
        "precipitation_indicator": 1,
        "high_temperature_indicator": 1,
    }]


def test_orders_forecasts_before_temperature_and_rolling_calculations():
    features = build_forecast_features([
        _forecast("2026-08-29T14:00", 42.0),
        _forecast("2026-08-29T12:00", 38.0),
        _forecast("2026-08-29T13:00", 40.0),
    ])
    assert [item["forecast_timestamp"] for item in features] == [
        "2026-08-29T12:00", "2026-08-29T13:00", "2026-08-29T14:00"
    ]
    assert [item["temperature_change"] for item in features] == [None, 2.0, 2.0]
    assert features[2]["temperature_rolling_mean_3"] == 40.0
    assert features[2]["temperature_rolling_max_3"] == 42.0


def test_missing_values_are_not_imputed_and_indicators_are_explicit():
    features = build_forecast_features([
        _forecast("2026-08-29T12:00", 39.0, humidity=None, precipitation=None),
        _forecast("2026-08-29T13:00", None, precipitation=0.0),
        _forecast("2026-08-29T14:00", 41.0, precipitation=1.0),
    ])
    assert features[0]["temperature_humidity_interaction"] is None
    assert features[0]["precipitation_indicator"] is None
    assert features[1]["temperature_change"] is None
    assert features[1]["high_temperature_indicator"] is None
    assert features[2]["temperature_change"] is None
    assert features[2]["temperature_rolling_mean_3"] is None
    assert [item["precipitation_indicator"] for item in features[1:]] == [0, 1]
    assert [item["high_temperature_indicator"] for item in features] == [0, None, 1]


def test_groups_temporal_features_by_area_and_is_deterministic():
    records = [
        {"area_id": 2, "forecast_timestamp": "2026-08-29T13:00", "temperature": 35.0,
         "humidity": 50.0, "wind_speed": 5.0, "precipitation": 0.0},
        {"area_id": 1, "forecast_timestamp": "2026-08-29T12:00", "temperature": 40.0,
         "humidity": 50.0, "wind_speed": 5.0, "precipitation": 0.0},
        {"area_id": 2, "forecast_timestamp": "2026-08-29T12:00", "temperature": 30.0,
         "humidity": 50.0, "wind_speed": 5.0, "precipitation": 0.0},
    ]
    first = build_forecast_features(records)
    assert [item["temperature"] for item in first] == [40.0, 30.0, 35.0]
    assert [item["temperature_change"] for item in first] == [None, None, 5.0]
    assert first == build_forecast_features(records)


def test_handles_empty_input_and_preserves_v010_compatibility_format():
    records = [_forecast("2026-08-29T12:00", 39.0, 60.0, 10.0, 0.0)]
    assert build_forecast_features([]) == []
    assert prepare_forecast_features(records) == [{
        "forecast_timestamp": "2026-08-29T12:00",
        "temperature": 39.0,
        "humidity": 60.0,
        "wind_speed": 10.0,
        "precipitation": 0.0,
    }]
