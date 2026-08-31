"""
alerts.py – Alert Center page for SIH26083.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

import api.backend_client as client
from components.metrics import section_title, empty_state, render_badge, risk_color


@st.cache_data(ttl=30)
def _fetch_alerts(area_id=None, active_only=False):
    return client.get_alerts(area_id=area_id, active_only=active_only)


@st.cache_data(ttl=60)
def _fetch_areas():
    return client.get_areas()


def _alert_card(alert: dict) -> str:
    """Return HTML for an alert card."""
    level = alert.get("level", "WATCH")
    risk_level = alert.get("risk_level", "")
    score = alert.get("risk_score")
    message = alert.get("message", "")
    ts = alert.get("timestamp", "")
    raised = alert.get("raised_at_utc", "")
    active = alert.get("active", True)
    factors = alert.get("factors", [])
    source = alert.get("source", "rule").upper()
    area_id = alert.get("area_id", "—")

    cls_map = {
        "WARNING": "alert-warning",
        "WATCH": "alert-watch",
        "INFORMATIONAL": "alert-info",
    }
    cls = cls_map.get(level, "alert-watch")

    status_html = (
        '<span style="color:#10b981;font-size:0.75rem;font-weight:600">● ACTIVE</span>'
        if active
        else '<span style="color:#64748b;font-size:0.75rem">● RESOLVED</span>'
    )

    factors_html = ""
    if factors:
        factors_html = (
            '<div style="margin-top:0.4rem"><ul style="margin:0;padding-left:1.2rem">'
            + "".join(f'<li style="font-size:0.78rem;color:#94a3b8">{f}</li>' for f in factors)
            + "</ul></div>"
        )

    score_str = f"{float(score):.1f}" if score is not None else "—"

    return f"""
    <div class="alert-card {cls}" style="margin-bottom:0.85rem">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.4rem;margin-bottom:0.4rem">
        <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap">
          {render_badge(level)}
          <span style="font-size:0.82rem;color:#94a3b8">Area {area_id}</span>
          <span style="font-size:0.78rem;color:#64748b;background:rgba(255,255,255,0.05);padding:0.15em 0.5em;border-radius:4px">{source}</span>
        </div>
        {status_html}
      </div>
      <div style="font-size:0.88rem;color:#e2e8f0;margin-bottom:0.3rem">{message}</div>
      <div style="display:flex;gap:1rem;flex-wrap:wrap;font-size:0.78rem;color:#64748b">
        <span>Risk Level: <b style="color:#94a3b8">{risk_level}</b></span>
        <span>Score: <b style="color:#94a3b8">{score_str}</b></span>
        <span>Event: {ts}</span>
        <span>Raised: {raised}</span>
      </div>
      {factors_html}
    </div>
    """


def render(backend_online: bool) -> None:
    """Render the Alert Center page."""
    if not backend_online:
        empty_state("🔌", "Backend Unavailable", "Start the backend service and refresh.")
        return

    # -----------------------------------------------------------------------
    # Filter controls
    # -----------------------------------------------------------------------
    areas, _ = _fetch_areas()
    area_filter_options = {"All Areas": None}
    if areas:
        for a in areas:
            area_filter_options[a["name"]] = a["id"]

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        selected_area_name = st.selectbox(
            "Filter by Area",
            options=list(area_filter_options.keys()),
            key="alert_area_filter",
        )
    with col2:
        active_only = st.toggle("Active Only", value=False, key="alert_active_only")
    with col3:
        if st.button("🔄 Refresh", key="alerts_refresh"):
            st.cache_data.clear()
            st.rerun()

    selected_area_id = area_filter_options[selected_area_name]

    # -----------------------------------------------------------------------
    # Fetch alerts
    # -----------------------------------------------------------------------
    alerts, err = _fetch_alerts(area_id=selected_area_id, active_only=active_only)

    if err:
        st.error(f"Could not load alerts: {err}")
        return

    if not alerts:
        empty_state(
            "✅",
            "No Alerts",
            "No alerts match the current filters. The system is monitoring all registered areas.",
        )
        return

    # -----------------------------------------------------------------------
    # Summary bar
    # -----------------------------------------------------------------------
    warning_count = sum(1 for a in alerts if a.get("level") == "WARNING")
    watch_count = sum(1 for a in alerts if a.get("level") == "WATCH")
    info_count = sum(1 for a in alerts if a.get("level") == "INFORMATIONAL")
    active_count = sum(1 for a in alerts if a.get("active", True))

    st.markdown(
        f"""
        <div style="display:flex;gap:0.75rem;flex-wrap:wrap;margin-bottom:1.2rem">
          <div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.25);border-radius:8px;padding:0.6rem 1rem;min-width:90px;text-align:center">
            <div style="font-size:1.5rem;font-weight:700;color:#ef4444">{warning_count}</div>
            <div style="font-size:0.72rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em">Warning</div>
          </div>
          <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.25);border-radius:8px;padding:0.6rem 1rem;min-width:90px;text-align:center">
            <div style="font-size:1.5rem;font-weight:700;color:#f59e0b">{watch_count}</div>
            <div style="font-size:0.72rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em">Watch</div>
          </div>
          <div style="background:rgba(6,182,212,0.1);border:1px solid rgba(6,182,212,0.2);border-radius:8px;padding:0.6rem 1rem;min-width:90px;text-align:center">
            <div style="font-size:1.5rem;font-weight:700;color:#06b6d4">{info_count}</div>
            <div style="font-size:0.72rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em">Informational</div>
          </div>
          <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2);border-radius:8px;padding:0.6rem 1rem;min-width:90px;text-align:center">
            <div style="font-size:1.5rem;font-weight:700;color:#10b981">{active_count}</div>
            <div style="font-size:0.72rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em">Active</div>
          </div>
          <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:0.6rem 1rem;min-width:90px;text-align:center">
            <div style="font-size:1.5rem;font-weight:700;color:#f0f6ff">{len(alerts)}</div>
            <div style="font-size:0.72rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.08em">Total</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # Sort: WARNING first, then WATCH, then INFORMATIONAL
    # -----------------------------------------------------------------------
    level_order = {"WARNING": 0, "WATCH": 1, "INFORMATIONAL": 2}
    sorted_alerts = sorted(alerts, key=lambda a: level_order.get(a.get("level", "WATCH"), 9))

    # -----------------------------------------------------------------------
    # Critical alerts section first
    # -----------------------------------------------------------------------
    critical = [a for a in sorted_alerts if a.get("level") == "WARNING"]
    rest = [a for a in sorted_alerts if a.get("level") != "WARNING"]

    if critical:
        section_title("⚠️  Warning Alerts", "🔴")
        for a in critical:
            st.markdown(_alert_card(a), unsafe_allow_html=True)

    if rest:
        section_title("Watch / Informational Alerts", "🟡")
        for a in rest:
            st.markdown(_alert_card(a), unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Intervention Framework (static, clearly labelled)
    # -----------------------------------------------------------------------
    st.markdown('<div style="height:1rem"></div>', unsafe_allow_html=True)
    with st.expander("📋 Standard Intervention Framework (SIH26083 Reference)", expanded=False):
        st.markdown(
            """
            <div style="background:rgba(255,255,255,0.02);border-radius:8px;padding:1rem">
              <div style="font-size:0.72rem;color:#f59e0b;text-transform:uppercase;letter-spacing:0.12em;font-weight:600;margin-bottom:0.75rem">
                ⚠️ Static Reference Framework — Not derived from live data
              </div>

              <table style="width:100%;border-collapse:collapse;font-size:0.83rem">
                <thead>
                  <tr style="border-bottom:1px solid rgba(255,255,255,0.08)">
                    <th style="padding:0.5rem;text-align:left;color:#64748b;font-size:0.72rem;text-transform:uppercase">Level</th>
                    <th style="padding:0.5rem;text-align:left;color:#64748b;font-size:0.72rem;text-transform:uppercase">Status</th>
                    <th style="padding:0.5rem;text-align:left;color:#64748b;font-size:0.72rem;text-transform:uppercase">Recommended Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
                    <td style="padding:0.5rem;color:#10b981;font-weight:700">INFORMATIONAL</td>
                    <td style="padding:0.5rem;color:#94a3b8">WATCH</td>
                    <td style="padding:0.5rem;color:#94a3b8">Issue public advisories; alert health workers; monitor vulnerable populations</td>
                  </tr>
                  <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
                    <td style="padding:0.5rem;color:#f59e0b;font-weight:700">WATCH</td>
                    <td style="padding:0.5rem;color:#94a3b8">WARNING</td>
                    <td style="padding:0.5rem;color:#94a3b8">Open cooling centers; deploy medical teams; school/outdoor work restrictions</td>
                  </tr>
                  <tr>
                    <td style="padding:0.5rem;color:#ef4444;font-weight:700">WARNING</td>
                    <td style="padding:0.5rem;color:#94a3b8">CRITICAL</td>
                    <td style="padding:0.5rem;color:#94a3b8">Emergency response activation; mandatory shelter orders; priority medical deployment</td>
                  </tr>
                </tbody>
              </table>
            </div>
            """,
            unsafe_allow_html=True,
        )
