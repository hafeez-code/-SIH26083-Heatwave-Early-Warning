"""
map.py – Folium GIS map component for SIH26083.

Primary:  Folium + streamlit-folium (CartoDB Dark tiles, no API key required).
Fallback: Native st.map() + risk table if streamlit-folium fails for any reason.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

try:
    import folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

try:
    from streamlit_folium import st_folium
    HAS_ST_FOLIUM = True
except ImportError:
    HAS_ST_FOLIUM = False

from components.metrics import risk_color


# ---------------------------------------------------------------------------
# Risk level → folium marker color
# ---------------------------------------------------------------------------

_FOLIUM_COLORS = {
    "NORMAL": "green",
    "LOW": "green",
    "WATCH": "orange",
    "MODERATE": "orange",
    "WARNING": "red",
    "HIGH": "red",
    "CRITICAL": "darkred",
    "EXTREME": "darkred",
    "VERY HIGH": "darkred",
}

_RISK_EMOJI = {
    "NORMAL": "🟢",
    "LOW": "🟢",
    "WATCH": "🟡",
    "MODERATE": "🟡",
    "WARNING": "🟠",
    "HIGH": "🟠",
    "CRITICAL": "🔴",
    "EXTREME": "🔴",
    "VERY HIGH": "🔴",
}


def _marker_color(level: Optional[str]) -> str:
    if not level:
        return "blue"
    return _FOLIUM_COLORS.get(level.upper(), "blue")


def _fmt(val, suffix="", decimals=1, na="N/A"):
    if val is None:
        return na
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return na


def _build_popup(area: dict, ew: Optional[dict]) -> str:
    """Build HTML popup for a map marker."""
    name = area.get("name", "Unknown")
    lat = area.get("latitude", "")
    lon = area.get("longitude", "")

    if ew:
        status = ew.get("overall_status", "—")
        emoji = _RISK_EMOJI.get((status or "").upper(), "⚪")
        weather = ew.get("weather") or {}
        hw = ew.get("heatwave_risk") or {}
        ts = ew.get("thermal_stress") or {}
        mv = ew.get("mortality_vulnerability") or {}

        color_hex = risk_color(status)

        # Wind speed unit: Open-Meteo / backend stores in km/h
        rows = [
            ("Status", f'<b style="color:{color_hex}">{emoji} {status}</b>'),
            ("Temperature", _fmt(weather.get("temperature"), "°C")),
            ("Humidity", _fmt(weather.get("humidity"), "%", 0)),
            ("Wind Speed", _fmt(weather.get("wind_speed"), " km/h")),
        ]
        if hw.get("score") is not None:
            rows.append(("Heatwave Risk Score", _fmt(hw.get("score"), "", 1)))
        if hw.get("level"):
            rows.append(("Heatwave Level", hw.get("level")))
        if ts:
            rows.append(("Thermal Stress", ts.get("level", "N/A")))
            rows.append(("Heat Index", _fmt(ts.get("heat_index_celsius"), "°C")))
        if mv:
            rows.append(("Mortality Risk", mv.get("level", "N/A")))
            rows.append(("Risk Score", _fmt(mv.get("score"), "", 1)))

        table_rows = "".join(
            f"<tr><td style='color:#94a3b8;padding:2px 8px 2px 0;font-size:12px'>{k}</td>"
            f"<td style='padding:2px 0;font-size:12px;font-weight:500'>{v}</td></tr>"
            for k, v in rows
        )
        html = f"""
        <div style="font-family:Inter,sans-serif;min-width:220px;background:#0f1f38;color:#f0f6ff;border-radius:8px;padding:12px 14px;">
          <div style="font-size:15px;font-weight:700;margin-bottom:8px;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:6px">{name}</div>
          <table>{table_rows}</table>
          <div style="margin-top:6px;font-size:10px;color:#64748b">{lat:.4f}°N, {lon:.4f}°E</div>
        </div>
        """
    else:
        html = f"""
        <div style="font-family:Inter,sans-serif;min-width:180px;background:#0f1f38;color:#f0f6ff;border-radius:8px;padding:12px 14px;">
          <div style="font-size:15px;font-weight:700;margin-bottom:6px">{name}</div>
          <div style="font-size:12px;color:#94a3b8">No risk data available.<br>Ingest weather data first.</div>
          <div style="margin-top:6px;font-size:10px;color:#64748b">{lat:.4f}°N, {lon:.4f}°E</div>
        </div>
        """
    return html


# ---------------------------------------------------------------------------
# Fallback: native st.map() + risk table
# ---------------------------------------------------------------------------

def _render_fallback_map(
    areas: list[dict],
    early_warnings: dict[int, Optional[dict]],
) -> None:
    """Render a fallback map using st.map() when Folium/streamlit-folium is unavailable."""
    st.info("📍 Displaying area map (standard view). Install `streamlit-folium` for the enhanced dark map.", icon="ℹ️")

    map_rows = []
    for area in areas:
        lat = area.get("latitude")
        lon = area.get("longitude")
        if lat is None or lon is None:
            continue
        map_rows.append({"lat": float(lat), "lon": float(lon)})

    if map_rows:
        st.map(pd.DataFrame(map_rows), zoom=4, use_container_width=True)

    # Risk status table below the fallback map
    _render_area_status_table(areas, early_warnings)


def _render_area_status_table(
    areas: list[dict],
    early_warnings: dict[int, Optional[dict]],
) -> None:
    """Render a compact risk/status table for all areas."""
    rows_html = ""
    for area in areas:
        area_id = area.get("id")
        name = area.get("name", "Unknown")
        lat = area.get("latitude", "—")
        lon = area.get("longitude", "—")
        ew = early_warnings.get(area_id) if area_id is not None else None

        if ew:
            status = ew.get("overall_status", "—")
            emoji = _RISK_EMOJI.get((status or "").upper(), "⚪")
            color = risk_color(status)
            weather = ew.get("weather") or {}
            temp = _fmt(weather.get("temperature"), "°C")
            wind = _fmt(weather.get("wind_speed"), " km/h")
            hw = ew.get("heatwave_risk") or {}
            hw_level = hw.get("level", "—")
            ml = ew.get("ml_prediction") or {}
            ml_label = ml.get("label", "—").replace("_", " ") if ml.get("available") else "Unavailable"
        else:
            status = "No data"
            emoji = "⚪"
            color = "#64748b"
            temp = "—"
            wind = "—"
            hw_level = "—"
            ml_label = "—"

        coord_str = f"{lat:.4f}°N, {lon:.4f}°E" if isinstance(lat, (int, float)) else "—"
        rows_html += f"""
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
          <td style="padding:0.45rem 0.75rem;font-size:0.82rem;color:#f0f6ff;font-weight:500">{name}</td>
          <td style="padding:0.45rem 0.75rem;font-size:0.82rem;color:{color};font-weight:700">{emoji} {status}</td>
          <td style="padding:0.45rem 0.75rem;font-size:0.82rem;color:#94a3b8">{temp}</td>
          <td style="padding:0.45rem 0.75rem;font-size:0.82rem;color:#94a3b8">{wind}</td>
          <td style="padding:0.45rem 0.75rem;font-size:0.82rem;color:#94a3b8">{hw_level}</td>
          <td style="padding:0.45rem 0.75rem;font-size:0.82rem;color:#64748b">{coord_str}</td>
        </tr>
        """

    if rows_html:
        st.markdown(
            f"""
            <div style="overflow-x:auto;margin-top:0.5rem">
              <table style="width:100%;border-collapse:collapse">
                <thead>
                  <tr style="border-bottom:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.03)">
                    <th style="padding:0.45rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Area</th>
                    <th style="padding:0.45rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Status</th>
                    <th style="padding:0.45rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Temp</th>
                    <th style="padding:0.45rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Wind</th>
                    <th style="padding:0.45rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">HW Risk</th>
                    <th style="padding:0.45rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Coordinates</th>
                  </tr>
                </thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Primary Folium map
