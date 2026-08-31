"""
area_intelligence.py – Area Intelligence page for SIH26083.
"""
from __future__ import annotations

import streamlit as st

import api.backend_client as client
from components.metrics import section_title, empty_state, render_badge, risk_color
from components.risk_cards import (
    render_heatwave_risk_card,
    render_thermal_stress_card,
    render_mortality_card,
    render_weather_card,
)
from components.charts import factors_chart, plot_chart


@st.cache_data(ttl=60)
def _fetch_areas():
    return client.get_areas()


@st.cache_data(ttl=30)
def _fetch_early_warning(area_id: int):
    return client.get_early_warning(area_id)


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


def render(backend_online: bool) -> None:
    """Render the Area Intelligence page."""

    if not backend_online:
        empty_state(
            "🔌",
            "Backend Unavailable",
            "The SIH26083 intelligence service is not reachable. Start the backend and refresh.",
        )
        return

    # Fetch areas
    areas, err = _fetch_areas()
    if err or not areas:
        empty_state(
            "🗂️",
            "No Areas Available",
            err or "No monitored areas found. Register an area via the backend API first.",
        )
        return

    # Area selector
    area_options = {a["name"]: a["id"] for a in areas}
    selected_name = st.selectbox(
        "Select Monitored Area",
        options=list(area_options.keys()),
        key="area_intel_select",
    )
    selected_id = area_options[selected_name]

    # Fetch early-warning data
    with st.spinner("Fetching intelligence data…"):
        ew, ew_err = _fetch_early_warning(selected_id)

    if ew_err or ew is None:
        empty_state(
            "📡",
            "Data Unavailable",
            ew_err or "Early-warning data unavailable for this area. Ingest weather data first.",
        )
        return

    # -----------------------------------------------------------------------
    # Overall Status Banner
    # -----------------------------------------------------------------------
    overall = ew.get("overall_status", "NORMAL")
    highest = ew.get("highest_risk_level", "LOW")
    has_alerts = ew.get("has_active_alerts", False)
    color = risk_color(overall)

    area_meta = ew.get("area") or {}
    lat = area_meta.get("latitude", "")
    lon = area_meta.get("longitude", "")

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,rgba(255,255,255,0.04),rgba(255,255,255,0.02));
        border:1px solid rgba(255,255,255,0.08);border-left:4px solid {color};
        border-radius:12px;padding:1.2rem 1.5rem;margin-bottom:1.2rem">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:0.75rem">
            <div>
              <div style="font-size:1.25rem;font-weight:700;color:#f0f6ff;margin-bottom:0.25rem">
                {selected_name}
              </div>
              <div style="font-size:0.8rem;color:#64748b">
                {lat:.4f}°N, {lon:.4f}°E &nbsp;·&nbsp; Area ID: {ew.get('area_id')}
              </div>
            </div>
            <div style="text-align:right">
              <div style="font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.3rem">Overall Status</div>
              <div style="font-size:1.6rem;font-weight:800;color:{color}">{overall}</div>
              {'<div style="font-size:0.78rem;color:#f59e0b;margin-top:0.2rem">⚡ Active Alerts</div>' if has_alerts else ''}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # Environmental + Risk Cards
    # -----------------------------------------------------------------------
    col1, col2 = st.columns([1, 2])

    with col1:
        weather = ew.get("weather") or {}
        render_weather_card(weather)

    with col2:
        render_heatwave_risk_card(ew.get("heatwave_risk") or {})

    st.markdown('<div style="height:0.75rem"></div>', unsafe_allow_html=True)

    col3, col4 = st.columns(2)
    with col3:
        render_thermal_stress_card(
            ew.get("thermal_stress"),
            error=ew.get("thermal_stress_error"),
        )
    with col4:
        render_mortality_card(
            ew.get("mortality_vulnerability"),
            demographics=ew.get("demographics"),
            error=ew.get("mortality_vulnerability_error"),
        )

    # -----------------------------------------------------------------------
    # Contributing Factors Chart
    # -----------------------------------------------------------------------
    hw = ew.get("heatwave_risk") or {}
    hw_factors = hw.get("contributing_factors", [])
    if hw_factors:
        st.markdown('<div style="height:0.75rem"></div>', unsafe_allow_html=True)
        section_title("Heatwave Risk – Detailed Factors", "🔬")
        fig = factors_chart(hw_factors, title="Heatwave Risk Contributing Factors", height=max(200, 40 * len(hw_factors)))
        plot_chart(fig)

    ts = ew.get("thermal_stress") or {}
    ts_factors = ts.get("contributing_factors", [])
    if ts_factors:
        st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)
        section_title("Thermal Stress – Detailed Factors", "🌡️")
        fig2 = factors_chart(ts_factors, title="Thermal Stress Contributing Factors", height=max(200, 40 * len(ts_factors)))
        plot_chart(fig2)

    # -----------------------------------------------------------------------
    # Active Alerts
    # -----------------------------------------------------------------------
    alerts = ew.get("alerts", [])
    if alerts:
        st.markdown('<div style="height:0.75rem"></div>', unsafe_allow_html=True)
        section_title("Active Alerts for This Area", "🚨")
        for alert in alerts:
            _render_alert(alert)
    else:
        st.markdown(
            """
            <div style="padding:1rem;background:rgba(16,185,129,0.06);border:1px solid rgba(16,185,129,0.15);
            border-radius:10px;font-size:0.85rem;color:#10b981;margin-top:1rem">
              ✅ No active alerts for this area.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -----------------------------------------------------------------------
    # Demographics
    # -----------------------------------------------------------------------
    demo = ew.get("demographics")
    if demo:
        st.markdown('<div style="height:0.75rem"></div>', unsafe_allow_html=True)
        section_title("Demographic Profile", "👥")

        pop = demo.get("population_total")
        elderly = demo.get("pct_elderly")
        children = demo.get("pct_children")
        notes = demo.get("vulnerability_notes", "")

        demo_cols = st.columns(4)
        with demo_cols[0]:
            st.metric("Population", f"{int(pop):,}" if pop else "N/A")
        with demo_cols[1]:
            st.metric("Elderly (≥65)", f"{elderly:.1f}%" if elderly is not None else "N/A")
        with demo_cols[2]:
            st.metric("Children (<18)", f"{children:.1f}%" if children is not None else "N/A")
        with demo_cols[3]:
            st.metric("Vulnerability Notes", notes[:30] + "…" if notes and len(notes) > 30 else (notes or "—"))
