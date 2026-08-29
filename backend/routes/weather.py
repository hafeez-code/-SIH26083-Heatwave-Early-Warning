"""Historical, persisted weather observation API routes."""

from flask import Blueprint, jsonify, request

from models.database_models import Area, WeatherObservation, db

weather_bp = Blueprint("weather_bp", __name__)


def _observation_data(observation: WeatherObservation) -> dict:
    return {
        "id": observation.id,
        "area_id": observation.area_id,
        "latitude": observation.latitude,
        "longitude": observation.longitude,
        "timestamp": observation.timestamp,
        "temperature": observation.temperature,
        "humidity": observation.humidity,
        "wind_speed": observation.wind_speed,
        "precipitation": observation.precipitation,
    }


def _requested_area():
    value = request.args.get("area_id")
    if value is None:
        return None, (jsonify({"status": "error", "message": "Missing area_id parameter."}), 400)
    try:
        area_id = int(value)
    except ValueError:
        return None, (jsonify({"status": "error", "message": "area_id must be an integer."}), 400)
    area = db.session.get(Area, area_id)
    if area is None:
        return None, (jsonify({"status": "error", "message": "Area not found."}), 404)
    return area, None


@weather_bp.route("/api/weather", methods=["GET"])
def weather_history():
    area, error = _requested_area()
    if error:
        return error

    query = WeatherObservation.query.filter_by(area_id=area.id)
    start = request.args.get("start")
    end = request.args.get("end")
    if start:
        query = query.filter(WeatherObservation.timestamp >= start)
    if end:
        query = query.filter(WeatherObservation.timestamp <= end)

    query = query.order_by(WeatherObservation.timestamp.asc(), WeatherObservation.id.asc())

    limit = request.args.get("limit")
    if limit is not None:
        try:
            limit_value = int(limit)
            if limit_value < 1:
                raise ValueError
        except ValueError:
            return jsonify({"status": "error", "message": "limit must be a positive integer."}), 400
        query = query.limit(limit_value)

    observations = query.all()
    return jsonify({
        "status": "success",
        "data": {"area_id": area.id, "observations": [_observation_data(item) for item in observations]},
    })
