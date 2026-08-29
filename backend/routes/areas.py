"""Area management API routes."""

from flask import Blueprint, jsonify, request

from models.database_models import Area, db

areas_bp = Blueprint("areas_bp", __name__)


def _area_data(area: Area) -> dict:
    return {
        "id": area.id,
        "name": area.name,
        "latitude": area.latitude,
        "longitude": area.longitude,
    }


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
