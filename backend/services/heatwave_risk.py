"""
heatwave_risk.py – Heatwave risk calculation for SIH26083.

Sprint 5 (v0.6): Deterministic heatwave risk assessment based on
weather observations.
"""

from dataclasses import dataclass
from typing import List, Optional

from config import Config
from services.data_ingestion import NormalisedObservation


@dataclass
class RiskAssessment:
    """Structured response for a heatwave risk assessment."""
    risk_level: str
    risk_score: int
    contributing_factors: List[str]
    timestamp: str
    latitude: float
    longitude: float


def calculate_risk(
    observation: NormalisedObservation,
    thresholds: Optional[dict] = None
) -> RiskAssessment:
    """
    Calculate a deterministic heatwave risk score and level from a weather observation.
    
    If temperature is None, raises ValueError.
    """
    if observation.temperature is None:
        raise ValueError("Temperature is required to calculate heatwave risk.")

    if thresholds is None:
        thresholds = Config.HEATWAVE_RISK_THRESHOLDS

    score = 0
    factors = []

    # Temperature (Primary Driver)
    temp = observation.temperature
    if temp < thresholds["TEMP_MIN"]:
        # If temperature is below the minimum threshold, risk is 0 regardless of other factors
        return RiskAssessment(
            risk_level="LOW",
            risk_score=0,
            contributing_factors=[f"Temperature ({temp}°C) is below risk threshold."],
            timestamp=observation.timestamp,
            latitude=observation.latitude,
            longitude=observation.longitude,
        )
    elif temp >= thresholds["TEMP_EXTREME"]:
        score += 80
        factors.append(f"Extreme heat ({temp}°C)")
    elif temp >= thresholds["TEMP_HIGH"]:
        score += 60
        factors.append(f"High heat ({temp}°C)")
    elif temp >= thresholds["TEMP_MODERATE"]:
        score += 40
        factors.append(f"Moderate heat ({temp}°C)")
    else:
        score += 20
        factors.append(f"Elevated heat ({temp}°C)")

    # Humidity Adjustment
    if observation.humidity is not None:
        hum = observation.humidity
        if hum >= thresholds["HUMIDITY_EXTREME"]:
            score += 20
            factors.append(f"Extreme humidity ({hum}%)")
        elif hum >= thresholds["HUMIDITY_HIGH"]:
            score += 10
            factors.append(f"High humidity ({hum}%)")
    else:
        factors.append("Missing data: humidity")

    # Wind Speed Adjustment
    if observation.wind_speed is not None:
        wind = observation.wind_speed
        if wind < thresholds["WIND_STAGNANT"]:
            score += 10
            factors.append(f"Stagnant air ({wind} km/h)")
        elif wind > thresholds["WIND_BREEZE"]:
            score -= 10
            factors.append(f"Cooling breeze ({wind} km/h)")
    else:
        factors.append("Missing data: wind speed")

    # Precipitation Adjustment
    if observation.precipitation is not None:
        precip = observation.precipitation
        if precip > 0:
            score -= 5
            factors.append(f"Precipitation ({precip} mm) providing temporary cooling")
    else:
        factors.append("Missing data: precipitation")

    # Clamp score to [0, 100]
    score = max(0, min(100, score))

    # Determine risk level
    if score < 30:
        level = "LOW"
    elif score < 60:
        level = "MODERATE"
    elif score < 80:
        level = "HIGH"
    else:
        level = "EXTREME"

    return RiskAssessment(
        risk_level=level,
        risk_score=score,
        contributing_factors=factors,
        timestamp=observation.timestamp,
        latitude=observation.latitude,
        longitude=observation.longitude,
    )
