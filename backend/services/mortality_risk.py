"""
mortality_risk.py – Mortality/Vulnerability Risk Index for SIH26083 v0.19.

PROTOTYPE DISCLAIMER
--------------------
This module implements a prototype Mortality/Vulnerability Risk Index for
the SIH26083 academic prototype.  It is NOT a medically validated mortality
probability or a clinically validated health-risk metric.

Results represent a transparent, rule-based environmental vulnerability
indicator combining thermal stress, heatwave severity, and demographic
risk amplification.  The term "mortality/vulnerability" is used in the
sense of the SIH project requirement; it does NOT mean the system predicts
actual deaths or is validated against mortality statistics.

Methodology
-----------
The index combines two existing risk layers with explicit, configurable
weights and then applies a demographic vulnerability multiplier:

    base_score = thermal_stress_score * W_THERMAL
               + heatwave_risk_score  * W_HEATWAVE

    vulnerability_factor = 1.0
                         + (pct_elderly   / 100) * W_ELDERLY
                         + (pct_children  / 100) * W_CHILDREN

    raw_score  = base_score * vulnerability_factor
    final_score = clamp(raw_score, 0, 100)

Where:
  W_THERMAL   — weight of thermal stress contribution (default 0.5)
  W_HEATWAVE  — weight of heatwave risk contribution (default 0.5)
  W_ELDERLY   — per-percentage-point amplification for elderly pop (default 0.8)
  W_CHILDREN  — per-percentage-point amplification for children pop (default 0.4)

All weights and thresholds are read from Config and can be overridden by
callers, making the index fully configurable and transparent.

Level mapping (score → level):
  [0,   SCORE_LOW)      → LOW
  [SCORE_LOW, SCORE_MODERATE)   → MODERATE
  [SCORE_MODERATE, SCORE_HIGH)  → HIGH
  [SCORE_HIGH, 100]             → EXTREME
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from config import Config

# --------------------------------------------------------------------------- #
# Prototype disclaimer text                                                    #
# --------------------------------------------------------------------------- #

_DISCLAIMER = (
    "Prototype Mortality/Vulnerability Risk Index (SIH26083 v0.19). "
    "Transparent weighted combination of thermal stress and heatwave risk "
    "with demographic amplification. "
    "NOT a medically validated mortality probability or clinical prediction."
)


# --------------------------------------------------------------------------- #
# Public dataclasses                                                           #
# --------------------------------------------------------------------------- #

@dataclass
class DemographicVulnerability:
    """Area-level aggregate demographic vulnerability factors.

    Only population-level statistics are represented here.
    No personally identifiable information is used or stored.

    Attributes
    ----------
    pct_elderly:
        Percentage of area population aged ≥65 (0.0–100.0), or None.
    pct_children:
        Percentage of area population aged <18 (0.0–100.0), or None.
    vulnerability_notes:
        Optional free-text description of known vulnerability context.
    """

    pct_elderly: Optional[float] = None
    pct_children: Optional[float] = None
    vulnerability_notes: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate that percentage values are in [0, 100]."""
        for attr, value in (
            ("pct_elderly", self.pct_elderly),
            ("pct_children", self.pct_children),
        ):
            if value is not None and not (0.0 <= value <= 100.0):
                raise ValueError(
                    f"DemographicVulnerability.{attr} must be between 0 and 100, got {value}."
                )


@dataclass
class MortalityVulnerabilityAssessment:
    """Structured Mortality/Vulnerability Risk assessment.

    Attributes
    ----------
    risk_level:
        Categorical level: LOW, MODERATE, HIGH, or EXTREME.
    risk_score:
        Prototype index score 0–100.
    vulnerability_factor:
        The demographic amplification multiplier applied.
        1.0 means no demographic data was available or no amplification.
        Values > 1.0 indicate demographic amplification was applied.
    contributing_factors:
        Ordered list of human-readable explanations of each score component.
    timestamp:
        ISO-8601 timestamp of the source observation.
    latitude, longitude:
        Geographic coordinates of the assessment.
    methodology_note:
        Prototype disclaimer text.
    """

    risk_level: str
    risk_score: int
    vulnerability_factor: float
    contributing_factors: List[str]
    timestamp: str
    latitude: float
    longitude: float
    methodology_note: str = field(default=_DISCLAIMER)


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #

