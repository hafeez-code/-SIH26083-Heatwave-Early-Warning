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


def _normalise_response(data: dict, latitude: float, longitude: float) -> NormalisedObservation:
    """Extract and normalise fields from a raw Open-Meteo-style API response.

    The response schema expected::

        {
            "latitude": <float>,
            "longitude": <float>,
            "current_weather": {
                "time": "<ISO-8601>",
                "temperature": <float>,          # °C
                "windspeed": <float>,            # km/h
                "relativehumidity_2m": <float>,  # %  (optional)
                "precipitation": <float>         # mm (optional)
            }
        }

    Latitude/longitude from the response override the request coordinates
    (APIs often snap to the nearest grid point).

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

    return NormalisedObservation(
        latitude=obs_lat,
        longitude=obs_lon,
        timestamp=str(timestamp),
        temperature=_safe_float(cw.get("temperature"), "temperature"),
        humidity=_safe_float(cw.get("relativehumidity_2m"), "relativehumidity_2m"),
        wind_speed=_safe_float(cw.get("windspeed"), "windspeed"),
        precipitation=_safe_float(cw.get("precipitation"), "precipitation"),
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
        "hourly": "relativehumidity_2m,precipitation",
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


def save_observation(observation: NormalisedObservation, db_session) -> None:
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
        latitude=observation.latitude,
        longitude=observation.longitude,
        timestamp=observation.timestamp,
        temperature=observation.temperature,
        humidity=observation.humidity,
        wind_speed=observation.wind_speed,
        precipitation=observation.precipitation,
    )
    db_session.add(record)
    logger.debug("Staged WeatherObservation for (%.4f, %.4f).", observation.latitude, observation.longitude)
