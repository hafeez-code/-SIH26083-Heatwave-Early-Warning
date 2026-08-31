"""
command_center.py – Main Command Center dashboard page for SIH26083.

Communicates:  AI-Assisted Multi-Area Heatwave Early-Warning System
Architecture:  All data comes from REST API via backend_client — never directly
               from SQLite, ML artifacts, or backend services.
"""
from __future__ import annotations

import streamlit as st

import api.backend_client as client
from components.map import render_map
from components.metrics import (
    render_kpi_row,
    risk_color,
    section_title,
    empty_state,
    render_badge,
)
from components.risk_cards import (
    render_heatwave_risk_card,
    render_thermal_stress_card,
    render_mortality_card,
    render_weather_card,
)
from components.ml_prediction import render_ml_prediction_card
from components.charts import (
    forecast_temperature_chart,
    forecast_humidity_chart,
    risk_trajectory_chart,
    plot_chart,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(val, suffix="", decimals=1, na="—"):
    if val is None:
        return na
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return na


# ---------------------------------------------------------------------------
# Cached fetches
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def _fetch_areas():
    return client.get_areas()


@st.cache_data(ttl=60)
def _fetch_ew(area_id: int):
    return client.get_early_warning(area_id)


@st.cache_data(ttl=60)
def _fetch_alerts(area_id: int):
    return client.get_alerts(area_id=area_id)


@st.cache_data(ttl=60)
def _fetch_weather(area_id: int):
    return client.get_weather(area_id)


@st.cache_data(ttl=60)
def _fetch_weather_forecast(area_id: int):
    return client.get_weather_forecast(area_id, stored=True)


@st.cache_data(ttl=60)
def _fetch_risk_forecast(area_id: int):
    return client.get_risk_forecast(area_id)


# ---------------------------------------------------------------------------
# Alert card renderer
# ---------------------------------------------------------------------------

def _render_alert(alert: dict) -> None:
    level = alert.get("level", "WATCH")
    cls_map = {
        "WARNING": "alert-warning",
        "WATCH": "alert-watch",
        "INFORMATIONAL": "alert-info",
    }
    cls = cls_map.get(level, "alert-watch")
    factors = alert.get("factors", [])
    factors_html = ""
    if factors:
        factors_html = "<ul style='margin:0.3rem 0 0 0;padding-left:1.2rem'>" + "".join(
            f"<li style='font-size:0.8rem;color:#94a3b8'>{f}</li>" for f in factors
        ) + "</ul>"

    st.markdown(
        f"""
        <div class="alert-card {cls}">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.3rem;margin-bottom:0.35rem">
            <span style="font-weight:600">{render_badge(level)} {alert.get('risk_level','')}</span>
            <span style="font-size:0.78rem;color:#94a3b8">{alert.get('raised_at_utc','')}</span>
          </div>
          <div style="font-size:0.85rem;color:#cbd5e1">{alert.get('message','')}</div>
          {factors_html}
          <div style="font-size:0.74rem;color:#475569;margin-top:0.4rem">Source: {alert.get('source','').upper()} &nbsp;·&nbsp; Score: {alert.get('risk_score','—')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Add area form
# ---------------------------------------------------------------------------

def _render_add_area_form():
    st.markdown(
        """
        <div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:1.5rem;max-width:800px;margin:0 auto;">
          <h3 style="margin-top:0;margin-bottom:1.5rem;color:#f0f6ff;">➕ Add Monitored Area</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.form("add_area_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            name = st.text_input("Area Name", key="add_area_name")
        with col2:
            lat = st.number_input("Latitude", value=20.0, format="%.4f", key="add_area_lat")
        with col3:
            lon = st.number_input("Longitude", value=78.0, format="%.4f", key="add_area_lon")

        st.markdown("##### Demographics (Optional)")
        col4, col5, col6 = st.columns(3)
        with col4:
            pop = st.number_input("Population Total", min_value=0, value=None, step=1000, key="add_area_pop")
        with col5:
            elderly = st.number_input("Elderly (≥65) %", min_value=0.0, max_value=100.0, value=None, format="%.1f", key="add_area_elderly")
        with col6:
            children = st.number_input("Children (<18) %", min_value=0.0, max_value=100.0, value=None, format="%.1f", key="add_area_children")
        notes = st.text_area("Vulnerability Notes", key="add_area_notes")

        submit = st.form_submit_button("Register Area")

        if submit:
            if not name:
                st.error("Area Name is required.")
                return

            with st.spinner("Creating area..."):
                area_data, err = client.create_area(name, lat, lon)
                if err:
                    st.error(f"Failed to create area: {err}")
                    return

                area_id = area_data.get("id")
                if area_id is not None and (pop is not None or elderly is not None or children is not None or notes):
                    _, demo_err = client.update_demographics(area_id, pop, elderly, children, notes)
                    if demo_err:
                        st.warning(f"Area created, but failed to save demographics: {demo_err}")

                st.success(f"Area '{name}' registered successfully.")
                st.cache_data.clear()
                st.session_state["new_area_id"] = area_id
                st.rerun()


# ---------------------------------------------------------------------------
# Multi-area overview table
# ---------------------------------------------------------------------------

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


def _render_area_overview(areas: list[dict], early_warnings: dict[int, dict | None]) -> None:
    """Render the multi-area risk overview table.

    All values come from the backend early-warning API.
    Missing data is shown as 'Unavailable' — never fabricated.
    """
    rows_html = ""
    for area in areas:
        area_id = area.get("id")
        name = area.get("name", "Unknown")
        ew = early_warnings.get(area_id) if area_id is not None else None

        if ew:
            status = ew.get("overall_status", "—")
            emoji = _RISK_EMOJI.get((status or "").upper(), "⚪")
            color = risk_color(status)
            weather = ew.get("weather") or {}
            temp = _fmt(weather.get("temperature"), "°C")
            # Wind speed: Open-Meteo/backend stores in km/h
            wind = _fmt(weather.get("wind_speed"), " km/h")
            hw = ew.get("heatwave_risk") or {}
            hw_score = _fmt(hw.get("score"), "", 1)
            hw_level = hw.get("level", "—")

            ml = ew.get("ml_prediction") or {}
            if ml.get("available"):
                ml_label = ml.get("label", "UNKNOWN").replace("_", " ")
                ml_prob = ml.get("probability")
                ml_prob_str = (
                    f"{float(ml_prob) * 100:.1f}%" if ml_prob is not None else "—"
                )
                ml_color = "#ef4444" if ml_label == "HEATWAVE" else "#10b981"
            else:
                ml_label = "Unavailable"
                ml_prob_str = "—"
                ml_color = "#64748b"

            has_alerts = ew.get("has_active_alerts", False)
            alert_html = (
                '<span style="color:#f59e0b;font-size:0.75rem;font-weight:600">⚡ Active</span>'
                if has_alerts else
                '<span style="color:#10b981;font-size:0.75rem">✅ None</span>'
            )
        else:
            status = "No data"
            emoji = "⚪"
            color = "#64748b"
            temp = "—"
            wind = "—"
            hw_score = "—"
            hw_level = "—"
            ml_label = "Unavailable"
            ml_prob_str = "—"
            ml_color = "#64748b"
            alert_html = '<span style="color:#64748b;font-size:0.75rem">—</span>'

        rows_html += f"""
        <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
          <td style="padding:0.5rem 0.75rem;font-size:0.83rem;color:#f0f6ff;font-weight:600">{name}</td>
          <td style="padding:0.5rem 0.75rem;font-size:0.83rem;color:{color};font-weight:700">{emoji} {status}</td>
          <td style="padding:0.5rem 0.75rem;font-size:0.82rem;color:#94a3b8">{temp}</td>
          <td style="padding:0.5rem 0.75rem;font-size:0.82rem;color:#94a3b8">{wind}</td>
          <td style="padding:0.5rem 0.75rem;font-size:0.82rem;color:#94a3b8">{hw_level} ({hw_score})</td>
          <td style="padding:0.5rem 0.75rem;font-size:0.82rem;color:{ml_color};font-weight:600">{ml_label}</td>
          <td style="padding:0.5rem 0.75rem;font-size:0.82rem;color:{ml_color}">{ml_prob_str}</td>
          <td style="padding:0.5rem 0.75rem">{alert_html}</td>
        </tr>
        """

    if not rows_html:
        return

    st.markdown(
        f"""
        <div class="glass-card" style="padding:0;overflow:hidden">
          <table style="width:100%;border-collapse:collapse">
            <thead>
              <tr style="border-bottom:1px solid rgba(255,255,255,0.1);
                         background:rgba(255,255,255,0.03)">
                <th style="padding:0.5rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Area</th>
                <th style="padding:0.5rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Status</th>
                <th style="padding:0.5rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Temp</th>
                <th style="padding:0.5rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Wind</th>
                <th style="padding:0.5rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">HW Risk</th>
                <th style="padding:0.5rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">ML Forecast</th>
                <th style="padding:0.5rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">HW Prob</th>
                <th style="padding:0.5rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Alerts</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
        <div style="font-size:0.69rem;color:#3d5272;margin-top:0.4rem;text-align:right">
          ML: Prototype v0.16 · Forecast-pattern classifier · Not an official warning
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render(backend_online: bool) -> None:
    """Render the main command center dashboard page."""
    if not backend_online:
        st.markdown(
            """
            <div style="text-align:center;padding:4rem 2rem">
              <div style="font-size:3.5rem;margin-bottom:1rem">⚡</div>
              <div style="font-size:1.3rem;font-weight:700;color:#ef4444;margin-bottom:0.75rem">Backend Unavailable</div>
              <div style="color:#94a3b8;max-width:420px;margin:0 auto;font-size:0.9rem">
                The SIH26083 intelligence service is not reachable.<br>
                Start the backend with <code style="background:rgba(255,255,255,0.07);padding:0.1em 0.4em;border-radius:4px">python app.py</code>
                from the <code style="background:rgba(255,255,255,0.07);padding:0.1em 0.4em;border-radius:4px">backend/</code> directory, then refresh.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # -----------------------------------------------------------------------
    # Fetch all areas
    # -----------------------------------------------------------------------
    areas, err = _fetch_areas()
    if err:
        st.error(f"Failed to fetch areas: {err}")
        return

    # -----------------------------------------------------------------------
    # Empty state
    # -----------------------------------------------------------------------
    if not areas:
        empty_state(
            "🗂️",
            "No Monitored Areas Found",
            "To begin using the early warning system, register a monitored area.",
        )
        _render_add_area_form()
        return

    # -----------------------------------------------------------------------
    # System banner
    # -----------------------------------------------------------------------
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,rgba(37,99,235,0.12),rgba(6,182,212,0.06));
                    border:1px solid rgba(37,99,235,0.2);border-radius:12px;
                    padding:1.1rem 1.5rem;margin-bottom:1.2rem;
                    display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem">
          <div>
            <div style="font-size:0.65rem;font-weight:700;color:#60a5fa;text-transform:uppercase;
                        letter-spacing:0.18em;margin-bottom:0.2rem">
              AI-Assisted Multi-Area Heatwave Early-Warning System
            </div>
            <div style="font-size:1.1rem;font-weight:700;color:#f0f6ff">
              SIH26083 · Command Center
            </div>
          </div>
          <div style="text-align:right">
            <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Monitoring</div>
            <div style="font-size:1.6rem;font-weight:800;color:#06b6d4;line-height:1">{len(areas)}</div>
            <div style="font-size:0.7rem;color:#64748b">Areas</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # Fetch early-warning data for ALL areas (for overview table + map)
    # NOTE: We reuse the existing per-area endpoint — there is no
    #       multi-area batch endpoint.  Individual calls are cached (ttl=60).
    # -----------------------------------------------------------------------
    early_warnings: dict[int, dict | None] = {}
    with st.spinner("Loading area intelligence..."):
        for a in areas:
            a_ew, _ = _fetch_ew(a["id"])
            early_warnings[a["id"]] = a_ew



    # -----------------------------------------------------------------------
    # Area Selection (single-area detail)
    # -----------------------------------------------------------------------
    area_options = {a["name"]: a["id"] for a in areas}

    default_index = 0
    if "new_area_id" in st.session_state:
        for idx, (_, aid) in enumerate(area_options.items()):
            if aid == st.session_state["new_area_id"]:
                default_index = idx
                break
        del st.session_state["new_area_id"]

    col_sel, _ = st.columns([1, 2])
    with col_sel:
        selected_name = st.selectbox(
            "DETAILED AREA ANALYSIS ▼",
            options=list(area_options.keys()),
            index=default_index,
            key="cmd_area_select",
        )
    selected_id = area_options[selected_name]

    # Use cached EW from the overview fetch where possible
    ew = early_warnings.get(selected_id)
    ew_err = None
    if ew is None:
        # Re-fetch if needed (e.g. area not in overview dict)
        ew, ew_err = _fetch_ew(selected_id)

    # Additional per-area data
    with st.spinner("Loading detailed data..."):
        weather_data, _ = _fetch_weather(selected_id)
        wf_data, _ = _fetch_weather_forecast(selected_id)
        rf_data, _ = _fetch_risk_forecast(selected_id)
        alerts, _ = _fetch_alerts(selected_id)

    # -----------------------------------------------------------------------
    # 1. CURRENT CONDITIONS HERO
    # -----------------------------------------------------------------------
    w: dict = {}
    if ew and ew.get("weather"):
        w = ew.get("weather", {})
    elif weather_data and weather_data.get("observations"):
        obs_list = weather_data.get("observations", [])
        if obs_list:
            w = obs_list[-1]

    if not w:
        st.markdown(
            '<div style="color:#64748b;font-size:0.85rem">'
            'No weather observations available yet. The weather scheduler is collecting data.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        temp_val = _fmt(w.get("temperature"), "°", 1, "—")
        hum_val = _fmt(w.get("humidity"), "%", 0, "—")
        wind_val = _fmt(w.get("wind_speed"), " km/h", 1, "—")
        precip_val = _fmt(w.get("precipitation"), " mm", 1, "—")
        solar_val = _fmt(w.get("solar_radiation"), " W/m²", 1, "—")
        
        st.markdown(
            f"""
            <div class="weather-hero">
                <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:2rem;">
                    <div style="flex:1; min-width:250px;">
                        <div class="weather-hero-city">{selected_name}</div>
                        <div class="weather-hero-temp">{temp_val}</div>
                        <div class="weather-hero-cond">Current conditions</div>
                        <div style="font-size:0.8rem;color:#cbd5e1;margin-top:1rem;">
                            Last updated: {w.get('timestamp', 'Unknown')}
                        </div>
                    </div>
                    <div style="flex:1; min-width:250px; display:flex; flex-direction:column; justify-content:center;">
                        <div class="hero-stat-row">
                            <span class="hero-stat-label">Humidity</span>
                            <span class="hero-stat-val">{hum_val}</span>
                        </div>
                        <div class="hero-stat-row">
                            <span class="hero-stat-label">Wind</span>
                            <span class="hero-stat-val">{wind_val}</span>
                        </div>
                        <div class="hero-stat-row">
                            <span class="hero-stat-label">Precipitation</span>
                            <span class="hero-stat-val">{precip_val}</span>
                        </div>
                        <div class="hero-stat-row">
                            <span class="hero-stat-label">Solar radiation</span>
                            <span class="hero-stat-val">{solar_val}</span>
                        </div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # -----------------------------------------------------------------------
    # Hourly Forecast (2)
    # -----------------------------------------------------------------------
    forecasts = (wf_data or {}).get("forecasts", [])
    if forecasts:
        # Generate horizontal scrollable items
        items_html = ""
        for f in forecasts[:48]:  # Show up to 48 hours
            # e.g., f = {"timestamp": "2026-08-31 14:00", "temperature": 32.5, "precipitation": 0.0}
            t_str = str(f.get("timestamp", ""))[-8:-3] # Extract HH:MM
            temp = _fmt(f.get("temperature"), "°", 0)
            precip = f.get("precipitation")
            precip_str = f"{precip:.1f} mm" if precip and float(precip) > 0 else ""
            
            items_html += f"""
            <div class="hourly-item">
                <div class="hourly-time">{t_str}</div>
                <div class="hourly-temp">{temp}</div>
                <div class="hourly-precip">{precip_str}</div>
            </div>
            """
        st.markdown(
            f"""
            <div class="section-title">Hourly Forecast</div>
            <div class="hourly-container">
                {items_html}
            </div>
            """, unsafe_allow_html=True
        )

    # -----------------------------------------------------------------------
    # Risk Intelligence (single area)
    # -----------------------------------------------------------------------
    section_title("Risk Intelligence", "🚦")
    if not ew:
        st.markdown(
            '<div style="color:#64748b;font-size:0.85rem">'
            'Risk intelligence data unavailable for this area. Ingest weather data first.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        col_hw, col_ts, col_mv = st.columns(3)
        with col_hw:
            render_heatwave_risk_card(ew.get("heatwave_risk") or {})
        with col_ts:
            render_thermal_stress_card(
                ew.get("thermal_stress"),
                error=ew.get("thermal_stress_error"),
            )
        with col_mv:
            render_mortality_card(
                ew.get("mortality_vulnerability"),
                demographics=ew.get("demographics"),
                error=ew.get("mortality_vulnerability_error"),
            )
            
        st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)
        
        # -----------------------------------------------------------------------
        # AI Forecast (single area)
        # -----------------------------------------------------------------------
        section_title("AI Forecast", "🤖")
        render_ml_prediction_card(ew.get("ml_prediction"))

    st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Forecast Outlook (Vertical List)
    # -----------------------------------------------------------------------
    section_title("Forecast Outlook", "📅")
    forecasts = (wf_data or {}).get("forecasts", [])
    if not forecasts:
        st.markdown(
            '<div style="color:#64748b;font-size:0.85rem">'
            'No stored forecast available for this area.</div>',
            unsafe_allow_html=True,
        )
    else:
        # We will show a vertical list of the next 7 days (or 5 days) daily summary
        # Group by day
        from collections import defaultdict
        daily_fcs = defaultdict(list)
        for f in forecasts:
            dt_str = str(f.get("timestamp", ""))[:10]
            if dt_str: daily_fcs[dt_str].append(f)
            
        list_html = '<div class="glass-card" style="padding:0;overflow:hidden"><table style="width:100%;border-collapse:collapse">'
        for day, fcs in list(daily_fcs.items())[:7]:
            # Aggregate daily
            high_temp = max([fc.get("temperature", 0) for fc in fcs if fc.get("temperature") is not None] + [-999])
            if high_temp == -999: high_temp = None
            total_precip = sum([fc.get("precipitation", 0) for fc in fcs if fc.get("precipitation") is not None])
            
            day_str = day
            temp_str = _fmt(high_temp, "°")
            precip_str = f"{total_precip:.1f} mm" if total_precip > 0 else "—"
            
            list_html += f'''
            <tr style="border-bottom:1px solid rgba(255,255,255,0.03);">
                <td style="padding:1rem;color:#cbd5e1;font-weight:500;">{day_str}</td>
                <td style="padding:1rem;color:#f8fafc;font-weight:600;">{temp_str}</td>
                <td style="padding:1rem;color:#06b6d4;">{precip_str}</td>
                <td style="padding:1rem;color:#64748b;text-align:right;">Forecast Active</td>
            </tr>
            '''
        list_html += '</table></div>'
        st.markdown(list_html, unsafe_allow_html=True)

    st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # AREA RISK OVERVIEW (multi-area table) - MOVED HERE
    # -----------------------------------------------------------------------
    section_title("Area Risk Overview", "🌐")
    st.markdown(
        '<div style="font-size:0.78rem;color:#64748b;margin-bottom:0.6rem">'
        'Real-time status for all monitored areas.'
        '</div>',
        unsafe_allow_html=True,
    )
    _render_area_overview(areas, early_warnings)

    st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # GIS Risk Map
    # -----------------------------------------------------------------------
    section_title("GIS Risk Map", "🗺️")
    render_map(areas, early_warnings, height=450)

    st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Demographic Vulnerability
    # -----------------------------------------------------------------------
    section_title("Demographic Vulnerability", "👥")
    demo = ew.get("demographics") if ew else None

    if demo:
        pop = demo.get("population_total")
        elderly = demo.get("pct_elderly")
        children = demo.get("pct_children")
        notes = demo.get("vulnerability_notes", "")

        d_kpis = [
            {
                "icon": "👨‍👩‍👧‍👦",
                "label": "Population Total",
                "value": f"{int(pop):,}" if pop is not None else "Not recorded",
            },
            {
                "icon": "🧓",
                "label": "Elderly (≥65)",
                "value": _fmt(elderly, "%", 1, "Not recorded"),
            },
            {
                "icon": "👶",
                "label": "Children (<18)",
                "value": _fmt(children, "%", 1, "Not recorded"),
            },
        ]
        render_kpi_row(d_kpis)
        if notes:
            st.markdown(
                f'<div style="font-size:0.82rem;color:#94a3b8;margin-top:0.8rem;padding:0.75rem;'
                f'background:rgba(255,255,255,0.02);border-radius:8px;border:1px solid rgba(255,255,255,0.05)">'
                f'<b>Notes:</b> {notes}</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            """
            <div style="padding:1rem;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);
            border-radius:10px;font-size:0.85rem;color:#64748b;">
              No demographic data available for this area.
              Add a demographic profile to enable mortality risk assessment.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div style="height:1.5rem"></div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Active Early Warnings
    # -----------------------------------------------------------------------
    section_title("Active Early Warnings", "🚨")
    active_alerts = [a for a in (alerts or []) if a.get("active", True)]

    if active_alerts:
        for alert in active_alerts:
            _render_alert(alert)
    else:
        st.markdown(
            """
            <div style="padding:1rem;background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.15);
            border-radius:10px;font-size:0.85rem;color:#10b981;">
              ✅ No active heatwave alerts for this area.
            </div>
            """,
            unsafe_allow_html=True,
        )