# ---------------------------------------------------------------------------

def _render_folium_map(
    areas: list[dict],
    early_warnings: dict[int, Optional[dict]],
    height: int,
) -> None:
    """Try to render the Folium map. Raises on failure so caller can fall back."""
    lats = [a.get("latitude", 20) for a in areas]
    lons = [a.get("longitude", 78) for a in areas]
    center_lat = sum(lats) / len(lats)
    center_lon = sum(lons) / len(lons)

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=5,
        tiles=None,
    )

    # Dark tile layer (no API key – CartoDB public tiles)
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        name="CartoDB Dark",
        max_zoom=19,
    ).add_to(m)

    for area in areas:
        area_id = area.get("id")
        lat = area.get("latitude")
        lon = area.get("longitude")
        if lat is None or lon is None:
            continue

        ew = early_warnings.get(area_id) if area_id is not None else None
        status = ew.get("overall_status") if ew else None

        marker_color = _marker_color(status)
        popup_html = _build_popup(area, ew)

        folium.CircleMarker(
            location=[lat, lon],
            radius=14,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.45,
            weight=2.5,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=folium.Tooltip(
                f"<b>{area.get('name', '')}</b><br>{status or 'No data'}",
                style="font-family:Inter,sans-serif;font-size:12px;",
            ),
        ).add_to(m)

        # Inner solid dot
        folium.CircleMarker(
            location=[lat, lon],
            radius=5,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.95,
            weight=0,
        ).add_to(m)

    # Fit bounds when multiple areas present
    if len(areas) > 1:
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    # This may raise if streamlit-folium is broken or version-incompatible
    st_folium(m, height=height, use_container_width=True)


# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

def render_map(
    areas: list[dict],
    early_warnings: dict[int, Optional[dict]],
    height: int = 500,
) -> None:
    """Render a risk-colored area map.

    Primary:  Folium + streamlit-folium (CartoDB Dark, no API key).
    Fallback: Native st.map() + risk table if Folium rendering fails.

    Parameters
    ----------
    areas:           List of area dicts from /api/areas.
    early_warnings:  Mapping of area_id → early-warning data dict (or None).
    height:          Map height in pixels (Folium path only).
    """
    if not areas:
        st.markdown(
            """
            <div class="empty-state" style="padding:2.5rem;">
              <div class="empty-state-icon">🗺️</div>
              <div class="empty-state-title">No Monitored Areas</div>
              <div style="font-size:0.85rem;color:#64748b;max-width:380px;margin:0.5rem auto 0">
                Monitored areas will appear on this map once they are registered in the system
                and weather data has been ingested.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Try the full Folium map first
    if HAS_FOLIUM and HAS_ST_FOLIUM:
        try:
            _render_folium_map(areas, early_warnings, height)
            return
        except Exception as exc:  # noqa: BLE001
            # Log but don't crash — fall through to the native fallback
            st.caption(f"ℹ️ Enhanced map unavailable ({type(exc).__name__}); using standard map view.")

    # Fallback: native st.map() + table
    _render_fallback_map(areas, early_warnings)
