"""
weather_scheduler.py – Continuous weather-data collection for SIH26083.

Sprint 4 (v0.5): Runs the fetch → normalise → save pipeline on a
configurable interval and accumulates a time-series of WeatherObservation
rows in the database.

Design decisions
----------------
* WeatherScheduler is a plain Python class; it does NOT auto-start on
  import and does NOT start when tests import the module.
* A threading.Event (_stop_event) is used as the sleep / stop mechanism:
  - event.wait(interval) blocks for *interval* seconds OR returns early
    when stop() signals the event, giving responsive shutdown.
* collect_once() is public and independent of the timing loop so tests
  can exercise a single collection cycle without any sleeping.
* All IngestionError subclasses are caught per cycle; one failure never
  corrupts previously stored data and the scheduler keeps running.
* The database session is committed (or rolled back) explicitly inside
  collect_once() so transaction boundaries are always visible.
* Coordinates and API settings are injected at construction time;
  nothing production-specific is hard-coded here.
"""

from __future__ import annotations

import logging
import threading
from contextlib import nullcontext
from typing import Optional

from services.data_ingestion import IngestionError, fetch_weather
from services.risk_pipeline import persist_observation_and_risk

logger = logging.getLogger(__name__)


class WeatherScheduler:
    """Collects weather observations on a fixed interval.

    Parameters
    ----------
    latitude, longitude:
        Geographic coordinates of the monitored location.
        Supplied by the caller; never hard-coded.
    interval:
        Seconds between collection cycles.
        Typically ``app.config["WEATHER_COLLECTION_INTERVAL"]``.
    base_url:
        Weather API root URL (``app.config["WEATHER_API_BASE_URL"]``).
    db_session:
        SQLAlchemy session used to persist observations.
        Typically ``db.session`` from Flask-SQLAlchemy.
    api_key:
        Optional bearer key (``app.config["WEATHER_API_KEY"]``).
        Defaults to empty string (keyless endpoint).
    api_timeout:
        Seconds before a single HTTP request is aborted.
        Typically ``app.config["WEATHER_API_TIMEOUT"]``.
    """

    def __init__(
        self,
        *,
        latitude: float,
        longitude: float,
        interval: int,
        base_url: str,
        db_session,
        api_key: str = "",
        api_timeout: int = 10,
        app=None,
        area_id: int | None = None,
    ) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.interval = interval
        self.base_url = base_url
        self.db_session = db_session
        self.api_key = api_key
        self.api_timeout = api_timeout
        self.app = app
        self.area_id = area_id

        self._stop_event: threading.Event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Single collection cycle (public – use in tests & manual triggers)   #
    # ------------------------------------------------------------------ #

    def collect_once(self) -> bool:
        """Execute one fetch → persist observation → calculate → persist risk cycle.

        Returns
        -------
        bool
            ``True`` if the observation was fetched and staged successfully,
            ``False`` if an error occurred (already logged; does not raise).

        When ``app`` is supplied, its application context is entered for the
        entire cycle.  This makes Flask-SQLAlchemy session use safe from the
        scheduler's background thread.
        """
        context = self.app.app_context() if self.app is not None else nullcontext()
        with context:
            return self._collect_once()

    def _collect_once(self) -> bool:
        """Run one cycle while its required application context is active."""
        try:
            observation = fetch_weather(
                latitude=self.latitude,
                longitude=self.longitude,
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.api_timeout,
            )
            if self.area_id is None:
                # Preserve the v0.8 call shape for existing integrations.
                _weather, risk_record = persist_observation_and_risk(
                    observation, self.db_session
                )
            else:
                _weather, risk_record = persist_observation_and_risk(
                    observation, self.db_session, area_id=self.area_id
                )
            self.db_session.commit()
            logger.info(
                "WeatherScheduler: observation and risk stored for (%.4f, %.4f) at %s.",
                observation.latitude,
                observation.longitude,
                observation.timestamp,
            )

            # v0.17: project the persisted risk into the alert service.
            # Imported inside the method to avoid circular imports at
            # module load time; the alert service depends on heatwave_risk
            # types that risk_pipeline also imports.
            if self.area_id is not None:
                try:
                    import json as _json

                    from services.alert_service import (
                        evaluate_alert_from_risk_assessment,
                    )

                    factors_raw = risk_record.contributing_factors
                    factors = (
                        _json.loads(factors_raw)
                        if isinstance(factors_raw, str)
                        else list(factors_raw or [])
                    )
                    evaluate_alert_from_risk_assessment(
                        area_id=self.area_id,
                        risk_level=risk_record.risk_level,
                        risk_score=risk_record.risk_score,
                        timestamp=observation.timestamp,
                        factors=factors,
                    )
                except Exception:  # noqa: BLE001
                    # Alert evaluation must never cause an otherwise
                    # successful persistence cycle to report failure.
                    logger.warning(
                        "WeatherScheduler: alert evaluation failed for area %s; "
                        "observation and risk were persisted successfully.",
                        self.area_id,
                        exc_info=True,
                    )

            # Phase 3: Forecast Ingestion
            if self.area_id is not None:
                try:
                    from services.forecast_ingestion import fetch_forecast, persist_forecasts
                    forecasts = fetch_forecast(
                        latitude=self.latitude,
                        longitude=self.longitude,
                        base_url=self.base_url,
                        api_key=self.api_key,
                        timeout=self.api_timeout,
                    )
                    persist_forecasts(forecasts, self.area_id, self.db_session)
                    self.db_session.commit()
                    logger.info("WeatherScheduler: forecast ingested successfully for area %s.", self.area_id)
                except Exception:
                    # Forecast failure must not corrupt the current observation cycle
                    try:
                        self.db_session.rollback()
                    except Exception:  # pragma: no cover
                        pass
                    logger.warning(
                        "WeatherScheduler: forecast ingestion failed for area %s; "
                        "current observation was preserved.",
                        self.area_id,
                        exc_info=True,
                    )

            return True

        except IngestionError as exc:
            # Roll back any partial work so the session stays clean for
            # the next cycle.  Previously committed rows are unaffected.
            try:
                self.db_session.rollback()
            except Exception:  # pragma: no cover
                pass
            logger.error(
                "WeatherScheduler: collection failed for (%.4f, %.4f) – %s: %s",
                self.latitude,
                self.longitude,
                type(exc).__name__,
                exc,
            )
            return False

        except Exception as exc:  # noqa: BLE001
            # Unexpected non-IngestionError (e.g. DB driver error).
            # Log, roll back, and continue so the scheduler keeps running.
            try:
                self.db_session.rollback()
            except Exception:  # pragma: no cover
                pass
            logger.exception(
                "WeatherScheduler: unexpected error during collection for (%.4f, %.4f): %s",
                self.latitude,
                self.longitude,
                exc,
            )
            return False

    # ------------------------------------------------------------------ #
    # Scheduler loop                                                       #
    # ------------------------------------------------------------------ #

    def _run_loop(self) -> None:
        """Background thread target: collect, wait interval, repeat."""
        logger.info(
            "WeatherScheduler started – interval=%ds, location=(%.4f, %.4f).",
            self.interval,
            self.latitude,
            self.longitude,
        )
        while not self._stop_event.is_set():
            self.collect_once()
            # Wait for the interval OR for stop() to set the event,
            # whichever comes first.  This gives sub-second shutdown response.
            self._stop_event.wait(self.interval)

        logger.info("WeatherScheduler stopped.")

    # ------------------------------------------------------------------ #
    # Start / stop                                                         #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start the scheduler in a background daemon thread.

        Calling start() when the scheduler is already running is a no-op.
        """
        if self._thread is not None and self._thread.is_alive():
            logger.warning("WeatherScheduler.start() called but already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="WeatherScheduler",
            daemon=True,  # exits automatically when the main process exits
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the scheduler to stop and wait for the thread to finish.

        Parameters
        ----------
        timeout:
            Maximum seconds to wait for the background thread to exit.
            Defaults to 5 s – enough for the event.wait() to unblock.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def is_running(self) -> bool:
        """True if the background thread is alive."""
        return self._thread is not None and self._thread.is_alive()
