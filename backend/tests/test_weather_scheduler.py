"""
test_weather_scheduler.py – Unit tests for the WeatherScheduler.

Sprint 4 (v0.5): Continuous weather collection.

All HTTP calls are mocked.
All DB operations use an in-memory SQLite instance via a minimal Flask app.
No real sleeping occurs in any test (the interval is patched or set to 0).

Test coverage
-------------
1.  collect_once() calls fetch_weather with the configured parameters.
2.  collect_once() passes the returned observation to save_observation.
3.  collect_once() commits the session on success.
4.  collect_once() returns True on success.
5.  collect_once() catches IngestionError, logs it, and returns False.
6.  collect_once() rolls back the session after an IngestionError.
7.  collect_once() catches an unexpected non-IngestionError and returns False.
8.  The scheduler thread starts and stops cleanly.
9.  is_running reflects the thread state correctly.
10. The configured interval is passed to threading.Event.wait().
11. stop() signals the event and joins the thread.
12. Calling start() twice does not spawn a second thread.
13. End-to-end: scheduler stores observations in an in-memory SQLite DB.
"""

from __future__ import annotations

import sys
import os
import time
import threading
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.data_ingestion import (   # noqa: E402
    IngestionError,
    NormalisedObservation,
    WeatherAPIError,
    WeatherAPITimeoutError,
)
from services.weather_scheduler import WeatherScheduler  # noqa: E402

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

LAT, LON = 28.6139, 77.2090   # New Delhi
BASE_URL = "https://api.example.com/v1"
INTERVAL = 900                 # seconds (never actually slept in tests)

