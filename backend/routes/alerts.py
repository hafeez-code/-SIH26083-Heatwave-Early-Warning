"""Early-warning alert API routes for SIH26083 v0.17."""

from flask import Blueprint, jsonify, request

from services.alert_service import (
    alert_to_dict,
    get_default_store,
    list_alerts,
)

alerts_bp = Blueprint("alerts_bp", __name__)


@alerts_bp.route("/api/alerts", methods=["GET"])
def get_alerts():
    """Return current alerts, optionally filtered by area and active state."""
    area_id_raw = request.args.get("area_id")
    active_only_raw = request.args.get("active_only", "false").lower()

    area_id = None
    if area_id_raw is not None:
        try:
            area_id = int(area_id_raw)
        except ValueError:
            return jsonify(
                {
                    "status": "error",
                    "message": "area_id must be an integer.",
                }
            ), 400

    if active_only_raw not in {"true", "false", "1", "0"}:
        return jsonify(
            {
                "status": "error",
                "message": "active_only must be true or false.",
            }
        ), 400

    active_only = active_only_raw in {"true", "1"}

    alerts = list_alerts(
        area_id=area_id,
        active_only=active_only,
    )

    return jsonify(
        {
            "status": "success",
            "data": [alert_to_dict(alert) for alert in alerts],
            "count": len(alerts),
        }
    )


@alerts_bp.route("/api/alerts/<string:alert_id>/resolve", methods=["POST"])
def resolve_alert(alert_id: str):
    """Mark an existing alert as inactive."""
    store = get_default_store()
    alert = store.resolve(alert_id)

    if alert is None:
        return jsonify(
            {
                "status": "error",
                "message": "Alert not found.",
            }
        ), 404

    return jsonify(
        {
            "status": "success",
            "data": alert_to_dict(alert),
        }
    )


@alerts_bp.route("/api/alerts/clear", methods=["POST"])
def clear_alerts():
    """Clear the in-memory alert store.

    This endpoint is intended for local prototype/demo use only.
    """
    get_default_store().clear()

    return jsonify(
        {
            "status": "success",
            "message": "Alert store cleared.",
        }
    )
@alerts_bp.route("/api/alerts/test", methods=["POST"])
def create_test_alert():
    """Create a synthetic HIGH-risk alert for local UI/demo testing."""
    from datetime import datetime, timezone
    from services.alert_service import evaluate_alert_from_risk_assessment

    alert = evaluate_alert_from_risk_assessment(
        area_id=1,
        risk_level="HIGH",
        risk_score=70,
        timestamp=datetime.now(timezone.utc).isoformat(),
        factors=[
            "Synthetic demo alert",
            "High heatwave risk condition",
        ],
    )

    if alert is None:
        return jsonify(
            {
                "status": "error",
                "message": "Test alert could not be created.",
            }
        ), 500

    return jsonify(
        {
            "status": "success",
            "data": alert_to_dict(alert),
        }
    )
