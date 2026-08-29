"""v0.18 forecast risk evaluation REST API route."""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from models.database_models import Area, db
from services.alert_service import alert_to_dict
from services.forecast_alerts import evaluate_forecast_risk_for_area
from routes.prediction import _default_artifact_dir, _default_artifact_version, _validate_task, _validate_target_column, _validate_artifact_version

forecast_bp = Blueprint("forecast_bp", __name__)


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


@forecast_bp.route("/api/risk/forecast", methods=["GET"])
def get_forecast_risk():
    """Evaluate and return upcoming forecast risk for an Area.

    Query parameters:
        area_id (int, required): monitored Area identifier.
        task (str, optional): ``classification`` (default) or ``regression``.
        target_column (str, optional): label column; default
            ``validated_heatwave_event``.
        artifact_version (str, optional): overrides ``ML_ARTIFACT_VERSION``.
    """
    area, error = _get_area_from_request()
    if error:
        return error

    task_value = request.args.get("task")
    target_value = request.args.get("target_column")
    version_value = request.args.get("artifact_version")

    try:
        from services.prediction import PredictionError
        task = _validate_task(task_value)
        target_column = _validate_target_column(target_value)
        artifact_version = _validate_artifact_version(version_value)
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    try:
        results = evaluate_forecast_risk_for_area(
            area=area,
            artifact_dir=_default_artifact_dir(),
            artifact_version=artifact_version,
            task=task,
            target_column=target_column,
        )
    except Exception:  # noqa: BLE001
        current_app.logger.exception("Unexpected error in /api/risk/forecast")
        return (
            jsonify({
                "status": "error",
                "message": "An unexpected internal error occurred.",
            }),
            500,
        )

    # Note: If no forecast records are present, the orchestrator returns
    # an empty dict of risks/predictions, but the user requested:
    # "If there are no forecast records for the requested area, return the
    # project’s appropriate empty/not-found response rather than silently inventing data."
    if not results.get("deterministic_risks") and not results.get("ml_predictions"):
        return (
            jsonify({
                "status": "error",
                "message": "No stored forecast found for this area.",
            }),
            404,
        )

    # Format the response to avoid exposing internal objects directly
    formatted_data = {
        "area_id": results["area_id"],
        "deterministic_risks": [
            {
                "risk_level": r.risk_level,
                "risk_score": r.risk_score,
                "timestamp": r.timestamp,
                "contributing_factors": r.contributing_factors,
            }
            for r in results["deterministic_risks"]
        ],
        "ml_predictions": [
            {
                "forecast_timestamp": p.forecast_timestamp,
                "task": p.task,
                "prediction": p.prediction,
                "probability": p.probability,
            }
            for p in results["ml_predictions"]
        ],
        "alerts": [alert_to_dict(a) for a in results["alerts"]],
    }

    return jsonify({
        "status": "success",
        "data": formatted_data,
    })
