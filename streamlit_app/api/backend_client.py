"""
backend_client.py – Centralized HTTP client for the SIH26083 Flask backend.

Configuration:
    STREAMLIT_BACKEND_URL env var (default: http://127.0.0.1:5000/api)

Design:
    * All methods return (data, error_message) tuples.
    * On success, error_message is None.
    * On failure, data is None and error_message is a human-readable string.
    * Never raises exceptions – the UI layer never sees a traceback.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL: str = os.environ.get(
    "STREAMLIT_BACKEND_URL", "http://127.0.0.1:5000/api"
).rstrip("/")

_TIMEOUT: int = 8  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: Optional[dict] = None) -> Tuple[Optional[Any], Optional[str]]:
    """Perform a GET request against the backend API.

    Returns
    -------
    (data, None)         – success; data is the parsed JSON ``data`` field.
    (None, error_str)    – failure.
    """
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return None, (
            "Backend connection unavailable. "
            "Start the SIH26083 intelligence service and refresh."
        )
    except requests.exceptions.Timeout:
        return None, f"Request timed out connecting to {url}."
    except requests.exceptions.RequestException as exc:
        return None, f"Network error: {exc}"

    try:
        payload = resp.json()
    except Exception:
        return None, f"Backend returned non-JSON response (HTTP {resp.status_code})."

    if resp.status_code == 404:
        msg = payload.get("message", "Resource not found.")
        return None, msg

    if resp.status_code >= 400:
        msg = payload.get("message", f"Backend error (HTTP {resp.status_code}).")
        return None, msg

    return payload.get("data"), None


def _post(path: str, json_data: dict) -> Tuple[Optional[Any], Optional[str]]:
    """Perform a POST request against the backend API.

    Returns
    -------
    (data, None)         – success; data is the parsed JSON ``data`` field.
    (None, error_str)    – failure.
    """
    url = f"{BASE_URL}{path}"
    try:
        resp = requests.post(url, json=json_data, timeout=_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return None, (
            "Backend connection unavailable. "
            "Start the SIH26083 intelligence service and refresh."
        )
    except requests.exceptions.Timeout:
        return None, f"Request timed out connecting to {url}."
    except requests.exceptions.RequestException as exc:
        return None, f"Network error: {exc}"

    try:
        payload = resp.json()
    except Exception:
        return None, f"Backend returned non-JSON response (HTTP {resp.status_code})."

    if resp.status_code == 404:
        msg = payload.get("message", "Resource not found.")
        return None, msg

    if resp.status_code >= 400:
        msg = payload.get("message", f"Backend error (HTTP {resp.status_code}).")
        return None, msg

    return payload.get("data"), None


# ---------------------------------------------------------------------------
# Public API methods
# ---------------------------------------------------------------------------

def check_health() -> Tuple[bool, str]:
    """Return (True, '') if backend is reachable, else (False, reason)."""
    url = f"{BASE_URL}/health"
    try:
        resp = requests.get(url, timeout=_TIMEOUT)
        if resp.status_code == 200:
            return True, ""
        return False, f"Backend returned HTTP {resp.status_code}."
    except requests.exceptions.ConnectionError:
        return False, (
            "Backend connection unavailable. "
            "Start the SIH26083 intelligence service and refresh."
        )
    except requests.exceptions.Timeout:
        return False, "Backend health check timed out."
    except requests.exceptions.RequestException as exc:
        return False, f"Network error: {exc}"


def get_areas() -> Tuple[Optional[list], Optional[str]]:
    """GET /api/areas – Return list of monitored areas."""
    return _get("/areas")


def get_area(area_id: int) -> Tuple[Optional[dict], Optional[str]]:
    """GET /api/areas/<id>"""
    return _get(f"/areas/{area_id}")


def get_area_demographics(area_id: int) -> Tuple[Optional[dict], Optional[str]]:
    """GET /api/areas/<id>/demographics"""
    return _get(f"/areas/{area_id}/demographics")


def create_area(name: str, latitude: float, longitude: float) -> Tuple[Optional[dict], Optional[str]]:
    """POST /api/areas"""
    return _post("/areas", {"name": name, "latitude": latitude, "longitude": longitude})


def update_demographics(
    area_id: int, 
    population_total: Optional[int] = None, 
    pct_elderly: Optional[float] = None, 
    pct_children: Optional[float] = None, 
    vulnerability_notes: Optional[str] = None
) -> Tuple[Optional[dict], Optional[str]]:
    """POST /api/areas/<id>/demographics"""
    payload = {}
    if population_total is not None:
        payload["population_total"] = population_total
    if pct_elderly is not None:
        payload["pct_elderly"] = pct_elderly
    if pct_children is not None:
        payload["pct_children"] = pct_children
    if vulnerability_notes is not None:
        payload["vulnerability_notes"] = vulnerability_notes
    return _post(f"/areas/{area_id}/demographics", payload)


def get_early_warning(area_id: int) -> Tuple[Optional[dict], Optional[str]]:
    """GET /api/areas/<id>/early-warning – Full unified risk picture."""
    return _get(f"/areas/{area_id}/early-warning")


def get_weather(area_id: int) -> Tuple[Optional[dict], Optional[str]]:
    """GET /api/weather?area_id=<id> – Historical observations."""
    return _get("/weather", params={"area_id": area_id})


def get_weather_forecast(area_id: int, stored: bool = True) -> Tuple[Optional[dict], Optional[str]]:
    """GET /api/weather/forecast?area_id=<id>&stored=true/false"""
    return _get("/weather/forecast", params={"area_id": area_id, "stored": str(stored).lower()})


def get_risk_forecast(area_id: int) -> Tuple[Optional[dict], Optional[str]]:
    """GET /api/risk/forecast?area_id=<id>"""
    return _get("/risk/forecast", params={"area_id": area_id})


def get_alerts(area_id: Optional[int] = None, active_only: bool = False) -> Tuple[Optional[list], Optional[str]]:
    """GET /api/alerts – All or filtered alerts."""
    params: dict = {"active_only": str(active_only).lower()}
    if area_id is not None:
        params["area_id"] = area_id

    url = f"{BASE_URL}/alerts"
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return None, "Backend connection unavailable."
    except requests.exceptions.Timeout:
        return None, "Request timed out."
    except requests.exceptions.RequestException as exc:
        return None, f"Network error: {exc}"

    try:
        payload = resp.json()
    except Exception:
        return None, f"Non-JSON response (HTTP {resp.status_code})."

    if resp.status_code >= 400:
        return None, payload.get("message", f"Backend error (HTTP {resp.status_code}).")

    # Alerts endpoint returns {"status": "success", "data": [...], "count": N}
    return payload.get("data", []), None