def _compute_vulnerability_factor(
    demographics: Optional[DemographicVulnerability],
    weights: dict,
) -> tuple[float, List[str]]:
    """Compute the demographic vulnerability multiplier.

    Returns
    -------
    (factor, factor_descriptions)
        factor       — float ≥ 1.0
        descriptions — list of factor explanation strings
    """
    if demographics is None:
        return 1.0, ["No demographic data available; vulnerability factor = 1.0 (no amplification)"]

    factor = 1.0
    descriptions: List[str] = []

    w_elderly = weights["W_ELDERLY"]
    w_children = weights["W_CHILDREN"]

    if demographics.pct_elderly is not None:
        elderly_contrib = (demographics.pct_elderly / 100.0) * w_elderly
        factor += elderly_contrib
        descriptions.append(
            f"Elderly population {demographics.pct_elderly:.1f}% "
            f"(+{elderly_contrib:.3f} amplification, weight {w_elderly})"
        )

    if demographics.pct_children is not None:
        children_contrib = (demographics.pct_children / 100.0) * w_children
        factor += children_contrib
        descriptions.append(
            f"Children population {demographics.pct_children:.1f}% "
            f"(+{children_contrib:.3f} amplification, weight {w_children})"
        )

    if demographics.vulnerability_notes:
        descriptions.append(f"Local context: {demographics.vulnerability_notes}")

    if not descriptions:
        descriptions.append("Demographic data present but no percentages provided; vulnerability factor = 1.0")

    return factor, descriptions


def _score_to_level(score: int, thresholds: dict) -> str:
    """Map a 0–100 score to a mortality/vulnerability risk level string."""
    if score < thresholds["SCORE_LOW"]:
        return "LOW"
    elif score < thresholds["SCORE_MODERATE"]:
        return "MODERATE"
    elif score < thresholds["SCORE_HIGH"]:
        return "HIGH"
    else:
        return "EXTREME"


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def calculate_mortality_vulnerability_risk(
    thermal_stress_score: int,
    heatwave_risk_score: int,
    timestamp: str,
    latitude: float,
    longitude: float,
    demographics: Optional[DemographicVulnerability] = None,
    weights: Optional[dict] = None,
    thresholds: Optional[dict] = None,
) -> MortalityVulnerabilityAssessment:
    """Calculate the prototype Mortality/Vulnerability Risk Index.

    Parameters
    ----------
    thermal_stress_score:
        Score 0–100 from ``calculate_thermal_stress``.
    heatwave_risk_score:
        Score 0–100 from ``calculate_risk`` (heatwave_risk service).
    timestamp:
        ISO-8601 timestamp of the source observation.
    latitude, longitude:
        Geographic coordinates.
    demographics:
        Optional area-level demographic vulnerability information.
        If None, no demographic amplification is applied (factor = 1.0).
    weights:
        Optional override dict for W_THERMAL, W_HEATWAVE, W_ELDERLY,
        W_CHILDREN.  Falls back to ``Config.MORTALITY_RISK_WEIGHTS``.
    thresholds:
        Optional override dict for SCORE_LOW, SCORE_MODERATE, SCORE_HIGH.
        Falls back to ``Config.MORTALITY_RISK_THRESHOLDS``.

    Returns
    -------
    MortalityVulnerabilityAssessment
        Deterministic, fully explainable risk assessment.

    Notes
    -----
    The same inputs always produce the same output (deterministic).
    The result is a prototype vulnerability indicator, NOT a mortality
    prediction or medical diagnostic.
    """
    if weights is None:
        weights = Config.MORTALITY_RISK_WEIGHTS
    if thresholds is None:
        thresholds = Config.MORTALITY_RISK_THRESHOLDS

    w_thermal = weights["W_THERMAL"]
    w_heatwave = weights["W_HEATWAVE"]

    factors: List[str] = []

    # ------------------------------------------------------------------ #
    # 1. Base score: weighted combination of thermal + heatwave risk      #
    # ------------------------------------------------------------------ #
    thermal_contribution = thermal_stress_score * w_thermal
    heatwave_contribution = heatwave_risk_score * w_heatwave
    base_score = thermal_contribution + heatwave_contribution

    factors.append(
        f"Thermal stress contribution: {thermal_stress_score} × {w_thermal} = {thermal_contribution:.1f}"
    )
    factors.append(
        f"Heatwave risk contribution: {heatwave_risk_score} × {w_heatwave} = {heatwave_contribution:.1f}"
    )
    factors.append(f"Base score (pre-demographics): {base_score:.1f}")

    # ------------------------------------------------------------------ #
    # 2. Demographic vulnerability multiplier                              #
    # ------------------------------------------------------------------ #
    vuln_factor, vuln_descriptions = _compute_vulnerability_factor(demographics, weights)
    factors.extend(vuln_descriptions)

    # ------------------------------------------------------------------ #
    # 3. Final amplified score                                            #
    # ------------------------------------------------------------------ #
    raw_score = base_score * vuln_factor
    final_score = max(0, min(100, int(round(raw_score))))

    if vuln_factor != 1.0:
        factors.append(
            f"Vulnerability amplification: {base_score:.1f} × {vuln_factor:.3f} "
            f"= {raw_score:.1f} → clamped to {final_score}"
        )

    level = _score_to_level(final_score, thresholds)

    return MortalityVulnerabilityAssessment(
        risk_level=level,
        risk_score=final_score,
        vulnerability_factor=round(vuln_factor, 4),
        contributing_factors=factors,
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
    )
