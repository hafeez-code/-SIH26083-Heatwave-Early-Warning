"""v0.16 ML prediction REST API routes."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, jsonify, request

from models.database_models import Area, ForecastObservation, db
from services.label_preparation import DEFAULT_LABEL_NAME
from services.ml_training import TaskType
from services.prediction import PredictionError, PredictionResult, predict

prediction_bp = Blueprint("prediction_bp", __name__)


def _prediction_data(result: PredictionResult) -> dict[str, Any]:
    return {
        "area_id": result.area_id,
        "forecast_timestamp": result.forecast_timestamp,
        "task": result.task,
        "prediction": result.prediction,
        "probability": result.probability,
        "features": dict(result.feature_values),
    }


def _get_area_from_request():
    value = request.args.get("area_id")
    try:
        area_id = int(value)
    except (TypeError, ValueError):
        return None, (
            jsonify({"status": "error", "message": "area_id must be an integer."}),
            400,
        )
    area = db.session.get(Area, area_id)
    if area is None:
        return None, (
            jsonify({"status": "error", "message": "Area not found."}),
            404,
        )
    return area, None


def _default_artifact_dir() -> str:
    return current_app.config.get(
        "ML_ARTIFACT_DIR",
        "artifacts/models",
    )


def _default_artifact_version() -> str:
    return current_app.config.get("ML_ARTIFACT_VERSION", "v0.16")


def _validate_task(value: Any) -> TaskType:
    if value is None:
        return "classification"
    if value not in ("classification", "regression"):
        raise PredictionError("task must be either 'classification' or 'regression'.")
    return value


def _validate_target_column(value: Any) -> str:
    if value is None:
        return DEFAULT_LABEL_NAME
    if not isinstance(value, str) or not value:
        raise PredictionError("target_column must be a non-empty string.")
    return value


def _validate_artifact_version(value: Any) -> str:
    if value is None:
        return _default_artifact_version()
    if not isinstance(value, str) or not value:
        raise PredictionError("artifact_version must be a non-empty string.")
    return value


@prediction_bp.route("/api/prediction/forecast", methods=["GET"])
def forecast_prediction():
    """Return ML predictions for stored ForecastObservation rows for an Area.

    Query parameters:
        area_id (int, required): monitored Area identifier.
        stored (bool, required): must equal ``true`` for v0.16.
        task (str, optional): ``classification`` (default) or ``regression``.
        target_column (str, optional): label column; default
            ``validated_heatwave_event``.
        artifact_version (str, optional): overrides ``ML_ARTIFACT_VERSION``.
    """
    if request.args.get("stored", "false").lower() != "true":
        return (
            jsonify({
                "status": "error",
                "message": "GET /api/prediction/forecast requires stored=true.",
            }),
            400,
        )

    area, error = _get_area_from_request()
    if error:
        return error

    task_value = request.args.get("task")
    target_value = request.args.get("target_column")
    version_value = request.args.get("artifact_version")
    try:
        task = _validate_task(task_value)
        target_column = _validate_target_column(target_value)
        artifact_version = _validate_artifact_version(version_value)
    except PredictionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    forecast_records = (
        ForecastObservation.query.filter_by(area_id=area.id)
        .order_by(
            ForecastObservation.forecast_timestamp.asc(),
            ForecastObservation.id.asc(),
        )
        .all()
    )
    if not forecast_records:
        return (
            jsonify({
                "status": "error",
                "message": "No stored forecast found for this area.",
            }),
            404,
        )

    records = [
        {
            "area_id": record.area_id,
            "forecast_timestamp": record.forecast_timestamp,
            "temperature": record.temperature,
            "humidity": record.humidity,
            "wind_speed": record.wind_speed,
            "precipitation": record.precipitation,
        }
        for record in forecast_records
    ]

    try:
        predictions = predict(
            records,
            artifact_dir=_default_artifact_dir(),
            task=task,
            target_column=target_column,
            artifact_version=artifact_version,
        )
    except PredictionError as exc:
        message = str(exc)
        if "No artifact found" in message:
            return jsonify({"status": "error", "message": message}), 404
        return jsonify({"status": "error", "message": message}), 422
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Unexpected error in /api/prediction/forecast")
        return (
            jsonify({
                "status": "error",
                "message": "An unexpected internal error occurred.",
            }),
            500,
        )

    return jsonify({
        "status": "success",
        "data": {
            "area_id": area.id,
            "task": task,
            "target_column": target_column,
            "artifact_version": artifact_version,
            "predictions": [_prediction_data(item) for item in predictions],
            "n_skipped": len(records) - len(predictions),
        },
    })


def _validate_raw_record(record: Any, index: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise PredictionError(f"Record {index} must be a JSON object.")
    try:
        area_id = int(record["area_id"])
    except (KeyError, TypeError, ValueError):
        raise PredictionError(f"Record {index} is missing a valid integer 'area_id'.")
    forecast_timestamp = record.get("forecast_timestamp")
    if not isinstance(forecast_timestamp, str) or not forecast_timestamp:
        raise PredictionError(
            f"Record {index} is missing a non-empty string 'forecast_timestamp'."
        )
    validated: dict[str, Any] = {
        "area_id": area_id,
        "forecast_timestamp": forecast_timestamp,
    }
    for weather_field in ("temperature", "humidity", "wind_speed", "precipitation"):
        raw = record.get(weather_field)
        if raw is None:
            validated[weather_field] = None
            continue
        if isinstance(raw, bool):
            raise PredictionError(
                f"Record {index} field {weather_field!r} must be numeric when provided."
            )
        try:
            validated[weather_field] = float(raw)
        except (TypeError, ValueError):
            raise PredictionError(
                f"Record {index} field {weather_field!r} must be numeric when provided."
            )
    return validated


@prediction_bp.route("/api/prediction", methods=["POST"])
def raw_prediction():
    """Score caller-supplied weather records against a saved artifact.

    Body:
        records (array, required): list of weather record objects each with
            ``area_id``, ``forecast_timestamp``, and optional numeric
            ``temperature``/``humidity``/``wind_speed``/``precipitation``.
        artifact_version (str, optional): overrides ``ML_ARTIFACT_VERSION``.
        task (str, optional): ``classification`` (default) or ``regression``.
        target_column (str, optional): default ``validated_heatwave_event``.
    """
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return (
            jsonify({
                "status": "error",
                "message": "Request body must be a JSON object.",
            }),
            400,
        )
    raw_records = payload.get("records")
    if not isinstance(raw_records, list):
        return (
            jsonify({
                "status": "error",
                "message": "'records' must be a non-empty JSON array.",
            }),
            400,
        )
    if not raw_records:
        return (
            jsonify({
                "status": "error",
                "message": "'records' must be a non-empty JSON array.",
            }),
            400,
        )
    try:
        records = [
            _validate_raw_record(record, index)
            for index, record in enumerate(raw_records)
        ]
    except PredictionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    try:
        task = _validate_task(payload.get("task"))
        target_column = _validate_target_column(payload.get("target_column"))
        artifact_version = _validate_artifact_version(payload.get("artifact_version"))
    except PredictionError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    try:
        predictions = predict(
            records,
            artifact_dir=_default_artifact_dir(),
            task=task,
            target_column=target_column,
            artifact_version=artifact_version,
        )
    except PredictionError as exc:
        message = str(exc)
        if "No artifact found" in message:
            return jsonify({"status": "error", "message": message}), 404
        return jsonify({"status": "error", "message": message}), 422
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Unexpected error in /api/prediction POST")
        return (
            jsonify({
                "status": "error",
                "message": "An unexpected internal error occurred.",
            }),
            500,
        )

    return jsonify({
        "status": "success",
        "data": {
            "task": task,
            "target_column": target_column,
            "artifact_version": artifact_version,
            "predictions": [_prediction_data(item) for item in predictions],
            "n_skipped": len(records) - len(predictions),
        },
    })
