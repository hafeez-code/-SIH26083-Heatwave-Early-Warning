"""
test_app_scheduler.py - Unit tests for app.py scheduler lifecycle

Verifies that WEATHER_SCHEDULER_ENABLED dynamically spawns background workers
for each stored Area and avoids duplicating threads during Werkzeug reload.
"""

import os
from unittest.mock import patch, MagicMock
import pytest

from flask import Flask

# Need to import app factory and models
import sys
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app import create_app
from models.database_models import db, Area
from services.weather_scheduler import WeatherScheduler


@pytest.fixture
def test_db_app():
    """Minimal app context with an in-memory database."""
    app = create_app("default")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # We need to make sure the app factory's before_request doesn't prematurely trigger
    # during setup if we make requests, but for these tests we will manually trigger it
    # or simulate the first request.
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


class TestAppSchedulerLifecycle:

    @patch.object(WeatherScheduler, "start")
    def test_scheduler_disabled_by_default(self, mock_start, test_db_app):
        """Test 1: Scheduler disabled -> no background scheduler starts."""
        # Add an area just in case it were to start
        with test_db_app.app_context():
            db.session.add(Area(id=401, name="Area401", latitude=10.0, longitude=20.0))
            db.session.commit()
        
        # Ensure config is false
        test_db_app.config["WEATHER_SCHEDULER_ENABLED"] = False
        
        # Trigger the before_request hook manually or via a test client
        with test_db_app.test_client() as client:
            client.get("/api/health")
            
        mock_start.assert_not_called()
        assert not getattr(test_db_app, "scheduler_instances", [])

    @patch.object(WeatherScheduler, "start")
    def test_scheduler_starts_for_existing_areas(self, mock_start, test_db_app):
        """Test 2, 3, 4: Scheduler enabled -> starts one scheduler per Area."""
        with test_db_app.app_context():
            db.session.add(Area(id=201, name="Area201", latitude=10.0, longitude=20.0))
            db.session.add(Area(id=202, name="Area202", latitude=30.0, longitude=40.0))
            db.session.commit()
            
        test_db_app.config["WEATHER_SCHEDULER_ENABLED"] = True
        
        # Remove the werkzeug guard if running locally with it set
        if "WERKZEUG_RUN_MAIN" in os.environ:
            del os.environ["WERKZEUG_RUN_MAIN"]
            
        with test_db_app.test_client() as client:
            client.get("/api/health")
            
        assert mock_start.call_count == 2
        instances = getattr(test_db_app, "scheduler_instances", [])
        assert len(instances) == 2
        
        # Verify each area received its own scheduler
        area_ids_assigned = {s.area_id for s in instances}
        assert area_ids_assigned == {201, 202}

    @patch.object(WeatherScheduler, "start")
    def test_werkzeug_reloader_protection(self, mock_start, test_db_app):
        """Test 5: Scheduler does not create duplicate workers in reloader helper."""
        with test_db_app.app_context():
            db.session.add(Area(id=301, name="Area301", latitude=10.0, longitude=20.0))
            db.session.commit()
            
        test_db_app.config["WEATHER_SCHEDULER_ENABLED"] = True
        
        # Simulate being in the Werkzeug reloader helper (WERKZEUG_RUN_MAIN is false/absent but we fake it as 'false' or something else)
        os.environ["WERKZEUG_RUN_MAIN"] = "false"
        
        with test_db_app.test_client() as client:
            client.get("/api/health")
            
        mock_start.assert_not_called()
        
        # Since the before_request hook only runs once per app, we must test the other branch
        # in a fresh app instance to verify the true path. But here we just verify that false
        # prevented the start. The true path is already verified in test_scheduler_starts_for_existing_areas.
