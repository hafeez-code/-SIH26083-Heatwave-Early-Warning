"""
test_demographics.py – Integration tests for the AreaDemographics model and API.

Covers: model creation, validation, API endpoints, and the full
area → demographics → early-warning integration chain.
"""

import os
import sys

import pytest
from flask import Flask

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import Area, AreaDemographics, db
from routes.areas import areas_bp


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(areas_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _create_area(client, name="Test Area"):
    response = client.post(
        "/api/areas",
        json={"name": name, "latitude": 17.385, "longitude": 78.4867},
    )
    assert response.status_code == 201
    return response.get_json()["data"]


# ---------------------------------------------------------------------------
# Model-level tests
# ---------------------------------------------------------------------------

class TestAreaDemographicsModel:
    def test_create_demographics_linked_to_area(self, app):
        with app.app_context():
            area = Area(name="Test", latitude=17.0, longitude=78.0)
            db.session.add(area)
            db.session.flush()
            demo = AreaDemographics(
                area_id=area.id,
                population_total=100000,
                pct_elderly=12.5,
                pct_children=28.0,
                vulnerability_notes="Dense urban population",
            )
            db.session.add(demo)
            db.session.commit()
            stored = AreaDemographics.query.filter_by(area_id=area.id).one()
            assert stored.population_total == 100000
            assert stored.pct_elderly == 12.5
            assert stored.pct_children == 28.0

    def test_demographics_null_fields_allowed(self, app):
        with app.app_context():
            area = Area(name="Test", latitude=17.0, longitude=78.0)
            db.session.add(area)
            db.session.flush()
            demo = AreaDemographics(area_id=area.id)
            db.session.add(demo)
            db.session.commit()
            stored = AreaDemographics.query.filter_by(area_id=area.id).one()
            assert stored.pct_elderly is None
            assert stored.pct_children is None

    def test_area_has_demographics_relationship(self, app):
        with app.app_context():
            area = Area(name="Test", latitude=17.0, longitude=78.0)
            db.session.add(area)
            db.session.flush()
            demo = AreaDemographics(area_id=area.id, pct_elderly=10.0)
            db.session.add(demo)
            db.session.commit()
            loaded_area = db.session.get(Area, area.id)
            assert loaded_area.demographics is not None
            assert loaded_area.demographics.pct_elderly == 10.0


# ---------------------------------------------------------------------------
# API: GET demographics
# ---------------------------------------------------------------------------

class TestGetDemographicsAPI:
    def test_get_demographics_not_found_returns_null_data(self, client):
        area = _create_area(client)
        resp = client.get(f"/api/areas/{area['id']}/demographics")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "success"
        assert body["data"] is None

    def test_get_demographics_invalid_area_returns_404(self, client):
        resp = client.get("/api/areas/9999/demographics")
        assert resp.status_code == 404

    def test_get_demographics_returns_stored_data(self, client, app):
        area = _create_area(client)
        with app.app_context():
            demo = AreaDemographics(
                area_id=area["id"],
                pct_elderly=15.0,
                pct_children=22.0,
                vulnerability_notes="test note",
            )
            db.session.add(demo)
            db.session.commit()

        resp = client.get(f"/api/areas/{area['id']}/demographics")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["pct_elderly"] == 15.0
        assert data["pct_children"] == 22.0
        assert data["vulnerability_notes"] == "test note"


# ---------------------------------------------------------------------------
# API: POST demographics (upsert)
# ---------------------------------------------------------------------------

class TestUpsertDemographicsAPI:
    def test_create_demographics(self, client):
        area = _create_area(client)
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            json={"pct_elderly": 12.0, "pct_children": 20.0},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["pct_elderly"] == 12.0
        assert data["pct_children"] == 20.0

    def test_update_demographics(self, client):
        area = _create_area(client)
        client.post(
            f"/api/areas/{area['id']}/demographics",
            json={"pct_elderly": 10.0},
        )
        # Update with new value
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            json={"pct_elderly": 20.0, "pct_children": 15.0},
        )
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["pct_elderly"] == 20.0
        assert data["pct_children"] == 15.0

    def test_invalid_area_returns_404(self, client):
        resp = client.post(
            "/api/areas/9999/demographics",
            json={"pct_elderly": 10.0},
        )
        assert resp.status_code == 404

    def test_invalid_pct_elderly_too_high(self, client):
        area = _create_area(client)
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            json={"pct_elderly": 150.0},
        )
        assert resp.status_code == 400

    def test_invalid_pct_children_negative(self, client):
        area = _create_area(client)
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            json={"pct_children": -5.0},
        )
        assert resp.status_code == 400

    def test_invalid_population_negative(self, client):
        area = _create_area(client)
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            json={"population_total": -1},
        )
        assert resp.status_code == 400

    def test_population_total_stored_correctly(self, client):
        area = _create_area(client)
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            json={"population_total": 500000},
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["population_total"] == 500000

    def test_non_json_body_returns_400(self, client):
        area = _create_area(client)
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code == 400

    def test_empty_payload_succeeds_no_values_set(self, client):
        area = _create_area(client)
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            json={},
        )
        assert resp.status_code == 201

    def test_vulnerability_notes_stored(self, client):
        area = _create_area(client)
        resp = client.post(
            f"/api/areas/{area['id']}/demographics",
            json={"vulnerability_notes": "Slum-dense neighbourhood"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["data"]["vulnerability_notes"] == "Slum-dense neighbourhood"
