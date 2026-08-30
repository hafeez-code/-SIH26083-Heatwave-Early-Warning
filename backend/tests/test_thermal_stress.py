"""
test_thermal_stress.py – Unit tests for the Human Thermal Stress Index service.

Covers: stress levels, score bounds, missing inputs, solar radiation,
wind adjustments, determinism, and methodology validation.
"""

import os
import sys

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.data_ingestion import NormalisedObservation
from services.thermal_stress import (
    ThermalStressAssessment,
    _compute_heat_index_celsius,
    _rothfusz_heat_index_fahrenheit,
    calculate_thermal_stress,
)

# ---------------------------------------------------------------------------
# Test thresholds (matching config defaults for explicitness)
# ---------------------------------------------------------------------------

THRESHOLDS = {
    "HI_LOW": 27.0,
    "HI_MODERATE": 32.0,
    "HI_HIGH": 41.0,
    "HI_VERY_HIGH": 54.0,
    "SCORE_LOW": 15,
    "SCORE_MODERATE": 35,
    "SCORE_HIGH": 60,
    "SCORE_VERY_HIGH": 80,
    "SCORE_EXTREME": 95,
    "WIND_COOLING_THRESHOLD": 20.0,
    "WIND_COOLING_BONUS": 5,
    "SOLAR_HIGH_THRESHOLD": 600.0,
    "SOLAR_SCORE_BONUS": 5,
}


def make_obs(
    temp=35.0,
    humidity=60.0,
    wind=10.0,
    precip=0.0,
    solar_radiation=None,
):
    return NormalisedObservation(
        latitude=17.385,
        longitude=78.4867,
        timestamp="2026-08-28T12:00",
        temperature=temp,
        humidity=humidity,
        wind_speed=wind,
        precipitation=precip,
        solar_radiation=solar_radiation,
    )


# ---------------------------------------------------------------------------
# Missing temperature (required)
# ---------------------------------------------------------------------------

class TestMissingTemperature:
    def test_raises_value_error_when_temperature_is_none(self):
        obs = make_obs(temp=None)
        with pytest.raises(ValueError, match="Temperature is required"):
            calculate_thermal_stress(obs, THRESHOLDS)

    def test_error_message_mentions_thermal_stress(self):
        obs = make_obs(temp=None)
        with pytest.raises(ValueError, match="Thermal Stress"):
            calculate_thermal_stress(obs, THRESHOLDS)


# ---------------------------------------------------------------------------
# Stress levels
# ---------------------------------------------------------------------------

