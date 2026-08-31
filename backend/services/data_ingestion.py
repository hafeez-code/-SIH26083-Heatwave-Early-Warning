"""
data_ingestion.py – Weather observation ingestion for SIH26083.

Sprint 3: Fetches a weather observation for a given latitude/longitude
from a configurable API, normalises the fields, and persists the result
to the WeatherObservation table.

Design principles
-----------------
* No secrets in source code – API URL and key come from Flask config /
  environment variables.
* Fail safely: every error path raises a typed IngestionError so callers
  always know what went wrong without having to inspect raw exceptions.
* Pure normalisation: _normalise_response() is a standalone function so
  tests can call it without touching the network or the database.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests
from requests.exceptions import ConnectionError, ReadTimeout, RequestException

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Public data structure                                                        #
# --------------------------------------------------------------------------- #

@dataclass
class NormalisedObservation:
    """A weather observation reduced to the fields we care about.

    All measurement fields are Optional – the provider may not return
    every value for every location/time.
    """

    latitude: float
    longitude: float
    timestamp: str                   # ISO-8601 string from the provider

    temperature: Optional[float]     # °C
    humidity: Optional[float]        # %
    wind_speed: Optional[float]      # km/h
    precipitation: Optional[float]   # mm
    # Solar radiation – never fabricated; None when provider does not supply it.
    solar_radiation: Optional[float] = None  # W/m²


# --------------------------------------------------------------------------- #
# Error hierarchy                                                              #
# --------------------------------------------------------------------------- #

class IngestionError(Exception):
    """Base class for all ingestion failures."""


class WeatherAPIError(IngestionError):
    """The weather API returned a non-2xx status or an error payload."""


class WeatherAPITimeoutError(IngestionError):
    """The request to the weather API timed out."""


class WeatherAPINetworkError(IngestionError):
    """A network-level failure prevented contacting the weather API."""


class WeatherDataError(IngestionError):
    """The API response was malformed or missing required fields."""


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #

def _safe_float(value: object, field: str) -> Optional[float]:
    """Convert *value* to float, returning None on failure.

    Logs a warning when the value is present but not convertible so that
    data-quality issues are visible without crashing the pipeline.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(
            "Field %r has unexpected value %r; storing as NULL.", field, value
        )
        return None


def _find_hourly_index(hourly_times: list, current_time: str) -> int:
    """Find the hourly array index whose timestamp best matches current_time.

    Open-Meteo's ``current_weather.time`` uses 15-minute resolution
    (e.g. ``2026-08-30T11:45``) while the ``hourly`` array uses
    whole-hour timestamps (e.g. ``2026-08-30T11:00``).  We match
    on the hour prefix (first 13 characters: ``YYYY-MM-DDTHH``).

    Returns -1 if no match is found.
    """
    prefix = str(current_time)[:13]  # "YYYY-MM-DDTHH"
    for idx, t in enumerate(hourly_times):
        if str(t)[:13] == prefix:
            return idx
    return -1


def _normalise_response(data: dict, latitude: float, longitude: float) -> NormalisedObservation:
    """Extract and normalise fields from a raw Open-Meteo-style API response.

    Open-Meteo returns temperature and wind speed inside ``current_weather``
    but keeps humidity, precipitation, and solar radiation in the ``hourly``
    arrays only.  This function extracts both sources and merges them into a
    single NormalisedObservation.

    Accepted response schemas:

    1. Real Open-Meteo response (``current_weather`` + ``hourly`` arrays)::

        {
            "latitude": <float>,
            "longitude": <float>,
            "current_weather": {
                "time": "<ISO-8601>",
                "temperature": <float>,  # °C
                "windspeed":   <float>,  # km/h
            },
            "hourly": {
                "time":                  ["YYYY-MM-DDTHH:00", ...],
                "relativehumidity_2m":   [<float>, ...],  # %
                "precipitation":         [<float>, ...],  # mm
                "shortwave_radiation":   [<float>, ...],  # W/m² (optional)
            }
        }

    2. Legacy / test mock format (all fields inside ``current_weather``)::

        {
            "current_weather": {
                "time": "...",
                "temperature": ...,
                "windspeed": ...,
                "relativehumidity_2m": ...,  # directly in cw for tests
                "precipitation": ...,
            }
        }

    The hourly lookup always takes priority over direct ``current_weather``
    fields for humidity / precipitation / solar radiation when both are
    present.  This ensures real API responses are handled correctly while
    existing unit-test mocks (which embed these fields in ``current_weather``)
    continue to work.

    Raises
    ------
    WeatherDataError
        When required fields (``current_weather``, ``time``) are absent.
    """
    if not isinstance(data, dict):
        raise WeatherDataError(
            f"Expected a JSON object from the weather API, got {type(data).__name__}."
        )

    cw = data.get("current_weather")
    if not isinstance(cw, dict):
        raise WeatherDataError(
            "Response missing required key 'current_weather'."
        )

    timestamp = cw.get("time")
    if not timestamp:
        raise WeatherDataError(
            "Response 'current_weather' missing required key 'time'."
        )

    # Coordinates: prefer those returned by the API (grid-snapped)
    obs_lat = _safe_float(data.get("latitude"), "latitude") or latitude
    obs_lon = _safe_float(data.get("longitude"), "longitude") or longitude

    # -----------------------------------------------------------------------
    # Humidity, precipitation, solar radiation
    # These fields exist in the hourly array in real Open-Meteo responses.
    # Fall back to current_weather keys for backwards compatibility with
    # existing test mocks that embed them there.
    # -----------------------------------------------------------------------
    hourly = data.get("hourly") or {}
    hourly_times: list = hourly.get("time") or []
    hourly_idx = _find_hourly_index(hourly_times, str(timestamp)) if hourly_times else -1

    def _hourly_value(field: str, cw_fallback: str | None = None) -> object:
        """Return the hourly value at the matched index, or fall back to cw."""
        hourly_arr = hourly.get(field) or []
        if hourly_idx >= 0 and hourly_idx < len(hourly_arr):
            return hourly_arr[hourly_idx]
        # Fallback: value might be directly in current_weather (test mocks)
        if cw_fallback:
            return cw.get(cw_fallback)
        return None

    humidity_raw = _hourly_value("relativehumidity_2m", cw_fallback="relativehumidity_2m")
    precipitation_raw = _hourly_value("precipitation", cw_fallback="precipitation")
    solar_raw = _hourly_value("shortwave_radiation", cw_fallback="shortwave_radiation")

    return NormalisedObservation(
        latitude=obs_lat,
        longitude=obs_lon,
        timestamp=str(timestamp),
        temperature=_safe_float(cw.get("temperature"), "temperature"),
        humidity=_safe_float(humidity_raw, "relativehumidity_2m"),
        wind_speed=_safe_float(cw.get("windspeed"), "windspeed"),
        precipitation=_safe_float(precipitation_raw, "precipitation"),
        solar_radiation=_safe_float(solar_raw, "shortwave_radiation"),
    )


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #

