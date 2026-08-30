"""
thermal_stress.py – Human Thermal Stress Index for SIH26083 v0.19.

PROTOTYPE DISCLAIMER
--------------------
This module implements a deterministic environmental heat-stress indicator
for the SIH26083 academic prototype.  It is NOT a clinically validated
medical diagnostic tool.  Results should not be used as a substitute for
professional medical advice or epidemiological analysis.

Methodology
-----------
Primary: Rothfusz (1990) Heat Index regression (NWS standard).
Reference: Steadman, R.G. (1979) "The Assessment of Sultriness".
           Rothfusz, L.P. (1990) "The Heat Index 'Equation'", NWS SR 90-23.

The Rothfusz equation requires temperature ≥ 27°C and humidity for a
meaningful heat index.  Below 27°C the thermal stress is LOW by definition
of the NWS methodology.

Additional environmental adjustments (applied after the base index):
  • Solar radiation bonus: high direct radiation (> threshold W/m²) adds a
    small score increment reflecting additional radiant heat load.
  • Wind cooling: sustained wind above threshold km/h provides some relief.

Score mapping (0–100 prototype index, not a medical severity scale):
  LOW       [0, SCORE_LOW)
  MODERATE  [SCORE_LOW, SCORE_MODERATE)
  HIGH      [SCORE_MODERATE, SCORE_HIGH)
  VERY HIGH [SCORE_HIGH, SCORE_VERY_HIGH)
  EXTREME   [SCORE_VERY_HIGH, 100]
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from config import Config
from services.data_ingestion import NormalisedObservation

# --------------------------------------------------------------------------- #
# Prototype disclaimer text                                                    #
# --------------------------------------------------------------------------- #

_DISCLAIMER = (
    "Prototype environmental heat-stress indicator (SIH26083 v0.19). "
    "Based on Rothfusz (1990) NWS Heat Index methodology. "
    "Not a clinically validated medical diagnosis."
)


# --------------------------------------------------------------------------- #
# Public dataclass                                                             #
# --------------------------------------------------------------------------- #

@dataclass
class ThermalStressAssessment:
    """Structured thermal stress assessment for one weather observation.

    Attributes
    ----------
    thermal_stress_level:
        Categorical risk level: LOW, MODERATE, HIGH, VERY HIGH, or EXTREME.
    thermal_stress_score:
        Prototype index score 0–100.  Higher values indicate greater
        environmental thermal stress.  Not a validated medical scale.
    heat_index_celsius:
        Computed apparent temperature (°C) via Rothfusz equation, or None
        when insufficient inputs are available (missing humidity or temp < 27°C).
    contributing_factors:
        Human-readable list of factors that drove the score.
    timestamp:
        ISO-8601 timestamp of the source observation.
    latitude, longitude:
        Geographic coordinates of the observation.
    methodology_note:
        Prototype disclaimer text.
    """

    thermal_stress_level: str
    thermal_stress_score: int
    heat_index_celsius: Optional[float]
    contributing_factors: List[str]
    timestamp: str
    latitude: float
    longitude: float
    methodology_note: str = field(default=_DISCLAIMER)


# --------------------------------------------------------------------------- #
# Rothfusz Heat Index                                                          #
# --------------------------------------------------------------------------- #

def _celsius_to_fahrenheit(t_c: float) -> float:
    return t_c * 9.0 / 5.0 + 32.0


def _fahrenheit_to_celsius(t_f: float) -> float:
    return (t_f - 32.0) * 5.0 / 9.0


def _rothfusz_heat_index_fahrenheit(t_f: float, rh: float) -> float:
    """Rothfusz (1990) multi-variable regression for apparent temperature.

    Parameters
    ----------
    t_f : float
        Dry-bulb temperature in °F.
    rh : float
        Relative humidity in percent (0–100).

    Returns
    -------
    float
        Apparent temperature (Heat Index) in °F.

    Notes
    -----
    Valid for T ≥ 80°F (≈ 27°C) and RH ≥ 40%.  Outside this range the
    caller falls back to the simple approximation or returns the dry-bulb
    temperature directly.
    """
    t2 = t_f * t_f
    h2 = rh * rh
    return (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh
        - 0.22475541 * t_f * rh
        - 0.00683783 * t2
        - 0.05481717 * h2
        + 0.00122874 * t2 * rh
        + 0.00085282 * t_f * h2
        - 0.00000199 * t2 * h2
    )


def _compute_heat_index_celsius(
    temperature_c: float,
    humidity: float,
) -> Optional[float]:
    """Return the Rothfusz Heat Index in °C, or None if not applicable.

    The Rothfusz equation is applied when T ≥ 27°C and RH ≥ 40%.
    For 27°C ≤ T < 27°C with low humidity, the dry-bulb temperature is
    returned as the best available proxy.
    For T < 27°C, returns None (below the methodology's applicability range).
    """
    if temperature_c < 27.0:
        return None  # Below meaningful heat-stress range for this methodology

    t_f = _celsius_to_fahrenheit(temperature_c)

    if humidity < 40.0:
        # Below RH applicability range: NWS uses a simpler Steadman approximation.
        # We return the dry-bulb as a conservative estimate.
        return temperature_c

    hi_f = _rothfusz_heat_index_fahrenheit(t_f, humidity)

    # NWS adjustment for low humidity (<13%) and T in 80–112°F range
    if humidity < 13.0 and 80.0 <= t_f <= 112.0:
        adjustment = ((13.0 - humidity) / 4.0) * math.sqrt((17.0 - abs(t_f - 95.0)) / 17.0)
        hi_f -= adjustment

    # NWS adjustment for high humidity (>85%) and T in 80–87°F range
    if humidity > 85.0 and 80.0 <= t_f <= 87.0:
        adjustment = ((humidity - 85.0) / 10.0) * ((87.0 - t_f) / 5.0)
        hi_f += adjustment

    return _fahrenheit_to_celsius(hi_f)


# --------------------------------------------------------------------------- #
# Score computation                                                            #
# --------------------------------------------------------------------------- #

def _heat_index_to_base_score(
    heat_index_c: Optional[float],
    temperature_c: float,
    thresholds: dict,
) -> tuple[int, str]:
    """Map heat index (or temperature when HI unavailable) to a base score.

    Returns
    -------
    (score, factor_description)
    """
    # Use heat index when available; fall back to dry-bulb temperature.
    effective_temp = heat_index_c if heat_index_c is not None else temperature_c
    hi_label = "heat index" if heat_index_c is not None else "temperature"

    hi_low = thresholds["HI_LOW"]
    hi_mod = thresholds["HI_MODERATE"]
    hi_high = thresholds["HI_HIGH"]
    hi_vh = thresholds["HI_VERY_HIGH"]

    score_low = thresholds["SCORE_LOW"]
    score_mod = thresholds["SCORE_MODERATE"]
    score_high = thresholds["SCORE_HIGH"]
    score_vh = thresholds["SCORE_VERY_HIGH"]
    score_ext = thresholds["SCORE_EXTREME"]

    if effective_temp < hi_low:
        return 0, f"Low thermal load ({hi_label} {effective_temp:.1f}°C)"
    elif effective_temp < hi_mod:
        return score_low, f"Moderate thermal load ({hi_label} {effective_temp:.1f}°C)"
    elif effective_temp < hi_high:
        return score_mod, f"High thermal load ({hi_label} {effective_temp:.1f}°C)"
    elif effective_temp < hi_vh:
        return score_high, f"Very high thermal load ({hi_label} {effective_temp:.1f}°C)"
    else:
        return score_vh, f"Extreme thermal load ({hi_label} {effective_temp:.1f}°C) – danger zone"


def _score_to_level(score: int, thresholds: dict) -> str:
    """Map a 0–100 score to a thermal stress level string."""
    s_low = thresholds["SCORE_LOW"]
    s_mod = thresholds["SCORE_MODERATE"]
    s_high = thresholds["SCORE_HIGH"]
    s_vh = thresholds["SCORE_VERY_HIGH"]

    if score < s_low:
        return "LOW"
    elif score < s_mod:
        return "MODERATE"
    elif score < s_high:
        return "HIGH"
    elif score < s_vh:
        return "VERY HIGH"
    else:
        return "EXTREME"


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def calculate_thermal_stress(
    observation: NormalisedObservation,
    thresholds: Optional[dict] = None,
) -> ThermalStressAssessment:
    """Calculate the Human Thermal Stress Index for one weather observation.

    Parameters
    ----------
    observation:
        A NormalisedObservation.  ``temperature`` is required.
        ``humidity``, ``wind_speed``, and ``solar_radiation`` are optional
        and are used when available.  Missing values are NEVER fabricated –
        their absence is recorded in ``contributing_factors``.
    thresholds:
        Configuration dict.  Falls back to ``Config.THERMAL_STRESS_THRESHOLDS``
        when not provided.

    Returns
    -------
    ThermalStressAssessment
        Deterministic, fully explainable assessment.  The same inputs always
        produce the same output.

    Raises
    ------
    ValueError
        When ``observation.temperature`` is None (required for any calculation).
    """
    if observation.temperature is None:
        raise ValueError(
            "Temperature is required to calculate Human Thermal Stress Index."
        )

    if thresholds is None:
        thresholds = Config.THERMAL_STRESS_THRESHOLDS

    factors: List[str] = []
    temperature = observation.temperature
    humidity = observation.humidity
    wind_speed = observation.wind_speed
    solar_radiation = getattr(observation, "solar_radiation", None)

    # ------------------------------------------------------------------ #
    # 1. Compute Heat Index                                               #
    # ------------------------------------------------------------------ #
    if humidity is not None:
        heat_index_c = _compute_heat_index_celsius(temperature, humidity)
        if heat_index_c is not None:
            factors.append(
                f"Rothfusz Heat Index {heat_index_c:.1f}°C "
                f"(T={temperature:.1f}°C, RH={humidity:.0f}%)"
            )
        else:
            factors.append(
                f"Temperature {temperature:.1f}°C (below heat-index applicability range)"
            )
    else:
        heat_index_c = None
        factors.append(f"Temperature {temperature:.1f}°C (humidity unavailable; heat index not computed)")

    # ------------------------------------------------------------------ #
    # 2. Base score from heat index or temperature                        #
    # ------------------------------------------------------------------ #
    base_score, base_factor = _heat_index_to_base_score(heat_index_c, temperature, thresholds)
    if base_factor not in factors:
        factors.append(base_factor)

    score = base_score

    # ------------------------------------------------------------------ #
    # 3. Wind cooling adjustment                                          #
    # ------------------------------------------------------------------ #
    wind_thresh = thresholds["WIND_COOLING_THRESHOLD"]
    wind_bonus = thresholds["WIND_COOLING_BONUS"]
    if wind_speed is not None:
        if wind_speed > wind_thresh:
            score -= wind_bonus
            factors.append(
                f"Wind cooling at {wind_speed:.1f} km/h (>{wind_thresh} km/h threshold, -{wind_bonus} pts)"
            )
    else:
        factors.append("Missing data: wind speed (no wind-cooling adjustment applied)")

    # ------------------------------------------------------------------ #
    # 4. Solar radiation adjustment                                       #
    # ------------------------------------------------------------------ #
    solar_thresh = thresholds["SOLAR_HIGH_THRESHOLD"]
    solar_bonus = thresholds["SOLAR_SCORE_BONUS"]
    if solar_radiation is not None:
        if solar_radiation > solar_thresh:
            score += solar_bonus
            factors.append(
                f"High solar radiation {solar_radiation:.0f} W/m² "
                f"(>{solar_thresh:.0f} W/m² threshold, +{solar_bonus} pts)"
            )
    # Not flagging missing solar radiation – it is always optional.

    # ------------------------------------------------------------------ #
    # 5. Clamp and map                                                    #
    # ------------------------------------------------------------------ #
    score = max(0, min(100, score))
    level = _score_to_level(score, thresholds)

    return ThermalStressAssessment(
        thermal_stress_level=level,
        thermal_stress_score=score,
        heat_index_celsius=round(heat_index_c, 2) if heat_index_c is not None else None,
        contributing_factors=factors,
        timestamp=observation.timestamp,
        latitude=observation.latitude,
        longitude=observation.longitude,
    )
