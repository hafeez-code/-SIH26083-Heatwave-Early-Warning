"""Deterministic feature engineering for persisted hourly forecasts.

This module deliberately has no provider or database-session responsibilities.
It accepts the v0.10 ``ForecastObservation`` ORM model, its
``NormalisedForecast`` ingestion representation, or equivalent mappings.

The temperature rolling features use a three-timestep window.  A window is
available only when all three temperatures are present; this avoids imputing
missing weather measurements.  ``high_temperature_indicator`` uses 40°C, a
transparent configurable screening threshold rather than a risk prediction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Optional


RAW_FEATURE_NAMES = (
    "forecast_timestamp",
    "temperature",
    "humidity",
    "wind_speed",
    "precipitation",
)

TEMPERATURE_WINDOW = 3
HIGH_TEMPERATURE_THRESHOLD = 40.0


def _value(record: object, name: str):
    """Read a forecast attribute from either an object or a mapping."""
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def raw_forecast_features(records: Iterable[object]) -> list[dict]:
    """Return the stable v0.10 raw forecast-feature representation.

    This intentionally preserves input order and field names so callers using
    the existing API helper retain its exact v0.10 output contract.
    """
    return [{name: _value(record, name) for name in RAW_FEATURE_NAMES} for record in records]


def build_forecast_features(
    records: Iterable[object],
    *,
    temperature_window: int = TEMPERATURE_WINDOW,
    high_temperature_threshold: float = HIGH_TEMPERATURE_THRESHOLD,
) -> list[dict]:
    """Create raw and derived ML-ready features from hourly forecasts.

    Input is grouped by ``area_id`` before temporal values are calculated, and
    every group is ordered by timestamp.  Inputs without an ``area_id`` (the
    v0.10 normalised provider representation) are treated as one sequence.
    Missing source values remain ``None``; derived values that need a missing
    input are also ``None``.  Indicators are integer ``0``/``1`` when known:
    precipitation is present when it is greater than zero, and high temperature
    is at or above ``high_temperature_threshold``.
    """
    if temperature_window < 1:
        raise ValueError("temperature_window must be at least 1.")

    groups: dict[object, list[tuple[int, object]]] = defaultdict(list)
    for index, record in enumerate(records):
        groups[_value(record, "area_id")].append((index, record))

    features = []
    for area_id in sorted(groups, key=lambda value: (value is not None, str(value))):
        ordered_records = sorted(
            groups[area_id],
            key=lambda item: (str(_value(item[1], "forecast_timestamp")), item[0]),
        )
        temperatures: list[Optional[float]] = []
        previous_temperature: Optional[float] = None

        for _, record in ordered_records:
            raw = {name: _value(record, name) for name in RAW_FEATURE_NAMES}
            temperature = raw["temperature"]
            humidity = raw["humidity"]
            precipitation = raw["precipitation"]
            temperatures.append(temperature)
            window = temperatures[-temperature_window:]

            temperature_humidity_interaction = (
                None if temperature is None or humidity is None else temperature * humidity
            )
            temperature_change = (
                None if temperature is None or previous_temperature is None
                else temperature - previous_temperature
            )
            if len(window) == temperature_window and all(value is not None for value in window):
                rolling_temperature_mean = sum(window) / temperature_window
                rolling_temperature_max = max(window)
            else:
                rolling_temperature_mean = None
                rolling_temperature_max = None

            features.append({
                **raw,
                "temperature_humidity_interaction": temperature_humidity_interaction,
                "temperature_change": temperature_change,
                "temperature_rolling_mean_3": rolling_temperature_mean,
                "temperature_rolling_max_3": rolling_temperature_max,
                "precipitation_indicator": None if precipitation is None else int(precipitation > 0),
                "high_temperature_indicator": (
                    None if temperature is None else int(temperature >= high_temperature_threshold)
                ),
            })
            previous_temperature = temperature
    return features
