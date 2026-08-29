"""
app.py – Flask application entry point for SIH26083.

Sprint 1: Minimal backend foundation with health-check endpoint.
Sprint 2: Database foundation (Flask-SQLAlchemy + SQLite, Area model).
v0.17:   Prototype CORS, early-warning alert blueprint, and demo scheduler
         lifecycle wiring with explicit config gates.
"""

import logging
import os

from flask import Flask, jsonify
from sqlalchemy import inspect

from config import config
from models.database_models import Area, db

logger = logging.getLogger(__name__)


def create_app(config_name="default"):
    """Application factory.

    Behaviour controlled explicitly via configuration:

    * ``DEV_CORS_ENABLED`` – attaches a permissive CORS after_request hook
      suitable for React/Vite frontends running on localhost.  Clearly
      marked as prototype/dev-only.
    * ``WEATHER_SCHEDULER_ENABLED`` – after DB tables are ready, iterates
      every stored Area and starts one ``WeatherScheduler`` attached to
      the app.  Default ``False`` so pytest (and ``TestingConfig``) never
      spawns background threads.  Flask's Werkzeug reloader creates two
      processes on ``flask run``; start-up is guarded with
      ``WERKZEUG_RUN_MAIN`` so schedulers only exist in the real worker.
    """
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ------------------------------------------------------------------ #
    # Extensions                                                           #
    # ------------------------------------------------------------------ #
    db.init_app(app)

    # Create tables if they do not exist yet (local dev / first run).
    # Replace with Flask-Migrate in a later sprint before going to production.
    with app.app_context():
        db.create_all()
        # create_all does not add columns to an existing SQLite database.
        # This non-destructive upgrade keeps local v0.8 databases usable.
        if db.engine.dialect.name == "sqlite":
            columns = {column["name"] for column in inspect(db.engine).get_columns("weather_observation")}
            if "area_id" not in columns:
                with db.engine.begin() as connection:
                    connection.exec_driver_sql(
                        "ALTER TABLE weather_observation ADD COLUMN area_id INTEGER REFERENCES area(id)"
                    )

    # ------------------------------------------------------------------ #
    # Prototype CORS (v0.17 development only)                             #
    # ------------------------------------------------------------------ #
    if app.config.get("DEV_CORS_ENABLED", False):

        @app.after_request
        def _dev_cors_headers(response):  # type: ignore[no-redef]
            """Attach permissive localhost-friendly CORS headers in dev.

            This hook is explicitly prototype/development grade.  It allows
            a React/Vite frontend running on any localhost port to call the
            Flask JSON API without browser preflight or credential issues.
            Not for production deployment.
            """
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            response.headers["Access-Control-Max-Age"] = "3600"
            return response

        @app.route("/api/<path:_ignored>", methods=["OPTIONS"])
        @app.route("/api/health", methods=["OPTIONS"])
        def _options_cors_preflight(_ignored=None):  # type: ignore[no-redef]
            """Respond to any ``OPTIONS /api/...`` preflight with 204.

            Combined with the ``after_request`` hook this lets any browser
            preflight for the supported verbs/headers complete successfully
            without a 404 from the routing layer.
            """
            return ("", 204)

    # ------------------------------------------------------------------ #
    # Routes                                                               #
    # ------------------------------------------------------------------ #
    from routes.alerts import alerts_bp
    from routes.areas import areas_bp
    from routes.prediction import prediction_bp
    from routes.risk import risk_bp
    from routes.weather import weather_bp
    from routes.forecast import forecast_bp

    app.register_blueprint(risk_bp)
    app.register_blueprint(areas_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(prediction_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(forecast_bp)

    # ------------------------------------------------------------------ #
    # Health-check endpoint                                                #
    # ------------------------------------------------------------------ #
    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify(
            {
                "status": "success",
                "message": "SIH26083 backend is running",
            }
        )

    # ------------------------------------------------------------------ #
    # Demo scheduler lifecycle (v0.17 – explicit config gate only)        #
    # ------------------------------------------------------------------ #
    # ``WEATHER_SCHEDULER_ENABLED`` defaults False so tests never spawn
    # threads.  Additionally, Flask's Werkzeug reloader creates two
    # processes on ``flask run``; WERKZEUG_RUN_MAIN=="true" identifies the
    # real request-serving process so the reloader helper process never
    # creates its own schedulers.  The app instance owns a list of
    # started schedulers so callers can later ``stop()`` them in bulk
    # (``app.scheduler_instances``) or via ``stop_all_schedulers``.
    def _maybe_start_demo_schedulers() -> None:
        if not app.config.get("WEATHER_SCHEDULER_ENABLED", False):
            return
        # When Flask's Werkzeug reloader is active it sets
        # WERKZEUG_RUN_MAIN="true" in the real worker process.  If the
        # variable is present with any other value we are in the reloader
        # helper and must not start schedulers (they'd be duplicated).
        # When the variable is absent the reloader is not in use and we
        # proceed normally.
        _wrm = os.environ.get("WERKZEUG_RUN_MAIN")
        if _wrm is not None and _wrm != "true":
            return

        from services.weather_scheduler import WeatherScheduler

        schedulers: list = []
        # Attach the list to the app object so host code can stop them later.
        if not hasattr(app, "scheduler_instances"):
            app.scheduler_instances = schedulers
        else:
            # Already initialised – prevent duplicate scheduler threads.
            return

        with app.app_context():
            areas = Area.query.order_by(Area.id.asc()).all()

        if not areas:
            logger.info("WeatherScheduler auto-start skipped: no Areas in the database.")
            return

        base_url = app.config.get("WEATHER_API_BASE_URL", "")
        interval = app.config.get("WEATHER_COLLECTION_INTERVAL", 900)
        api_key = app.config.get("WEATHER_API_KEY", "")
        api_timeout = app.config.get("WEATHER_API_TIMEOUT", 10)

        for area in areas:
            scheduler = WeatherScheduler(
                latitude=float(area.latitude),
                longitude=float(area.longitude),
                interval=int(interval),
                base_url=base_url,
                db_session=db.session,
                api_key=api_key,
                api_timeout=api_timeout,
                app=app,
                area_id=int(area.id),
            )
            scheduler.start()
            schedulers.append(scheduler)
            logger.info(
                "WeatherScheduler started for Area %s (%s) at interval %ss.",
                area.id,
                area.name,
                interval,
            )

        def _stop_all_schedulers(timeout: float = 5.0) -> None:
            for item in list(getattr(app, "scheduler_instances", [])):
                try:
                    item.stop(timeout=timeout)
                except Exception:  # noqa: BLE001
                    logger.exception("Error while stopping scheduler.")
            try:
                app.scheduler_instances.clear()
            except Exception:  # noqa: BLE001
                pass

        app.stop_all_schedulers = _stop_all_schedulers  # type: ignore[attr-defined]

    # Schedule the startup hook for Flask 2.x / 3.x.  ``before_first_request``
    # was deprecated in Flask 2.3, so we use the teardown-friendly signal
    # ``got_first_request`` equivalent via calling from app context builder
    # attached via ``app.before_request`` guard that runs exactly once.
    _scheduler_started_marker: list[bool] = []

    @app.before_request
    def _ensure_schedulers_started_once() -> None:
        if _scheduler_started_marker:
            return
        _scheduler_started_marker.append(True)
        try:
            _maybe_start_demo_schedulers()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to start WeatherSchedulers during app startup.")

    return app


# Local development entry point
if __name__ == "__main__":
    app = create_app("development")
    try:
        app.run(host="127.0.0.1", port=5000)
    finally:
        # Graceful stop for schedulers started via ``python app.py``.
        stop_all = getattr(app, "stop_all_schedulers", None)
        if callable(stop_all):
            stop_all()
