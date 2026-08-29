"""v0.17 minimal early-warning alert service for SIH26083.

Design
------
* Primary data source is the existing rule-based risk pipeline.  No new
  risk scoring is invented here; alerts are purely a downstream projection
  of ``RiskAssessment``/stored ``HeatwaveRiskAssessment`` plus optional
  ML ``PredictionResult`` probabilities in later milestones.
* In-memory store: ``AlertStore`` is a process-wide singleton backed by
  an ordered dict keyed by a deterministic dedupe key (area_id + level +
  6h bucket).  Re-evaluating the same area and severity within the same
  six-hour window never emits a duplicate alert, even if the scheduler
  or risk route evaluates repeatedly.
* No database model in v0.17: the in-memory store is acceptable for the
  SIH prototype and avoids schema churn that would otherwise need a
  migration story.  A later milestone can persist alerts when the
  front-end requirements around retention/history solidify.
* ``Alert`` objects are timezone-aware via ``datetime.timezone.utc`` when
  a timestamp is generated locally.  External timestamps (from
  ``RiskAssessment.timestamp`` or ``PredictionResult.forecast_timestamp``)
  are stored verbatim so callers can reason about the originating event
  time independently of when the alert was raised.
"""

from __future__ import annotations

import datetime as _dt
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Optional

from services.data_ingestion import NormalisedObservation
from services.heatwave_risk import RiskAssessment
from services.prediction import PredictionResult


AlertLevel = Literal["WARNING", "WATCH", "INFORMATIONAL"]


# --------------------------------------------------------------------------- #
# Public dataclass                                                             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Alert:
    """A single early-warning alert produced from heatwave conditions."""

    alert_id: str
    area_id: int
    level: AlertLevel
    risk_level: str
    risk_score: Optional[int]
    message: str
    timestamp: str
    raised_at_utc: str
    active: bool
    factors: list[str] = field(default_factory=list)
    source: str = "rule"


# --------------------------------------------------------------------------- #
# Alert level mapping                                                          #
# --------------------------------------------------------------------------- #


def _map_risk_level(risk_level: str) -> Optional[AlertLevel]:
    """Return the alert severity for a deterministic risk level, if any."""
    level = risk_level.upper() if isinstance(risk_level, str) else ""
    if level in {"EXTREME", "HIGH"}:
        return "WARNING"
    if level == "MODERATE":
        return "WATCH"
    # LOW risk does not generate alerts at all.
    return None


def _level_rank(level: AlertLevel) -> int:
    return {"WARNING": 3, "WATCH": 2, "INFORMATIONAL": 1}[level]


# --------------------------------------------------------------------------- #
# Store                                                                        #
# --------------------------------------------------------------------------- #