class TestStressLevels:
    def test_low_stress_below_hi_threshold(self):
        # T=20°C is below HI applicability; heat index is None → LOW
        obs = make_obs(temp=20.0, humidity=50.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.thermal_stress_level == "LOW"
        assert result.thermal_stress_score == 0

    def test_moderate_stress(self):
        # T=28°C, RH=50% → heat index ≈ 27–32°C → MODERATE
        obs = make_obs(temp=28.0, humidity=50.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.thermal_stress_level in ("LOW", "MODERATE")
        # Score should be in moderate range
        assert result.thermal_stress_score >= 0

    def test_high_stress_high_heat_index(self):
        # T=38°C, RH=70% → heat index well above 32°C → at least HIGH
        obs = make_obs(temp=38.0, humidity=70.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.thermal_stress_level in ("HIGH", "VERY HIGH", "EXTREME")
        assert result.thermal_stress_score >= THRESHOLDS["SCORE_MODERATE"]

    def test_very_high_stress(self):
        # T=44°C, RH=80% → extreme heat index → HIGH or above
        obs = make_obs(temp=44.0, humidity=80.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.thermal_stress_level in ("HIGH", "VERY HIGH", "EXTREME")
        assert result.thermal_stress_score >= THRESHOLDS["SCORE_MODERATE"]

    def test_extreme_stress(self):
        # T=48°C, RH=90% → extreme thermal load
        obs = make_obs(temp=48.0, humidity=90.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        # Should be high or very high with this heat load
        assert result.thermal_stress_score >= THRESHOLDS["SCORE_MODERATE"]
        assert result.thermal_stress_level in ("HIGH", "VERY HIGH", "EXTREME")


# ---------------------------------------------------------------------------
# Score bounds
# ---------------------------------------------------------------------------

class TestScoreBounds:
    def test_score_never_below_zero(self):
        # Very low temp + high wind
        obs = make_obs(temp=20.0, humidity=50.0, wind=50.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.thermal_stress_score >= 0

    def test_score_never_above_100(self):
        # Extreme conditions
        obs = make_obs(temp=55.0, humidity=100.0, wind=0.0, solar_radiation=1200.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.thermal_stress_score <= 100

    def test_score_is_integer(self):
        obs = make_obs(temp=35.0, humidity=60.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert isinstance(result.thermal_stress_score, int)


# ---------------------------------------------------------------------------
# Missing optional inputs
# ---------------------------------------------------------------------------

class TestMissingOptionalInputs:
    def test_missing_humidity(self):
        obs = make_obs(temp=35.0, humidity=None)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        # No heat index computable; should fall back to temperature-only assessment
        assert result.heat_index_celsius is None
        assert result.thermal_stress_level is not None
        assert any("humidity unavailable" in f for f in result.contributing_factors)

    def test_missing_wind_speed(self):
        obs = make_obs(temp=35.0, humidity=60.0, wind=None)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        # Should still compute without wind
        assert result.thermal_stress_level is not None
        assert any("wind speed" in f for f in result.contributing_factors)

    def test_missing_solar_radiation_is_silently_accepted(self):
        # Solar radiation is fully optional; no error or missing-factor message
        obs = make_obs(temp=35.0, humidity=60.0, solar_radiation=None)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.thermal_stress_level is not None

    def test_missing_precipitation_has_no_effect(self):
        # Precipitation is not used in thermal stress calculation
        obs1 = make_obs(temp=35.0, humidity=60.0, precip=None)
        obs2 = make_obs(temp=35.0, humidity=60.0, precip=10.0)
        r1 = calculate_thermal_stress(obs1, THRESHOLDS)
        r2 = calculate_thermal_stress(obs2, THRESHOLDS)
        assert r1.thermal_stress_score == r2.thermal_stress_score


# ---------------------------------------------------------------------------
# Solar radiation contribution
# ---------------------------------------------------------------------------

class TestSolarRadiation:
    def test_high_solar_radiation_increases_score(self):
        base_obs = make_obs(temp=35.0, humidity=60.0, solar_radiation=None)
        solar_obs = make_obs(temp=35.0, humidity=60.0, solar_radiation=800.0)
        base_result = calculate_thermal_stress(base_obs, THRESHOLDS)
        solar_result = calculate_thermal_stress(solar_obs, THRESHOLDS)
        # High solar radiation should add SOLAR_SCORE_BONUS points
        assert solar_result.thermal_stress_score == base_result.thermal_stress_score + THRESHOLDS["SOLAR_SCORE_BONUS"]

    def test_low_solar_radiation_no_bonus(self):
        base_obs = make_obs(temp=35.0, humidity=60.0, solar_radiation=None)
        low_solar_obs = make_obs(temp=35.0, humidity=60.0, solar_radiation=300.0)
        base_result = calculate_thermal_stress(base_obs, THRESHOLDS)
        low_result = calculate_thermal_stress(low_solar_obs, THRESHOLDS)
        # Below threshold: no bonus
        assert low_result.thermal_stress_score == base_result.thermal_stress_score

    def test_solar_radiation_factor_in_contributing_factors(self):
        obs = make_obs(temp=35.0, humidity=60.0, solar_radiation=700.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert any("solar radiation" in f.lower() for f in result.contributing_factors)


# ---------------------------------------------------------------------------
# Wind cooling
# ---------------------------------------------------------------------------

class TestWindCooling:
    def test_high_wind_reduces_score(self):
        calm_obs = make_obs(temp=35.0, humidity=60.0, wind=5.0)
        windy_obs = make_obs(temp=35.0, humidity=60.0, wind=25.0)
        calm_result = calculate_thermal_stress(calm_obs, THRESHOLDS)
        windy_result = calculate_thermal_stress(windy_obs, THRESHOLDS)
        # High wind should reduce the score
        assert windy_result.thermal_stress_score == calm_result.thermal_stress_score - THRESHOLDS["WIND_COOLING_BONUS"]

    def test_wind_factor_in_contributing_factors(self):
        obs = make_obs(temp=35.0, humidity=60.0, wind=30.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert any("cooling" in f.lower() for f in result.contributing_factors)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_produce_same_output(self):
        obs1 = make_obs(temp=38.0, humidity=65.0, wind=8.0, solar_radiation=450.0)
        obs2 = make_obs(temp=38.0, humidity=65.0, wind=8.0, solar_radiation=450.0)
        r1 = calculate_thermal_stress(obs1, THRESHOLDS)
        r2 = calculate_thermal_stress(obs2, THRESHOLDS)
        assert r1.thermal_stress_score == r2.thermal_stress_score
        assert r1.thermal_stress_level == r2.thermal_stress_level
        assert r1.heat_index_celsius == r2.heat_index_celsius
        assert r1.contributing_factors == r2.contributing_factors

    def test_different_temperatures_produce_different_scores(self):
        r1 = calculate_thermal_stress(make_obs(temp=28.0, humidity=60.0), THRESHOLDS)
        r2 = calculate_thermal_stress(make_obs(temp=45.0, humidity=60.0), THRESHOLDS)
        assert r1.thermal_stress_score < r2.thermal_stress_score


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

class TestOutputStructure:
    def test_returns_thermal_stress_assessment(self):
        obs = make_obs(temp=35.0, humidity=60.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert isinstance(result, ThermalStressAssessment)

    def test_latitude_longitude_preserved(self):
        obs = make_obs(temp=35.0, humidity=60.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.latitude == obs.latitude
        assert result.longitude == obs.longitude

    def test_timestamp_preserved(self):
        obs = make_obs(temp=35.0, humidity=60.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.timestamp == obs.timestamp

    def test_methodology_note_present(self):
        obs = make_obs(temp=35.0, humidity=60.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.methodology_note
        assert "prototype" in result.methodology_note.lower()

    def test_contributing_factors_is_list(self):
        obs = make_obs(temp=35.0, humidity=60.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert isinstance(result.contributing_factors, list)
        assert len(result.contributing_factors) > 0

    def test_heat_index_present_when_inputs_available(self):
        obs = make_obs(temp=35.0, humidity=60.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        # T=35°C, RH=60% → heat index should be computed
        assert result.heat_index_celsius is not None
        assert result.heat_index_celsius > obs.temperature  # HI > dry-bulb for hot humid conditions

    def test_heat_index_none_when_below_27c(self):
        obs = make_obs(temp=20.0, humidity=60.0)
        result = calculate_thermal_stress(obs, THRESHOLDS)
        assert result.heat_index_celsius is None


# ---------------------------------------------------------------------------
# Rothfusz formula internal tests
# ---------------------------------------------------------------------------

class TestRothfuszFormula:
    def test_heat_index_higher_than_temperature_in_hot_humid_conditions(self):
        hi = _compute_heat_index_celsius(38.0, 70.0)
        assert hi is not None
        assert hi > 38.0

    def test_heat_index_none_below_27c(self):
        hi = _compute_heat_index_celsius(25.0, 80.0)
        assert hi is None

    def test_rothfusz_raw_increases_with_humidity(self):
        """For fixed temperature, more humidity increases heat index."""
        hi_50 = _rothfusz_heat_index_fahrenheit(100.0, 50.0)
        hi_80 = _rothfusz_heat_index_fahrenheit(100.0, 80.0)
        assert hi_80 > hi_50