_SAMPLE_OBS = NormalisedObservation(
    latitude=LAT,
    longitude=LON,
    timestamp="2026-08-28T12:00",
    temperature=38.5,
    humidity=55.0,
    wind_speed=15.2,
    precipitation=0.0,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_session():
    """Return a MagicMock that acts as a SQLAlchemy session."""
    session = MagicMock()
    return session


@pytest.fixture()
def scheduler(mock_session):
    """Return a WeatherScheduler instance wired to the mock session."""
    return WeatherScheduler(
        latitude=LAT,
        longitude=LON,
        interval=INTERVAL,
        base_url=BASE_URL,
        db_session=mock_session,
        api_key="",
        api_timeout=5,
    )


@pytest.fixture()
def in_memory_db():
    """Minimal Flask app + in-memory SQLite for end-to-end DB tests."""
    import flask
    from models.database_models import db, WeatherObservation

    app = flask.Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield db, WeatherObservation


# ---------------------------------------------------------------------------
# collect_once() unit tests (mocked fetch & pipeline)
# ---------------------------------------------------------------------------

class TestCollectOnce:

    @patch("services.weather_scheduler.persist_observation_and_risk")
    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    def test_calls_fetch_weather_with_correct_args(
        self, mock_fetch, mock_pipeline, scheduler, mock_session
    ):
        """Test 1 – collect_once() calls fetch_weather with configured params."""
        scheduler.collect_once()

        mock_fetch.assert_called_once_with(
            latitude=LAT,
            longitude=LON,
            base_url=BASE_URL,
            api_key="",
            timeout=5,
        )

    @patch("services.weather_scheduler.persist_observation_and_risk")
    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    def test_passes_observation_to_risk_pipeline(
        self, mock_fetch, mock_pipeline, scheduler, mock_session
    ):
        """The fetched observation is passed to the risk pipeline."""
        scheduler.collect_once()

        mock_pipeline.assert_called_once_with(_SAMPLE_OBS, mock_session)

    @patch("services.weather_scheduler.persist_observation_and_risk")
    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    def test_commits_session_on_success(
        self, mock_fetch, mock_pipeline, scheduler, mock_session
    ):
        """Test 3 – The DB session is committed after a successful cycle."""
        scheduler.collect_once()

        mock_session.commit.assert_called_once()

    @patch("services.weather_scheduler.persist_observation_and_risk")
    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    def test_returns_true_on_success(
        self, mock_fetch, mock_pipeline, scheduler
    ):
        """Test 4 – collect_once() returns True on success."""
        result = scheduler.collect_once()
        assert result is True

    @patch("services.weather_scheduler.fetch_weather",
           side_effect=WeatherAPIError("503 unavailable"))
    def test_ingestion_error_is_caught_returns_false(
        self, mock_fetch, scheduler, mock_session
    ):
        """Test 5 – IngestionError is caught; collect_once returns False."""
        result = scheduler.collect_once()
        assert result is False

    @patch("services.weather_scheduler.fetch_weather",
           side_effect=WeatherAPITimeoutError("timed out"))
    def test_ingestion_error_triggers_rollback(
        self, mock_fetch, scheduler, mock_session
    ):
        """Test 6 – Session is rolled back after an IngestionError."""
        scheduler.collect_once()
        mock_session.rollback.assert_called_once()

    @patch("services.weather_scheduler.fetch_weather",
           side_effect=WeatherAPIError("503"))
    def test_ingestion_error_does_not_raise(self, mock_fetch, scheduler):
        """Test 5 (corollary) – IngestionError must NOT propagate out."""
        # If collect_once() raises, this test fails.
        scheduler.collect_once()

    @patch("services.weather_scheduler.fetch_weather",
           side_effect=RuntimeError("unexpected"))
    def test_unexpected_error_is_caught_returns_false(
        self, mock_fetch, scheduler
    ):
        """Test 7 – Non-IngestionError is also caught; returns False."""
        result = scheduler.collect_once()
        assert result is False

    @patch("services.weather_scheduler.persist_observation_and_risk")
    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    def test_no_commit_after_ingestion_error(
        self, mock_fetch, mock_pipeline, scheduler, mock_session
    ):
        """A failed cycle must not commit (rollback only)."""
        mock_pipeline.side_effect = IngestionError("pipeline error")
        scheduler.collect_once()
        mock_session.commit.assert_not_called()
        mock_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# Scheduler threading tests
# ---------------------------------------------------------------------------

class TestSchedulerThreading:

    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    @patch("services.weather_scheduler.persist_observation_and_risk")
    def test_start_creates_live_thread(self, mock_pipeline, mock_fetch, scheduler):
        """Test 8 – start() spawns a background thread; is_running is True."""
        assert not scheduler.is_running
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()

    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    @patch("services.weather_scheduler.persist_observation_and_risk")
    def test_stop_terminates_thread(self, mock_pipeline, mock_fetch, scheduler):
        """Test 8 / 11 – stop() terminates the thread cleanly."""
        scheduler.start()
        scheduler.stop(timeout=2.0)
        assert not scheduler.is_running

    def test_is_running_false_before_start(self, scheduler):
        """Test 9 – is_running is False before start() is called."""
        assert not scheduler.is_running

    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    @patch("services.weather_scheduler.persist_observation_and_risk")
    def test_double_start_does_not_spawn_second_thread(
        self, mock_pipeline, mock_fetch, scheduler
    ):
        """Test 12 – Calling start() twice uses only one thread."""
        scheduler.start()
        thread_first = scheduler._thread
        scheduler.start()               # second call – should be a no-op
        thread_second = scheduler._thread
        assert thread_first is thread_second
        scheduler.stop()

    @patch("services.weather_scheduler.fetch_weather",
           side_effect=WeatherAPIError("API down"))
    def test_scheduler_continues_after_failed_cycle(
        self, mock_fetch, mock_session
    ):
        """Test 8 – A failed cycle must NOT stop the scheduler thread."""
        sched = WeatherScheduler(
            latitude=LAT,
            longitude=LON,
            interval=0,          # no real sleeping
            base_url=BASE_URL,
            db_session=mock_session,
        )
        sched.start()
        time.sleep(0.05)         # let the loop tick at least once
        assert sched.is_running  # still alive despite errors
        sched.stop(timeout=2.0)


# ---------------------------------------------------------------------------
# Interval configuration test (mocked Event.wait)
# ---------------------------------------------------------------------------

class TestIntervalRespected:

    @patch("services.weather_scheduler.persist_observation_and_risk")
    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    def test_configured_interval_passed_to_event_wait(
        self, mock_fetch, mock_pipeline, mock_session
    ):
        """Test 3 (interval) – The scheduler waits for exactly `interval` seconds."""
        custom_interval = 300
        sched = WeatherScheduler(
            latitude=LAT,
            longitude=LON,
            interval=custom_interval,
            base_url=BASE_URL,
            db_session=mock_session,
        )

        wait_calls: list[float] = []

        original_wait = threading.Event.wait

        def recording_wait(self_event, timeout=None):
            if timeout is not None:
                wait_calls.append(timeout)
                # Signal stop after recording the first wait so the thread exits.
                self_event.set()
                return True
            return original_wait(self_event, timeout)  # pragma: no cover

        with patch.object(threading.Event, "wait", recording_wait):
            sched.start()
            sched._thread.join(timeout=2.0)

        assert any(w == custom_interval for w in wait_calls), (
            f"Expected interval {custom_interval}s in wait calls, got {wait_calls}"
        )


# ---------------------------------------------------------------------------
# End-to-end: collect_once() → real in-memory SQLite
# ---------------------------------------------------------------------------

class TestCollectOnceEndToEnd:

    @patch("services.weather_scheduler.fetch_weather", return_value=_SAMPLE_OBS)
    def test_observation_persisted_to_sqlite(self, mock_fetch, in_memory_db):
        """Single collect_once() cycle stores one row in the real DB."""
        db_ext, WeatherObservation = in_memory_db

        sched = WeatherScheduler(
            latitude=LAT,
            longitude=LON,
            interval=INTERVAL,
            base_url=BASE_URL,
            db_session=db_ext.session,
        )

        result = sched.collect_once()

        assert result is True
        rows = WeatherObservation.query.all()
        assert len(rows) == 1

        row = rows[0]
        assert row.latitude == pytest.approx(LAT)
        assert row.longitude == pytest.approx(LON)
        assert row.timestamp == "2026-08-28T12:00"
        assert row.temperature == pytest.approx(38.5)
        assert row.risk_assessment is not None
        assert row.risk_assessment.weather_observation_id == row.id

    @patch("services.weather_scheduler.fetch_weather")
    def test_multiple_cycles_accumulate_rows(self, mock_fetch, in_memory_db):
        """Three collect_once() calls should produce three distinct rows."""
        db_ext, WeatherObservation = in_memory_db

        timestamps = [
            "2026-08-28T12:00",
            "2026-08-28T12:15",
            "2026-08-28T12:30",
        ]

        sched = WeatherScheduler(
            latitude=LAT,
            longitude=LON,
            interval=INTERVAL,
            base_url=BASE_URL,
            db_session=db_ext.session,
        )

        for ts in timestamps:
            mock_fetch.return_value = NormalisedObservation(
                latitude=LAT,
                longitude=LON,
                timestamp=ts,
                temperature=38.0,
                humidity=50.0,
                wind_speed=10.0,
                precipitation=0.0,
            )
            sched.collect_once()

        rows = WeatherObservation.query.order_by(WeatherObservation.timestamp).all()
        assert len(rows) == 3
        assert [r.timestamp for r in rows] == timestamps
        assert all(row.risk_assessment is not None for row in rows)
