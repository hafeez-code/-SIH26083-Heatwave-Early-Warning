"""
forecast.py – Forecast Intelligence page for SIH26083.
"""
from __future__ import annotations

import streamlit as st

import api.backend_client as client
from components.metrics import section_title, empty_state, render_badge, risk_color
from components.charts import (
    forecast_temperature_chart,
    forecast_humidity_chart,
    forecast_wind_chart,
    forecast_precipitation_chart,
    risk_trajectory_chart,
    plot_chart,
)


@st.cache_data(ttl=60)
def _fetch_areas():
    return client.get_areas()


@st.cache_data(ttl=120)
def _fetch_weather_forecast(area_id: int, stored: bool = True):
    return client.get_weather_forecast(area_id, stored=stored)


@st.cache_data(ttl=120)
def _fetch_risk_forecast(area_id: int):
    return client.get_risk_forecast(area_id)


def _trajectory_html(deterministic_risks: list[dict]) -> None:
    """Display the early-warning trajectory."""
    if not deterministic_risks:
        return

    _rank = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "VERY HIGH": 3, "EXTREME": 4}
    levels_in_order = [r.get("risk_level", "LOW") for r in deterministic_risks]

    # Collect unique transition levels in order of appearance
    seen = []
    for lv in levels_in_order:
        if not seen or seen[-1] != lv:
            seen.append(lv)

    _label_map = {
        "LOW": ("NORMAL", "#10b981"),
        "MODERATE": ("WATCH", "#f59e0b"),
        "HIGH": ("WARNING", "#f97316"),
        "VERY HIGH": ("CRITICAL", "#ef4444"),
        "EXTREME": ("CRITICAL", "#ef4444"),
    }

    steps_html = ""
    for i, lv in enumerate(seen):
        label, color = _label_map.get(lv, (lv, "#94a3b8"))
        arrow = ' <span style="color:#06b6d4;margin:0 0.3rem">→</span> ' if i < len(seen) - 1 else ""
        steps_html += f'<span style="color:{color};font-weight:700;font-size:0.95rem">{label}</span>{arrow}'

    st.markdown(
        f"""
        <div class="glass-card" style="margin-bottom:1rem">
          <div style="font-size:0.72rem;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.12em;margin-bottom:0.6rem">
            📈 Early Warning Trajectory
          </div>
          <div style="display:flex;align-items:center;flex-wrap:wrap;gap:0.3rem">
            {steps_html}
          </div>
          <div style="font-size:0.75rem;color:#475569;margin-top:0.5rem">
            Based on {len(deterministic_risks)} deterministic forecast evaluations
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render(backend_online: bool) -> None:
    """Render the Forecast Intelligence page."""
    if not backend_online:
        empty_state("🔌", "Backend Unavailable", "Start the backend service and refresh.")
        return

    areas, err = _fetch_areas()
    if err or not areas:
        empty_state("🗂️", "No Areas Available", err or "No monitored areas found.")
        return

    area_options = {a["name"]: a["id"] for a in areas}
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        selected_name = st.selectbox(
            "Select Area for Forecast",
            options=list(area_options.keys()),
            key="forecast_area_select",
        )
    with col_btn:
        live_mode = st.toggle("Live Fetch", value=False, key="forecast_live", help="Fetch live forecast from weather provider (uses API quota)")

    selected_id = area_options[selected_name]

    # Fetch forecast data
    with st.spinner("Loading forecast data…"):
        wf_data, wf_err = _fetch_weather_forecast(selected_id, stored=not live_mode)
        rf_data, rf_err = _fetch_risk_forecast(selected_id)

    forecasts: list[dict] = []
    if wf_data:
        forecasts = wf_data.get("forecasts", [])

    deterministic_risks: list[dict] = []
    ml_predictions: list[dict] = []
    forecast_alerts: list[dict] = []
    if rf_data:
        deterministic_risks = rf_data.get("deterministic_risks", [])
        ml_predictions = rf_data.get("ml_predictions", [])
        forecast_alerts = rf_data.get("alerts", [])

    # -----------------------------------------------------------------------
    # No data state
    # -----------------------------------------------------------------------
    if not forecasts and not deterministic_risks:
        msg_parts = []
        if wf_err:
            msg_parts.append(f"Weather forecast: {wf_err}")
        if rf_err:
            msg_parts.append(f"Risk forecast: {rf_err}")
        empty_state(
            "📡",
            "No Forecast Data Available",
            (
                " | ".join(msg_parts)
                or "No stored forecast available. Fetch live data using the toggle above, "
                   "or run the weather scheduler to populate forecast observations."
            ),
        )
        return

    # -----------------------------------------------------------------------
    # Trajectory
    # -----------------------------------------------------------------------
    section_title("Early Warning Trajectory", "📈")
    _trajectory_html(deterministic_risks)

    # -----------------------------------------------------------------------
    # Weather charts
    # -----------------------------------------------------------------------
    if forecasts:
        section_title("Weather Forecast", "🌤️")

        fig_temp = forecast_temperature_chart(forecasts, height=270)
        plot_chart(fig_temp)

        c1, c2 = st.columns(2)
        with c1:
            plot_chart(forecast_humidity_chart(forecasts, height=230))
        with c2:
            plot_chart(forecast_wind_chart(forecasts, height=230))

        fig_precip = forecast_precipitation_chart(forecasts)
        if fig_precip:
            plot_chart(fig_precip)
    else:
        st.markdown(
            f'<div style="color:#64748b;font-size:0.85rem;padding:0.5rem 0">{wf_err or "Weather forecast not available."}</div>',
            unsafe_allow_html=True,
        )

    # -----------------------------------------------------------------------
    # Risk forecast charts
    # -----------------------------------------------------------------------
    if deterministic_risks:
        section_title("Risk Forecast", "🚦")
        plot_chart(risk_trajectory_chart(deterministic_risks, height=280))

        # Summary table
        st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)
        rows_html = ""
        for r in deterministic_risks[:12]:
            lv = r.get("risk_level", "—")
            score = r.get("risk_score")
            ts = r.get("timestamp", "—")
            factors = r.get("contributing_factors", [])
            color = risk_color(lv)
            rows_html += f"""
            <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
              <td style="padding:0.5rem 0.75rem;font-size:0.8rem;color:#94a3b8">{ts}</td>
              <td style="padding:0.5rem 0.75rem">{render_badge(lv)}</td>
              <td style="padding:0.5rem 0.75rem;color:{color};font-weight:600;font-size:0.85rem">{f'{float(score):.1f}' if score is not None else '—'}</td>
              <td style="padding:0.5rem 0.75rem;font-size:0.79rem;color:#64748b">{', '.join(str(f) for f in (factors or [])[:2])}</td>
            </tr>
            """

        st.markdown(
            f"""
            <div class="glass-card" style="padding:0;overflow:hidden">
              <table style="width:100%;border-collapse:collapse">
                <thead>
                  <tr style="border-bottom:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03)">
                    <th style="padding:0.55rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Timestamp</th>
                    <th style="padding:0.55rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Level</th>
                    <th style="padding:0.55rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Score</th>
                    <th style="padding:0.55rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Key Factors</th>
                  </tr>
                </thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -----------------------------------------------------------------------
    # ML Predictions
    # -----------------------------------------------------------------------
    if ml_predictions:
        section_title("ML Heatwave Probability", "🤖")
        st.markdown(
            '<div style="font-size:0.8rem;color:#64748b;margin-bottom:0.5rem">'
            'Prototype ML heatwave-event classifier (v0.16) — forecast-pattern classification. '
            '<span style="color:#f59e0b;font-weight:600">'
            '⚠️ Not an official warning, medical prediction, or production-validated model.'
            '</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        rows_html = ""
        for p in ml_predictions[:12]:
            ts = p.get("forecast_timestamp", "—")
            prob = p.get("probability")
            pred = p.get("prediction")
            task = p.get("task", "—")

            prob_pct = f"{float(prob)*100:.1f}%" if prob is not None else "—"
            prob_color = "#ef4444" if prob and float(prob) >= 0.80 else ("#f59e0b" if prob and float(prob) >= 0.55 else "#10b981")

            rows_html += f"""
            <tr style="border-bottom:1px solid rgba(255,255,255,0.04)">
              <td style="padding:0.5rem 0.75rem;font-size:0.8rem;color:#94a3b8">{ts}</td>
              <td style="padding:0.5rem 0.75rem;font-size:0.85rem;color:{prob_color};font-weight:600">{prob_pct}</td>
              <td style="padding:0.5rem 0.75rem;font-size:0.82rem;color:#94a3b8">{pred if pred is not None else '—'}</td>
              <td style="padding:0.5rem 0.75rem;font-size:0.78rem;color:#64748b">{task}</td>
            </tr>
            """

        st.markdown(
            f"""
            <div class="glass-card" style="padding:0;overflow:hidden">
              <table style="width:100%;border-collapse:collapse">
                <thead>
                  <tr style="border-bottom:1px solid rgba(255,255,255,0.08);background:rgba(255,255,255,0.03)">
                    <th style="padding:0.55rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Forecast Time</th>
                    <th style="padding:0.55rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Probability</th>
                    <th style="padding:0.55rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Prediction</th>
                    <th style="padding:0.55rem 0.75rem;text-align:left;font-size:0.7rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Task</th>
                  </tr>
                </thead>
                <tbody>{rows_html}</tbody>
              </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -----------------------------------------------------------------------
    # Forecast alerts
    # -----------------------------------------------------------------------
    if forecast_alerts:
        section_title("Forecast Alerts", "⚡")
        for a in forecast_alerts:
            level = a.get("level", "WATCH")
            cls = "alert-warning" if level == "WARNING" else "alert-watch"
            st.markdown(
                f"""
                <div class="alert-card {cls}">
                  <span style="font-weight:600">{render_badge(level)}</span>
                  <span style="font-size:0.84rem;color:#cbd5e1;margin-left:0.5rem">{a.get('message','')}</span>
                  <div style="font-size:0.74rem;color:#475569;margin-top:0.3rem">{a.get('timestamp','')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