def fetch_weather(
    latitude: float,
    longitude: float,
    base_url: str,
    api_key: str = "",
    timeout: int = 10,
) -> NormalisedObservation:
    """Fetch a current weather observation for the given coordinates.

    Parameters
    ----------
    latitude, longitude:
        Geographic coordinates of the point of interest.
    base_url:
        Root URL of the weather API (from ``config.WEATHER_API_BASE_URL``).
        Should NOT include a trailing slash.
    api_key:
        Optional bearer / query-param key.  Omitted when empty.
    timeout:
        Seconds to wait for a response before raising
        ``WeatherAPITimeoutError``.

    Returns
    -------
    NormalisedObservation
        Normalised weather data ready for storage.

    Raises
    ------
    WeatherAPITimeoutError
        Request timed out.
    WeatherAPINetworkError
        Could not reach the server.
    WeatherAPIError
        Server returned a non-2xx status.
    WeatherDataError
        Response was malformed or missing required fields.
    """
    params: dict = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": "true",
        # Request humidity, precipitation, and solar radiation from the hourly
        # array.  Open-Meteo does not include these in current_weather.
        # shortwave_radiation is optional – the provider may omit it for some
        # locations/times, which is handled gracefully in _normalise_response.
        "hourly": "relativehumidity_2m,precipitation,shortwave_radiation",
    }

    headers: dict = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = f"{base_url.rstrip('/')}/forecast"

    logger.debug("Fetching weather from %s for (%.4f, %.4f)", url, latitude, longitude)

    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except ReadTimeout as exc:
        raise WeatherAPITimeoutError(
            f"Weather API timed out after {timeout}s for ({latitude}, {longitude})."
        ) from exc
    except ConnectionError as exc:
        raise WeatherAPINetworkError(
            f"Network error contacting weather API: {exc}"
        ) from exc
    except RequestException as exc:
        raise WeatherAPINetworkError(
            f"Unexpected request error: {exc}"
        ) from exc

    if not response.ok:
        raise WeatherAPIError(
            f"Weather API returned HTTP {response.status_code} for ({latitude}, {longitude}): "
            f"{response.text[:200]}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise WeatherDataError(
            f"Weather API response was not valid JSON: {exc}"
        ) from exc

    observation = _normalise_response(data, latitude, longitude)
    logger.info(
        "Fetched observation for (%.4f, %.4f) at %s.",
        observation.latitude,
        observation.longitude,
        observation.timestamp,
    )
    return observation


def save_observation(
    observation: NormalisedObservation, db_session, area_id: int | None = None
):
    """Persist a NormalisedObservation to the database.

    Parameters
    ----------
    observation:
        The normalised data returned by ``fetch_weather``.
    db_session:
        The SQLAlchemy session to use (typically ``db.session`` from the
        Flask-SQLAlchemy extension).

    The caller is responsible for committing the session.  This keeps
    transaction boundaries explicit and avoids hidden auto-commits.
    """
    from models.database_models import WeatherObservation  # local import avoids circular refs

    record = WeatherObservation(
        area_id=area_id,
        latitude=observation.latitude,
        longitude=observation.longitude,
        timestamp=observation.timestamp,
        temperature=observation.temperature,
        humidity=observation.humidity,
        wind_speed=observation.wind_speed,
        precipitation=observation.precipitation,
        solar_radiation=getattr(observation, "solar_radiation", None),
    )
    db_session.add(record)
    logger.debug("Staged WeatherObservation for (%.4f, %.4f).", observation.latitude, observation.longitude)
    return record
