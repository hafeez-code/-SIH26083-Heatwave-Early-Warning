"""
risk.py – Risk assessment API routes for SIH26083.

Sprint 7 (v0.7): REST API endpoint for heatwave risk calculation.
"""
import json

from flask import Blueprint, request, jsonify, current_app
from models.database_models import Area, HeatwaveRiskAssessment, WeatherObservation, db
from services.data_ingestion import (
    fetch_weather, 
    WeatherAPITimeoutError, 
    WeatherDataError, 
    WeatherAPIError, 
    WeatherAPINetworkError
)
from services.heatwave_risk import calculate_risk

risk_bp = Blueprint("risk_bp", __name__)


def _risk_data(record: HeatwaveRiskAssessment) -> dict:
    observation = record.weather_observation
    return {
        "location": {
            "latitude": observation.latitude,
            "longitude": observation.longitude,
        },
        "weather": {
            "timestamp": observation.timestamp,
            "temperature": observation.temperature,
            "humidity": observation.humidity,
            "wind_speed": observation.wind_speed,
            "precipitation": observation.precipitation,
        },
        "risk": {
            "score": record.risk_score,
            "level": record.risk_level,
            "contributing_factors": json.loads(record.contributing_factors),
        },
    }


def _stored_risk_response(query, missing_message: str):
    """Return the most recent stored assessment for an already-filtered query."""
    record = query.order_by(
        WeatherObservation.timestamp.desc(), WeatherObservation.id.desc()
    ).first()
    if record is None:
        return jsonify({
            "status": "error",
            "message": missing_message,
        }), 404
    return jsonify({"status": "success", "data": _risk_data(record)})


def _get_area_from_request():
    value = request.args.get("area_id")
    try:
        area_id = int(value)
    except (TypeError, ValueError):
        return None, (jsonify({"status": "error", "message": "area_id must be an integer."}), 400)
    area = db.session.get(Area, area_id)
    if area is None:
        return None, (jsonify({"status": "error", "message": "Area not found."}), 404)
    return area, None

@risk_bp.route("/api/risk", methods=["GET"])
def get_risk():
    if request.args.get("area_id") is not None:
        if request.args.get("stored", "false").lower() != "true":
            return jsonify({"status": "error", "message": "area_id requires stored=true."}), 400
        area, error = _get_area_from_request()
        if error:
            return error
        return _stored_risk_response(
            HeatwaveRiskAssessment.query.join(WeatherObservation).filter(
                WeatherObservation.area_id == area.id
            ),
            "No stored risk assessment found for this area.",
        )

    lat_str = request.args.get("latitude")
    lon_str = request.args.get("longitude")

    if lat_str is None or lon_str is None:
        return jsonify({"status": "error", "message": "Missing latitude or longitude parameter."}), 400

    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except ValueError:
        return jsonify({"status": "error", "message": "Latitude and longitude must be numeric."}), 400

    if not (-90 <= lat <= 90):
        return jsonify({"status": "error", "message": "Latitude must be between -90 and 90."}), 400
    if not (-180 <= lon <= 180):
        return jsonify({"status": "error", "message": "Longitude must be between -180 and 180."}), 400

    if request.args.get("stored", "false").lower() == "true":
        return _stored_risk_response(
            HeatwaveRiskAssessment.query.join(WeatherObservation).filter(
                WeatherObservation.latitude == lat,
                WeatherObservation.longitude == lon,
            ),
            "No stored risk assessment found for this location.",
        )

    try:
        # Obtain weather data using existing config
        base_url = current_app.config.get("WEATHER_API_BASE_URL")
        api_key = current_app.config.get("WEATHER_API_KEY", "")
        timeout = current_app.config.get("WEATHER_API_TIMEOUT", 10)

        observation = fetch_weather(
            latitude=lat,
            longitude=lon,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout
        )

        # Calculate risk
        risk_assessment = calculate_risk(observation)

        return jsonify({
            "status": "success",
            "data": {
                "location": {
                    "latitude": lat,
                    "longitude": lon
                },
                "weather": {
                    "timestamp": observation.timestamp,
                    "temperature": observation.temperature,
                    "humidity": observation.humidity,
                    "wind_speed": observation.wind_speed,
                    "precipitation": observation.precipitation
                },
                "risk": {
                    "score": risk_assessment.risk_score,
                    "level": risk_assessment.risk_level,
                    "contributing_factors": risk_assessment.contributing_factors
                }
            }
        })

    except WeatherAPITimeoutError:
        return jsonify({"status": "error", "message": "Weather API request timed out."}), 504
    except (WeatherAPIError, WeatherAPINetworkError, WeatherDataError) as e:
        return jsonify({"status": "error", "message": f"Weather API error: {str(e)}"}), 502
    except ValueError as e:
        # E.g. Missing temperature, raised by calculate_risk
        return jsonify({"status": "error", "message": f"Data processing error: {str(e)}"}), 422
    except Exception as e:
        current_app.logger.exception("Unexpected error in /api/risk")
        return jsonify({"status": "error", "message": "An unexpected internal error occurred."}), 500


@risk_bp.route("/api/risk/history", methods=["GET"])
def risk_history():
    """Return persisted risk records for an Area in provider timestamp order."""
    area, error = _get_area_from_request()
    if error:
        return error
    records = (
        HeatwaveRiskAssessment.query.join(WeatherObservation)
        .filter(WeatherObservation.area_id == area.id)
        .order_by(WeatherObservation.timestamp.asc(), WeatherObservation.id.asc())
        .all()
    )
    return jsonify({
        "status": "success",
        "data": {
            "area_id": area.id,
            "risks": [
                {"id": record.id, "weather_observation_id": record.weather_observation_id, **_risk_data(record)}
                for record in records
            ],
        },
    })
