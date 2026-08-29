"""Historical, persisted weather observation API routes."""

from flask import Blueprint, current_app, jsonify, request

from models.database_models import Area, ForecastObservation, WeatherObservation, db
from services.data_ingestion import (
    WeatherAPIError,
    WeatherAPINetworkError,
    WeatherAPITimeoutError,
    WeatherDataError,
)
from services.forecast_ingestion import (
    fetch_forecast,
    persist_forecasts,
    prepare_forecast_features,
)

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


def _forecast_data(forecast: ForecastObservation) -> dict:
    return {
        "id": forecast.id,
        "area_id": forecast.area_id,
        "forecast_timestamp": forecast.forecast_timestamp,
        "temperature": forecast.temperature,
        "humidity": forecast.humidity,
        "wind_speed": forecast.wind_speed,
        "precipitation": forecast.precipitation,
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


@weather_bp.route("/api/weather/forecast", methods=["GET"])
def area_forecast():
    """Fetch or retrieve hourly forecasts using authoritative Area coordinates."""
    area, error = _requested_area()
    if error:
        return error

    if request.args.get("stored", "false").lower() == "true":
        records = (
            ForecastObservation.query.filter_by(area_id=area.id)
            .order_by(ForecastObservation.forecast_timestamp.asc(), ForecastObservation.id.asc())
            .all()
        )
        if not records:
            return jsonify({"status": "error", "message": "No stored forecast found for this area."}), 404
        return jsonify({
            "status": "success",
            "data": {
                "area_id": area.id,
                "forecasts": [_forecast_data(record) for record in records],
                "features": prepare_forecast_features(records),
            },
        })

    try:
        forecasts = fetch_forecast(
            latitude=area.latitude,
            longitude=area.longitude,
            base_url=current_app.config["WEATHER_API_BASE_URL"],
            api_key=current_app.config.get("WEATHER_API_KEY", ""),
            timeout=current_app.config.get("WEATHER_API_TIMEOUT", 10),
        )
        records = persist_forecasts(forecasts, area.id, db.session)
        db.session.commit()
        records.sort(key=lambda record: (record.forecast_timestamp, record.id))
        return jsonify({
            "status": "success",
            "data": {
                "area_id": area.id,
                "forecasts": [_forecast_data(record) for record in records],
                "features": prepare_forecast_features(records),
            },
        })
    except WeatherAPITimeoutError:
        return jsonify({"status": "error", "message": "Forecast provider request timed out."}), 504
    except (WeatherAPIError, WeatherAPINetworkError, WeatherDataError) as exc:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Forecast provider error: {exc}"}), 502
    except Exception:  # noqa: BLE001
        db.session.rollback()
        return jsonify({"status": "error", "message": "An unexpected internal error occurred."}), 500