def _dedupe_key(area_id: int, alert_level: AlertLevel, event_timestamp: str, source: str = "rule") -> str:
    """Return a key that suppresses duplicate alerts per 6h window.

    Re-evaluating the same area and alert severity within a six-hour
    bucket returns the identical key, so callers can safely re-evaluate
    whenever a new risk observation lands without spamming the alert
    list.
    """
    try:
        # Prefer UTC bucketing for real ISO timestamps; fall back to the
        # raw string if parsing fails (unlikely but safe).
        parsed = _dt.datetime.fromisoformat(event_timestamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        bucket = str(event_timestamp)[:13]
    else:
        bucket_hour = (parsed.hour // 6) * 6
        parsed = parsed.astimezone(_dt.timezone.utc).replace(
            hour=bucket_hour, minute=0, second=0, microsecond=0
        )
        bucket = parsed.isoformat()
    return f"{int(area_id)}::{alert_level}::{bucket}::{source}"


class AlertStore:
    """Thread-safe, process-wide ordered in-memory alert collection."""

    def __init__(self, max_alerts: int = 500) -> None:
        self._max_alerts = max_alerts
        self._by_key: "OrderedDict[str, Alert]" = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Read helpers                                                         #
    # ------------------------------------------------------------------ #

    def all(self, *, area_id: Optional[int] = None, active_only: bool = False) -> list[Alert]:
        """Return alerts, most-recently-raised last so JSON lists read chronologically."""
        with self._lock:
            items = list(self._by_key.values())
        if area_id is not None:
            items = [item for item in items if item.area_id == int(area_id)]
        if active_only:
            items = [item for item in items if item.active]
        return items

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_key)

    # ------------------------------------------------------------------ #
    # Mutation helpers                                                     #
    # ------------------------------------------------------------------ #

    def _prune_locked(self) -> None:
        while len(self._by_key) > self._max_alerts:
            self._by_key.popitem(last=False)

    def put(self, alert: Alert, dedupe_key: str) -> Alert:
        """Insert ``alert`` under ``dedupe_key``.

        If an alert already exists for the same dedupe key, the existing
        alert is returned unchanged so the caller can keep a stable
        ``alert_id`` for front-end diffing.  Callers that want a fresher
        alert can explicitly ``resolve()`` the old one before inserting.
        """
        with self._lock:
            existing = self._by_key.get(dedupe_key)
            if existing is not None:
                return existing
            self._by_key[dedupe_key] = alert
            self._prune_locked()
            return alert

    def resolve(self, alert_id: str) -> Optional[Alert]:
        """Mark a previously raised alert as no longer active.

        Returns the updated alert or ``None`` if the id was not present.
        Mutation is performed via a fresh object because ``Alert`` is
        intentionally frozen.
        """
        with self._lock:
            for existing_key, existing in self._by_key.items():
                if existing.alert_id != alert_id:
                    continue
                updated = Alert(
                    alert_id=existing.alert_id,
                    area_id=existing.area_id,
                    level=existing.level,
                    risk_level=existing.risk_level,
                    risk_score=existing.risk_score,
                    message=existing.message,
                    timestamp=existing.timestamp,
                    raised_at_utc=existing.raised_at_utc,
                    active=False,
                    factors=list(existing.factors),
                    source=existing.source,
                )
                self._by_key[existing_key] = updated
                return updated
            return None

    def clear(self) -> None:
        """Reset the store.  Primarily used by tests."""
        with self._lock:
            self._by_key.clear()


# Process-wide default store.  Flask blueprints and the scheduler integration
# both import and mutate this single instance; ``AlertStore`` is internally
# synchronised so concurrent evaluations stay consistent.
_default_store = AlertStore()


def get_default_store() -> AlertStore:
    return _default_store


# --------------------------------------------------------------------------- #
# Timestamp helpers                                                            #
# --------------------------------------------------------------------------- #


def _now_utc_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Public evaluation APIs                                                       #
# --------------------------------------------------------------------------- #


def _alert_message(area_id: int, risk_level: str, risk_score: Optional[int]) -> str:
    score = f" (score {int(risk_score)})" if risk_score is not None else ""
    if risk_level == "EXTREME":
        return f"Extreme heatwave risk detected for Area {area_id}{score}. Initiate immediate heat action plan."
    if risk_level == "HIGH":
        return f"High heatwave risk detected for Area {area_id}{score}. Advise population-level hydration and shelter guidance."
    if risk_level == "MODERATE":
        return f"Elevated heatwave watch for Area {area_id}{score}. Monitor vulnerable groups and conditions."
    return f"Heat conditions update for Area {area_id}{score}."


def _build_alert(
    *,
    area_id: int,
    alert_level: AlertLevel,
    risk_level: str,
    risk_score: Optional[int],
    timestamp: str,
    factors: Iterable[str],
    source: str = "rule",
) -> Alert:
    return Alert(
        alert_id=str(uuid.uuid4()),
        area_id=int(area_id),
        level=alert_level,
        risk_level=str(risk_level),
        risk_score=None if risk_score is None else int(risk_score),
        message=_alert_message(int(area_id), str(risk_level), risk_score),
        timestamp=str(timestamp),
        raised_at_utc=_now_utc_iso(),
        active=True,
        factors=list(factors),
        source=source,
    )


def evaluate_alert(
    area_id: int,
    risk_result: RiskAssessment,
    *,
    store: Optional[AlertStore] = None,
) -> Optional[Alert]:
    """Evaluate a rule risk ``RiskAssessment`` for area ``area_id``.

    Returns the alert if the risk crossed an alerting threshold and the
    alert is either new or still active, ``None`` for LOW risk or for a
    duplicate within the same dedupe window.
    """
    if not isinstance(risk_result, RiskAssessment):
        raise TypeError("risk_result must be a services.heatwave_risk.RiskAssessment.")
    alert_level = _map_risk_level(risk_result.risk_level)
    if alert_level is None:
        return None

    alert = _build_alert(
        area_id=area_id,
        alert_level=alert_level,
        risk_level=risk_result.risk_level,
        risk_score=risk_result.risk_score,
        timestamp=risk_result.timestamp,
        factors=risk_result.contributing_factors,
        source="rule",
    )
    dedupe_key = _dedupe_key(area_id, alert_level, risk_result.timestamp, source="rule")
    active_store = store if store is not None else get_default_store()
    return active_store.put(alert, dedupe_key)


def evaluate_alert_from_risk_assessment(
    area_id: int,
    risk_level: str,
    risk_score: Optional[int],
    *,
    timestamp: str,
    factors: Optional[Iterable[str]] = None,
    store: Optional[AlertStore] = None,
) -> Optional[Alert]:
    """Convenience wrapper for callers that only have stored row data.

    This is used by the scheduler pipeline where the stored
    ``HeatwaveRiskAssessment`` row has already been written; we avoid
    recomputing the risk and simply project the already-calculated
    level/score into an alert object using the exact same dedupe rules.
    """
    alert_level = _map_risk_level(risk_level)
    if alert_level is None:
        return None
    alert = _build_alert(
        area_id=area_id,
        alert_level=alert_level,
        risk_level=str(risk_level),
        risk_score=None if risk_score is None else int(risk_score),
        timestamp=str(timestamp),
        factors=list(factors) if factors is not None else [],
        source="rule",
    )
    dedupe_key = _dedupe_key(area_id, alert_level, str(timestamp), source="rule")
    active_store = store if store is not None else get_default_store()
    return active_store.put(alert, dedupe_key)


def evaluate_forecast_alert_from_risk_assessment(
    area_id: int,
    risk_level: str,
    risk_score: Optional[int],
    *,
    timestamp: str,
    factors: Optional[Iterable[str]] = None,
    store: Optional[AlertStore] = None,
) -> Optional[Alert]:
    """Evaluate deterministic risk for a future forecast observation.

    Like evaluate_alert_from_risk_assessment, but explicitly identifies
    the alert as a forecast projection to avoid confusing it with
    real-time deterministic risk.
    """
    alert_level = _map_risk_level(risk_level)
    if alert_level is None:
        return None

    alert = _build_alert(
        area_id=area_id,
        alert_level=alert_level,
        risk_level=str(risk_level),
        risk_score=None if risk_score is None else int(risk_score),
        timestamp=str(timestamp),
        factors=list(factors) if factors is not None else [],
        source="forecast_rule",
    )

    # Prefix the message so humans know it's a forecast
    updated_message = f"Forecast: {alert.message}"

    # We must construct a new Alert because it's frozen
    forecast_alert = Alert(
        alert_id=alert.alert_id,
        area_id=alert.area_id,
        level=alert.level,
        risk_level=alert.risk_level,
        risk_score=alert.risk_score,
        message=updated_message,
        timestamp=alert.timestamp,
        raised_at_utc=alert.raised_at_utc,
        active=alert.active,
        factors=list(alert.factors),
        source=alert.source,
    )

    dedupe_key = _dedupe_key(area_id, alert_level, str(timestamp), source="forecast_rule")
    active_store = store if store is not None else get_default_store()
    return active_store.put(forecast_alert, dedupe_key)


def evaluate_alert_from_prediction(
    prediction: PredictionResult,
    *,
    warning_threshold: float = 0.80,
    watch_threshold: float = 0.55,
    store: Optional[AlertStore] = None,
) -> Optional[Alert]:
    """Project an ML prediction into an alert, if thresholds are breached.

    v0.17 note: ML alerts are informational-only.  They do not override
    rule-based ``WARNING`` / ``WATCH`` alerts; the rule engine is the
    canonical source of truth.  ML alerts are only emitted for
    classification predictions with an exposed probability; regression
    output is ignored here.
    """
    if prediction.probability is None or prediction.task != "classification":
        return None
    probability = float(prediction.probability)
    if probability >= warning_threshold:
        alert_level: AlertLevel = "WARNING"
        risk_level_display = "ML_HIGH"
        message = (
            f"ML model predicts elevated heatwave event probability ({probability:.0%}) "
            f"for Area {prediction.area_id} at {prediction.forecast_timestamp}."
        )
    elif probability >= watch_threshold:
        alert_level = "WATCH"
        risk_level_display = "ML_MODERATE"
        message = (
            f"ML model flags possible heatwave conditions ({probability:.0%}) "
            f"for Area {prediction.area_id} at {prediction.forecast_timestamp}."
        )
    else:
        return None

    alert = Alert(
        alert_id=str(uuid.uuid4()),
        area_id=int(prediction.area_id),
        level=alert_level,
        risk_level=risk_level_display,
        risk_score=None,
        message=message,
        timestamp=str(prediction.forecast_timestamp),
        raised_at_utc=_now_utc_iso(),
        active=True,
        factors=[f"ML probability {probability:.3f}"],
        source="ml",
    )
    dedupe_key = _dedupe_key(prediction.area_id, alert_level, str(prediction.forecast_timestamp), source="ml")
    active_store = store if store is not None else get_default_store()
    return active_store.put(alert, dedupe_key)


def evaluate_forecast_alert_from_prediction(
    prediction: PredictionResult,
    *,
    warning_threshold: float = 0.80,
    watch_threshold: float = 0.55,
    store: Optional[AlertStore] = None,
) -> Optional[Alert]:
    """Evaluate an ML prediction for a future forecast observation.

    Like evaluate_alert_from_prediction, but explicitly identifies
    the alert as a forecast projection. Preserves source="ml".
    """
    if prediction.probability is None or prediction.task != "classification":
        return None
    probability = float(prediction.probability)
    if probability >= warning_threshold:
        alert_level: AlertLevel = "WARNING"
        risk_level_display = "ML_HIGH"
        message = (
            f"Forecast ML model predicts elevated heatwave event probability ({probability:.0%}) "
            f"for Area {prediction.area_id} at {prediction.forecast_timestamp}."
        )
    elif probability >= watch_threshold:
        alert_level = "WATCH"
        risk_level_display = "ML_MODERATE"
        message = (
            f"Forecast ML model flags possible heatwave conditions ({probability:.0%}) "
            f"for Area {prediction.area_id} at {prediction.forecast_timestamp}."
        )
    else:
        return None

    alert = Alert(
        alert_id=str(uuid.uuid4()),
        area_id=int(prediction.area_id),
        level=alert_level,
        risk_level=risk_level_display,
        risk_score=None,
        message=message,
        timestamp=str(prediction.forecast_timestamp),
        raised_at_utc=_now_utc_iso(),
        active=True,
        factors=[f"ML probability {probability:.3f}"],
        source="ml",
    )
    dedupe_key = _dedupe_key(prediction.area_id, alert_level, str(prediction.forecast_timestamp), source="ml")
    active_store = store if store is not None else get_default_store()
    return active_store.put(alert, dedupe_key)


def list_alerts(
    *,
    area_id: Optional[int] = None,
    active_only: bool = False,
    store: Optional[AlertStore] = None,
) -> list[Alert]:
    """Convenience wrapper that returns the current alert list."""
    active_store = store if store is not None else get_default_store()
    return active_store.all(area_id=area_id, active_only=active_only)


def alert_to_dict(alert: Alert) -> dict[str, Any]:
    """Plain-JSON friendly representation for REST endpoints."""
    return {
        "alert_id": alert.alert_id,
        "area_id": alert.area_id,
        "level": alert.level,
        "risk_level": alert.risk_level,
        "risk_score": alert.risk_score,
        "message": alert.message,
        "timestamp": alert.timestamp,
        "raised_at_utc": alert.raised_at_utc,
        "active": alert.active,
        "factors": list(alert.factors),
        "source": alert.source,
    }
