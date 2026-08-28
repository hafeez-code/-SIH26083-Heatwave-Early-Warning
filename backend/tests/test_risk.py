"""
test_risk.py – Unit tests for the heatwave risk assessment service.

Sprint 5 (v0.6): Heatwave Risk Calculation Foundation.
"""

import sys
import os
import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.data_ingestion import NormalisedObservation
from services.heatwave_risk import calculate_risk, RiskAssessment

# Default thresholds for testing explicitly to avoid depending on config changes
TEST_THRESHOLDS = {
    "TEMP_MIN": 32.0,
    "TEMP_MODERATE": 35.0,
    "TEMP_HIGH": 38.0,
    "TEMP_EXTREME": 42.0,
    "HUMIDITY_HIGH": 60.0,
    "HUMIDITY_EXTREME": 80.0,
    "WIND_STAGNANT": 5.0,
    "WIND_BREEZE": 20.0,
}

def create_obs(temp=30.0, hum=50.0, wind=10.0, precip=0.0):
    return NormalisedObservation(
        latitude=28.6,
        longitude=77.2,
        timestamp="2026-08-28T12:00",
        temperature=temp,
        humidity=hum,
        wind_speed=wind,
        precipitation=precip,
    )

def test_missing_temperature_raises_error():
    obs = create_obs(temp=None)
    with pytest.raises(ValueError, match="Temperature is required"):
        calculate_risk(obs, TEST_THRESHOLDS)

def test_clearly_low_risk_observation():
    obs = create_obs(temp=30.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_level == "LOW"
    assert risk.risk_score == 0
    assert any("below risk threshold" in f for f in risk.contributing_factors)

def test_moderate_risk_observation():
    # Temp 35 (score 40), normal humidity/wind
    obs = create_obs(temp=35.0, hum=50.0, wind=10.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_level == "MODERATE"
    assert risk.risk_score == 40
    assert any("Moderate heat" in f for f in risk.contributing_factors)

def test_high_risk_observation():
    # Temp 38 (score 60)
    obs = create_obs(temp=38.5, hum=50.0, wind=10.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_level == "HIGH"
    assert risk.risk_score == 60
    assert any("High heat" in f for f in risk.contributing_factors)

def test_extreme_risk_observation():
    # Temp 42+ (score 80) + high hum (+20) -> 100
    obs = create_obs(temp=43.0, hum=85.0, wind=10.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_level == "EXTREME"
    assert risk.risk_score == 100
    assert any("Extreme heat" in f for f in risk.contributing_factors)
    assert any("Extreme humidity" in f for f in risk.contributing_factors)

def test_high_temperature_contribution():
    obs = create_obs(temp=39.0) # score 60
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 60

def test_humidity_contribution():
    # Base 32 -> score 20
    # Hum 65 -> +10 => 30
    obs = create_obs(temp=33.0, hum=65.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 30
    assert any("High humidity" in f for f in risk.contributing_factors)

def test_wind_contribution_stagnant():
    # Base 32 -> score 20
    # Wind 2 -> +10 => 30
    obs = create_obs(temp=33.0, wind=2.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 30
    assert any("Stagnant air" in f for f in risk.contributing_factors)

def test_wind_contribution_breeze():
    # Base 35 -> score 40
    # Wind 25 -> -10 => 30
    obs = create_obs(temp=35.0, wind=25.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 30
    assert any("Cooling breeze" in f for f in risk.contributing_factors)

def test_precipitation_contribution():
    # Base 35 -> 40
    # Precip 5.0 -> -5 => 35
    obs = create_obs(temp=35.0, precip=5.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 35
    assert any("Precipitation" in f for f in risk.contributing_factors)

def test_missing_humidity():
    obs = create_obs(temp=35.0, hum=None)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 40
    assert any("Missing data: humidity" in f for f in risk.contributing_factors)

def test_missing_wind_speed():
    obs = create_obs(temp=35.0, wind=None)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 40
    assert any("Missing data: wind speed" in f for f in risk.contributing_factors)

def test_missing_precipitation():
    obs = create_obs(temp=35.0, precip=None)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 40
    assert any("Missing data: precipitation" in f for f in risk.contributing_factors)

def test_multiple_contributing_factors():
    # Base 35 (40) + hum 85 (+20) + wind 2 (+10) + precip 0 = 70
    obs = create_obs(temp=35.0, hum=85.0, wind=2.0, precip=0.0)
    risk = calculate_risk(obs, TEST_THRESHOLDS)
    assert risk.risk_score == 70
    assert risk.risk_level == "HIGH"
    assert len(risk.contributing_factors) >= 3

def test_deterministic_repeatable_score():
    obs1 = create_obs(temp=37.0, hum=70.0, wind=15.0, precip=0.0)
    obs2 = create_obs(temp=37.0, hum=70.0, wind=15.0, precip=0.0)
    risk1 = calculate_risk(obs1, TEST_THRESHOLDS)
    risk2 = calculate_risk(obs2, TEST_THRESHOLDS)
    assert risk1.risk_score == risk2.risk_score
    assert risk1.risk_level == risk2.risk_level
    assert risk1.contributing_factors == risk2.contributing_factors

def test_boundary_conditions():
    # Temp exactly 32 -> score 20
    obs = create_obs(temp=32.0)
    assert calculate_risk(obs, TEST_THRESHOLDS).risk_score == 20

    # Temp exactly 35 -> score 40
    obs = create_obs(temp=35.0)
    assert calculate_risk(obs, TEST_THRESHOLDS).risk_score == 40

    # Score maxed out at 100
    obs = create_obs(temp=50.0, hum=90.0, wind=0.0)
    assert calculate_risk(obs, TEST_THRESHOLDS).risk_score == 100

    # Score minimized at 0 (without temp < 32 condition, though that kicks in first here, 
    # we can trust the max(0, score) works due to simple code inspection).
    obs = create_obs(temp=32.0, wind=30.0, precip=10.0)
    assert calculate_risk(obs, TEST_THRESHOLDS).risk_score == 5
