"""
test_mortality_risk.py – Unit tests for the Mortality/Vulnerability Risk Index.

Covers: risk levels, demographic contribution, determinism, edge cases.
"""

import os
import sys

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.mortality_risk import (
    DemographicVulnerability,
    MortalityVulnerabilityAssessment,
    calculate_mortality_vulnerability_risk,
    _compute_vulnerability_factor,
    _score_to_level,
)

# ---------------------------------------------------------------------------
# Test configuration (matching config defaults for explicitness)
# ---------------------------------------------------------------------------

WEIGHTS = {
    "W_THERMAL": 0.5,
    "W_HEATWAVE": 0.5,
    "W_ELDERLY": 0.8,
    "W_CHILDREN": 0.4,
}

THRESHOLDS = {
    "SCORE_LOW": 30,
    "SCORE_MODERATE": 55,
    "SCORE_HIGH": 75,
}


def _make_assessment(
    thermal_score=40,
    heatwave_score=40,
    demographics=None,
    weights=None,
    thresholds=None,
):
    return calculate_mortality_vulnerability_risk(
        thermal_stress_score=thermal_score,
        heatwave_risk_score=heatwave_score,
        timestamp="2026-08-28T12:00",
        latitude=17.385,
        longitude=78.4867,
        demographics=demographics,
        weights=weights or WEIGHTS,
        thresholds=thresholds or THRESHOLDS,
    )


# ---------------------------------------------------------------------------
# Risk levels
# ---------------------------------------------------------------------------

class TestRiskLevels:
    def test_low_risk(self):
        # Both scores low → base = 0.5*10 + 0.5*10 = 10 → LOW
        result = _make_assessment(thermal_score=10, heatwave_score=10)
        assert result.risk_level == "LOW"
        assert result.risk_score < THRESHOLDS["SCORE_LOW"]

    def test_moderate_risk(self):
        # Base = 0.5*40 + 0.5*40 = 40 → MODERATE
        result = _make_assessment(thermal_score=40, heatwave_score=40)
        assert result.risk_level == "MODERATE"
        assert THRESHOLDS["SCORE_LOW"] <= result.risk_score < THRESHOLDS["SCORE_MODERATE"]

    def test_high_risk(self):
        # Base = 0.5*70 + 0.5*70 = 70 → HIGH
        result = _make_assessment(thermal_score=70, heatwave_score=70)
        assert result.risk_level in ("HIGH", "EXTREME")

    def test_extreme_risk(self):
        # Base = 0.5*100 + 0.5*100 = 100 → EXTREME
        result = _make_assessment(thermal_score=100, heatwave_score=100)
        assert result.risk_level == "EXTREME"
        assert result.risk_score == 100


# ---------------------------------------------------------------------------
# Demographic contribution
# ---------------------------------------------------------------------------

class TestDemographicContribution:
    def test_no_demographics_gives_factor_1(self):
        result = _make_assessment(thermal_score=40, heatwave_score=40, demographics=None)
        assert result.vulnerability_factor == 1.0

    def test_elderly_population_increases_score(self):
        no_demo = _make_assessment(thermal_score=40, heatwave_score=40, demographics=None)
        demo = DemographicVulnerability(pct_elderly=20.0)
        with_demo = _make_assessment(thermal_score=40, heatwave_score=40, demographics=demo)
        assert with_demo.risk_score > no_demo.risk_score
        assert with_demo.vulnerability_factor > 1.0

    def test_children_population_increases_score(self):
        no_demo = _make_assessment(thermal_score=40, heatwave_score=40, demographics=None)
        demo = DemographicVulnerability(pct_children=30.0)
        with_demo = _make_assessment(thermal_score=40, heatwave_score=40, demographics=demo)
        assert with_demo.risk_score > no_demo.risk_score

    def test_elderly_has_higher_weight_than_children(self):
        """For equal percentages, elderly should amplify more than children."""
        demo_elderly = DemographicVulnerability(pct_elderly=20.0)
        demo_children = DemographicVulnerability(pct_children=20.0)
        r_elderly = _make_assessment(thermal_score=40, heatwave_score=40, demographics=demo_elderly)
        r_children = _make_assessment(thermal_score=40, heatwave_score=40, demographics=demo_children)
        assert r_elderly.vulnerability_factor > r_children.vulnerability_factor

    def test_combined_demographics_amplifies_further(self):
        demo_elderly = DemographicVulnerability(pct_elderly=20.0)
        demo_both = DemographicVulnerability(pct_elderly=20.0, pct_children=15.0)
        r_elderly = _make_assessment(thermal_score=40, heatwave_score=40, demographics=demo_elderly)
        r_both = _make_assessment(thermal_score=40, heatwave_score=40, demographics=demo_both)
        assert r_both.vulnerability_factor > r_elderly.vulnerability_factor

    def test_vulnerability_notes_in_contributing_factors(self):
        demo = DemographicVulnerability(
            pct_elderly=10.0,
            vulnerability_notes="High outdoor worker density"
        )
        result = _make_assessment(thermal_score=40, heatwave_score=40, demographics=demo)
        assert any("outdoor worker" in f for f in result.contributing_factors)


# ---------------------------------------------------------------------------
# DemographicVulnerability validation
# ---------------------------------------------------------------------------

