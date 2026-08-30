"""Area management and early-warning API routes for SIH26083 v0.19.

New endpoints (v0.19):
  GET  /api/areas/<area_id>/early-warning    – unified early-warning picture
  GET  /api/areas/<area_id>/demographics     – get area demographics
  POST /api/areas/<area_id>/demographics     – upsert area demographics
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from flask import Blueprint, jsonify, request

from models.database_models import Area, AreaDemographics, WeatherObservation, db
from services.alert_service import list_alerts

logger = logging.getLogger(__name__)

areas_bp = Blueprint("areas_bp", __name__)


# --------------------------------------------------------------------------- #
# Serialisers                                                                  #
# --------------------------------------------------------------------------- #

def _area_data(area: Area) -> dict:
    """GIS-ready area representation."""
    return {
        "id": area.id,
        "name": area.name,
        "latitude": area.latitude,
        "longitude": area.longitude,
    }


def _demographics_data(demo: AreaDemographics) -> dict:
    return {
        "area_id": demo.area_id,
        "population_total": demo.population_total,
        "pct_elderly": demo.pct_elderly,
        "pct_children": demo.pct_children,
        "vulnerability_notes": demo.vulnerability_notes,
    }


# --------------------------------------------------------------------------- #
# Area CRUD                                                                    #
# --------------------------------------------------------------------------- #

@areas_bp.route("/api/areas", methods=["POST"])
def create_area():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"status": "error", "message": "Request body must be a JSON object."}), 400

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"status": "error", "message": "Name must be present and non-empty."}), 400

    try:
        latitude = float(payload["latitude"])
        longitude = float(payload["longitude"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"status": "error", "message": "Latitude and longitude must be numeric."}), 400

    if not -90 <= latitude <= 90:
        return jsonify({"status": "error", "message": "Latitude must be between -90 and 90."}), 400
    if not -180 <= longitude <= 180:
        return jsonify({"status": "error", "message": "Longitude must be between -180 and 180."}), 400

    area = Area(name=name.strip(), latitude=latitude, longitude=longitude)
    db.session.add(area)
    db.session.commit()
    return jsonify({"status": "success", "data": _area_data(area)}), 201


@areas_bp.route("/api/areas", methods=["GET"])
def list_areas():
    areas = Area.query.order_by(Area.id).all()
    return jsonify({"status": "success", "data": [_area_data(area) for area in areas]})


@areas_bp.route("/api/areas/<int:area_id>", methods=["GET"])
def get_area(area_id: int):
    area = db.session.get(Area, area_id)
    if area is None:
        return jsonify({"status": "error", "message": "Area not found."}), 404
    return jsonify({"status": "success", "data": _area_data(area)})


# --------------------------------------------------------------------------- #
# Demographics                                                                 #
# --------------------------------------------------------------------------- #

@areas_bp.route("/api/areas/<int:area_id>/demographics", methods=["GET"])
def get_demographics(area_id: int):
    """Return the aggregate demographic profile for an area."""
    area = db.session.get(Area, area_id)
    if area is None:
        return jsonify({"status": "error", "message": "Area not found."}), 404

    demo = AreaDemographics.query.filter_by(area_id=area_id).one_or_none()
    if demo is None:
        return jsonify({
            "status": "success",
            "data": None,
            "message": "No demographic data stored for this area.",
        })
    return jsonify({"status": "success", "data": _demographics_data(demo)})


@areas_bp.route("/api/areas/<int:area_id>/demographics", methods=["POST"])
def upsert_demographics(area_id: int):
    """Create or update aggregate demographic data for an area.

    Body (all fields optional except the area must exist):
        population_total (int, optional): total population count.
        pct_elderly (float, optional): % of population aged ≥65 (0–100).
        pct_children (float, optional): % of population aged <18 (0–100).
        vulnerability_notes (str, optional): free-text context.

    No personally identifiable information is accepted or stored.
    """
    area = db.session.get(Area, area_id)
    if area is None:
        return jsonify({"status": "error", "message": "Area not found."}), 404

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"status": "error", "message": "Request body must be a JSON object."}), 400

    # Validate percentage fields
    for pct_field in ("pct_elderly", "pct_children"):
        raw = payload.get(pct_field)
        if raw is not None:
            try:
                val = float(raw)
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": f"{pct_field} must be numeric."}), 400
            if not 0.0 <= val <= 100.0:
                return jsonify({"status": "error", "message": f"{pct_field} must be between 0 and 100."}), 400

    # Validate population count
    pop_raw = payload.get("population_total")
    if pop_raw is not None:
        try:
            pop_val = int(pop_raw)
            if pop_val < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "population_total must be a non-negative integer."}), 400

    demo = AreaDemographics.query.filter_by(area_id=area_id).one_or_none()
    if demo is None:
        demo = AreaDemographics(area_id=area_id)
        db.session.add(demo)

    if "population_total" in payload:
        demo.population_total = None if payload["population_total"] is None else int(payload["population_total"])
    if "pct_elderly" in payload:
        demo.pct_elderly = None if payload["pct_elderly"] is None else float(payload["pct_elderly"])
    if "pct_children" in payload:
        demo.pct_children = None if payload["pct_children"] is None else float(payload["pct_children"])
    if "vulnerability_notes" in payload:
        demo.vulnerability_notes = payload.get("vulnerability_notes")

    db.session.commit()
    return jsonify({"status": "success", "data": _demographics_data(demo)}), 201


# --------------------------------------------------------------------------- #
# Unified Early-Warning Endpoint                                               #
# --------------------------------------------------------------------------- #

def _thermal_stress_to_dict(ts) -> Optional[dict]:
    if ts is None:
        return None
    return {
        "level": ts.thermal_stress_level,
        "score": ts.thermal_stress_score,
        "heat_index_celsius": ts.heat_index_celsius,
        "contributing_factors": ts.contributing_factors,
        "methodology_note": ts.methodology_note,
    }


def _mortality_to_dict(mv) -> Optional[dict]:
    if mv is None:
        return None
    return {
        "level": mv.risk_level,
        "score": mv.risk_score,
        "vulnerability_factor": mv.vulnerability_factor,
        "contributing_factors": mv.contributing_factors,
        "methodology_note": mv.methodology_note,
    }


@areas_bp.route("/api/areas/<int:area_id>/early-warning", methods=["GET"])
def get_early_warning(area_id: int):
    """Return the unified current early-warning picture for an area.

    This endpoint assembles:
      • Latest stored weather observation
      • Heatwave risk (deterministic)
      • Human Thermal Stress Index
      • Demographic vulnerability (if data exists)
      • Mortality/Vulnerability Risk Index
      • Active alerts

    GIS-ready: the response includes latitude/longitude, area name, and
    structured risk scores suitable for map rendering.

    Returns
    -------
    200 with full early-warning data.
    400 if area_id is not an integer (caught by Flask route conversion).
    404 if area not found.
    404 if no weather data available for the area.
    500 on unexpected internal failure.
    """
    area = db.session.get(Area, area_id)
    if area is None:
        return jsonify({"status": "error", "message": "Area not found."}), 404

    # -- Latest weather observation -----------------------------------------
    latest_obs = (
        WeatherObservation.query
        .filter_by(area_id=area_id)
        .order_by(WeatherObservation.timestamp.desc(), WeatherObservation.id.desc())
        .first()
    )
    if latest_obs is None:
        return jsonify({
            "status": "error",
            "message": "No weather data available for this area. Ingest weather data first.",
        }), 404

    # -- Build NormalisedObservation for risk pipeline ----------------------
    from services.data_ingestion import NormalisedObservation
    obs = NormalisedObservation(
        latitude=float(latest_obs.latitude),
        longitude=float(latest_obs.longitude),
        timestamp=latest_obs.timestamp,
        temperature=latest_obs.temperature,
        humidity=latest_obs.humidity,
        wind_speed=latest_obs.wind_speed,
        precipitation=latest_obs.precipitation,
        solar_radiation=getattr(latest_obs, "solar_radiation", None),
    )

    # -- Demographics -------------------------------------------------------
    demo_record = AreaDemographics.query.filter_by(area_id=area_id).one_or_none()
    from services.mortality_risk import DemographicVulnerability
    demographics: Optional[DemographicVulnerability] = None
    if demo_record is not None:
        try:
            demographics = DemographicVulnerability(
                pct_elderly=demo_record.pct_elderly,
                pct_children=demo_record.pct_children,
                vulnerability_notes=demo_record.vulnerability_notes,
            )
        except ValueError as exc:
            logger.warning("Invalid demographic data for area %s: %s", area_id, exc)

    # -- Run full pipeline --------------------------------------------------
    from services.risk_pipeline import run_full_risk_pipeline
    try:
        result = run_full_risk_pipeline(obs, demographics=demographics)
    except ValueError as exc:
        return jsonify({
            "status": "error",
            "message": f"Risk calculation failed: {exc}",
        }), 422
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in early-warning pipeline for area %s", area_id)
        return jsonify({
            "status": "error",
            "message": "An unexpected internal error occurred.",
        }), 500

    # -- Active alerts for this area ----------------------------------------
    from services.alert_service import alert_to_dict
    active_alerts = list_alerts(area_id=area_id, active_only=True)

    # -- Overall early-warning status ----------------------------------------
    # Derived from the highest risk level across all layers.
    def _level_to_int(level: str) -> int:
        return {"LOW": 0, "MODERATE": 1, "HIGH": 2, "VERY HIGH": 3, "EXTREME": 4}.get(
            level.upper(), 0
        )

    hw_level = result.heatwave_risk.risk_level
    ts_level = result.thermal_stress.thermal_stress_level if result.thermal_stress else "LOW"
    mv_level = result.mortality_vulnerability.risk_level if result.mortality_vulnerability else "LOW"

    highest = max([hw_level, ts_level, mv_level], key=_level_to_int)
    has_active_alerts = len(active_alerts) > 0

    overall_status: str
    if _level_to_int(highest) >= _level_to_int("EXTREME"):
        overall_status = "CRITICAL"
    elif _level_to_int(highest) >= _level_to_int("HIGH"):
        overall_status = "WARNING"
    elif _level_to_int(highest) >= _level_to_int("MODERATE"):
        overall_status = "WATCH"
    else:
        overall_status = "NORMAL"

    # -- Response -----------------------------------------------------------
    response_data: dict[str, Any] = {
        "area_id": area.id,
        "area": {
            "name": area.name,
            "latitude": area.latitude,
            "longitude": area.longitude,
        },
        "weather": {
            "timestamp": obs.timestamp,
            "temperature": obs.temperature,
            "humidity": obs.humidity,
            "wind_speed": obs.wind_speed,
            "precipitation": obs.precipitation,
            "solar_radiation": obs.solar_radiation,
        },
        "heatwave_risk": {
            "level": result.heatwave_risk.risk_level,
            "score": result.heatwave_risk.risk_score,
            "contributing_factors": result.heatwave_risk.contributing_factors,
        },
        "thermal_stress": _thermal_stress_to_dict(result.thermal_stress),
        "thermal_stress_error": result.thermal_stress_error,
        "mortality_vulnerability": _mortality_to_dict(result.mortality_vulnerability),
        "mortality_vulnerability_error": result.mortality_error,
        "demographics": (
            _demographics_data(demo_record) if demo_record is not None else None
        ),
        "alerts": [alert_to_dict(a) for a in active_alerts],
        "overall_status": overall_status,
        "highest_risk_level": highest,
        "has_active_alerts": has_active_alerts,
    }

    return jsonify({"status": "success", "data": response_data})
