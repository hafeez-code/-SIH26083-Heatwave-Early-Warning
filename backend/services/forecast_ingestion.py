"""Open-Meteo-style forecast ingestion and ML feature preparation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import requests
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

from models.database_models import ForecastObservation
from services.data_ingestion import (
    WeatherAPIError,
    WeatherAPINetworkError,
    WeatherAPITimeoutError,
    WeatherDataError,
)


@dataclass(frozen=True)
class NormalisedForecast:
    """One provider forecast timestep, independent of storage details."""

    forecast_timestamp: str
    temperature: Optional[float]
    humidity: Optional[float]
    wind_speed: Optional[float]
    precipitation: Optional[float]


def _optional_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_forecast_response(data: dict) -> list[NormalisedForecast]:
    """Normalise Open-Meteo hourly arrays into forecast timesteps.

    Open-Meteo keeps forecast variables under ``hourly`` rather than
    ``current_weather``.  Time and temperature are required to produce a
    usable heatwave feature vector; other provider variables remain nullable.
    """
    if not isinstance(data, dict):
        raise WeatherDataError("Expected a JSON object from the forecast provider.")
    hourly = data.get("hourly")
    if not isinstance(hourly, dict):
        raise WeatherDataError("Forecast response missing required key 'hourly'.")

    timestamps = hourly.get("time")
    temperatures = hourly.get("temperature_2m")
    if not isinstance(timestamps, list) or not timestamps:
        raise WeatherDataError("Forecast response missing non-empty hourly 'time'.")
    if not isinstance(temperatures, list) or len(temperatures) != len(timestamps):
        raise WeatherDataError("Forecast hourly 'temperature_2m' must match 'time'.")

    def values(name: str) -> list[object]:
        value = hourly.get(name)
        if value is None:
            return [None] * len(timestamps)
        if not isinstance(value, list) or len(value) != len(timestamps):
            raise WeatherDataError(f"Forecast hourly '{name}' must match 'time'.")
        return value

    humidity = values("relative_humidity_2m")
    wind_speed = values("wind_speed_10m")
    precipitation = values("precipitation")
    return [
        NormalisedForecast(
            forecast_timestamp=str(timestamp),
            temperature=_optional_float(temperatures[index]),
            humidity=_optional_float(humidity[index]),
            wind_speed=_optional_float(wind_speed[index]),
            precipitation=_optional_float(precipitation[index]),
        )
        for index, timestamp in enumerate(timestamps)
    ]


def fetch_forecast(
    latitude: float,
    longitude: float,
    base_url: str,
    api_key: str = "",
    timeout: int = 10,
) -> list[NormalisedForecast]:
    """Fetch and normalise hourly forecast data for provider coordinates."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
    }
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"{base_url.rstrip('/')}/forecast"
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except ReadTimeout as exc:
        raise WeatherAPITimeoutError(f"Forecast provider timed out after {timeout}s.") from exc
    except ConnectionError as exc:
        raise WeatherAPINetworkError(f"Network error contacting forecast provider: {exc}") from exc
    except RequestException as exc:
        raise WeatherAPINetworkError(f"Unexpected forecast request error: {exc}") from exc
    if not response.ok:
        raise WeatherAPIError(f"Forecast provider returned HTTP {response.status_code}: {response.text[:200]}")
    try:
        return _normalise_forecast_response(response.json())
    except ValueError as exc:
        raise WeatherDataError(f"Forecast provider response was not valid JSON: {exc}") from exc


def persist_forecasts(
    forecasts: Iterable[NormalisedForecast], area_id: int, db_session
) -> list[ForecastObservation]:
    """Stage idempotent forecast rows for an Area; the caller owns commit."""
    records = []
    for forecast in forecasts:
        record = ForecastObservation.query.filter_by(
            area_id=area_id, forecast_timestamp=forecast.forecast_timestamp
        ).one_or_none()
        if record is None:
            record = ForecastObservation(area_id=area_id, forecast_timestamp=forecast.forecast_timestamp)
            db_session.add(record)
        record.temperature = forecast.temperature
        record.humidity = forecast.humidity
        record.wind_speed = forecast.wind_speed
        record.precipitation = forecast.precipitation
        records.append(record)
    return records


def prepare_forecast_features(
    records: Iterable[NormalisedForecast | ForecastObservation],
) -> list[dict]:
    """Return the compatibility-preserving v0.10 raw feature format.

    New derived forecast features are intentionally exposed through
    ``services.forecast_features.build_forecast_features``.  Keeping this
    established helper raw prevents a v0.11 engineering change from altering
    the existing forecast API contract.
    """
    from services.forecast_features import raw_forecast_features

    return raw_forecast_features(records)