class TestDemographicVulnerabilityValidation:
    def test_valid_demographics_created_successfully(self):
        demo = DemographicVulnerability(pct_elderly=10.0, pct_children=25.0)
        assert demo.pct_elderly == 10.0
        assert demo.pct_children == 25.0

    def test_none_demographics_is_valid(self):
        demo = DemographicVulnerability()
        assert demo.pct_elderly is None
        assert demo.pct_children is None

    def test_invalid_pct_elderly_too_high_raises(self):
        with pytest.raises(ValueError, match="pct_elderly"):
            DemographicVulnerability(pct_elderly=110.0)

    def test_invalid_pct_elderly_negative_raises(self):
        with pytest.raises(ValueError, match="pct_elderly"):
            DemographicVulnerability(pct_elderly=-5.0)

    def test_invalid_pct_children_too_high_raises(self):
        with pytest.raises(ValueError, match="pct_children"):
            DemographicVulnerability(pct_children=200.0)

    def test_boundary_values_valid(self):
        demo = DemographicVulnerability(pct_elderly=0.0, pct_children=100.0)
        assert demo.pct_elderly == 0.0
        assert demo.pct_children == 100.0


# ---------------------------------------------------------------------------
# Score bounds
# ---------------------------------------------------------------------------

class TestScoreBounds:
    def test_score_clamped_to_100(self):
        demo = DemographicVulnerability(pct_elderly=100.0, pct_children=100.0)
        result = _make_assessment(thermal_score=100, heatwave_score=100, demographics=demo)
        assert result.risk_score <= 100

    def test_score_never_below_zero(self):
        result = _make_assessment(thermal_score=0, heatwave_score=0)
        assert result.risk_score >= 0


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_produce_same_output(self):
        demo = DemographicVulnerability(pct_elderly=15.0, pct_children=20.0)
        r1 = _make_assessment(thermal_score=50, heatwave_score=60, demographics=demo)
        r2 = _make_assessment(thermal_score=50, heatwave_score=60, demographics=demo)
        assert r1.risk_score == r2.risk_score
        assert r1.risk_level == r2.risk_level
        assert r1.vulnerability_factor == r2.vulnerability_factor
        assert r1.contributing_factors == r2.contributing_factors

    def test_higher_inputs_give_higher_score(self):
        r_low = _make_assessment(thermal_score=10, heatwave_score=10)
        r_high = _make_assessment(thermal_score=90, heatwave_score=90)
        assert r_high.risk_score > r_low.risk_score


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------

class TestOutputStructure:
    def test_returns_mortality_vulnerability_assessment(self):
        result = _make_assessment(thermal_score=50, heatwave_score=50)
        assert isinstance(result, MortalityVulnerabilityAssessment)

    def test_contributing_factors_non_empty_list(self):
        result = _make_assessment(thermal_score=50, heatwave_score=50)
        assert isinstance(result.contributing_factors, list)
        assert len(result.contributing_factors) > 0

    def test_factors_contain_base_score_description(self):
        result = _make_assessment(thermal_score=50, heatwave_score=50)
        factors_text = " ".join(result.contributing_factors)
        assert "thermal stress" in factors_text.lower() or "heatwave" in factors_text.lower()

    def test_methodology_note_present(self):
        result = _make_assessment(thermal_score=50, heatwave_score=50)
        assert result.methodology_note
        assert "prototype" in result.methodology_note.lower()

    def test_mortality_note_says_not_validated(self):
        result = _make_assessment(thermal_score=50, heatwave_score=50)
        note = result.methodology_note.lower()
        assert "not" in note  # "NOT a medically validated..."

    def test_latitude_longitude_timestamp_preserved(self):
        result = calculate_mortality_vulnerability_risk(
            thermal_stress_score=40,
            heatwave_risk_score=40,
            timestamp="2026-08-28T12:00",
            latitude=17.385,
            longitude=78.4867,
        )
        assert result.latitude == 17.385
        assert result.longitude == 78.4867
        assert result.timestamp == "2026-08-28T12:00"


# ---------------------------------------------------------------------------
# Level mapping
# ---------------------------------------------------------------------------

class TestLevelMapping:
    def test_score_below_low_threshold(self):
        assert _score_to_level(0, THRESHOLDS) == "LOW"
        assert _score_to_level(29, THRESHOLDS) == "LOW"

    def test_score_at_low_threshold(self):
        assert _score_to_level(30, THRESHOLDS) == "MODERATE"

    def test_score_at_moderate_threshold(self):
        assert _score_to_level(55, THRESHOLDS) == "HIGH"

    def test_score_at_high_threshold(self):
        assert _score_to_level(75, THRESHOLDS) == "EXTREME"

    def test_score_at_100(self):
        assert _score_to_level(100, THRESHOLDS) == "EXTREME"


# ---------------------------------------------------------------------------
# Vulnerability factor computation
# ---------------------------------------------------------------------------

class TestVulnerabilityFactor:
    def test_no_demographics_returns_factor_1(self):
        factor, descriptions = _compute_vulnerability_factor(None, WEIGHTS)
        assert factor == 1.0
        assert len(descriptions) > 0

    def test_20pct_elderly_applies_correct_formula(self):
        demo = DemographicVulnerability(pct_elderly=20.0)
        factor, _ = _compute_vulnerability_factor(demo, WEIGHTS)
        expected = 1.0 + (20.0 / 100.0) * WEIGHTS["W_ELDERLY"]
        assert abs(factor - expected) < 1e-9

    def test_30pct_children_applies_correct_formula(self):
        demo = DemographicVulnerability(pct_children=30.0)
        factor, _ = _compute_vulnerability_factor(demo, WEIGHTS)
        expected = 1.0 + (30.0 / 100.0) * WEIGHTS["W_CHILDREN"]
        assert abs(factor - expected) < 1e-9
