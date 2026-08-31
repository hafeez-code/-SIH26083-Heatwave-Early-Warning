"""
risk_cards.py – Risk assessment card components for SIH26083.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from components.metrics import render_badge, risk_color, section_title


def _fmt(val, suffix="", decimals=1, na="N/A"):
    if val is None:
        return na
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return na


def _factors_html(factors) -> str:
    """Render contributing factors as bullet list HTML."""
    if not factors:
        return '<span style="color:#64748b;font-size:0.8rem">No factors available</span>'
    items = "".join(
        f'<li style="color:#94a3b8;font-size:0.82rem;margin-bottom:3px">{f}</li>'
        for f in (factors if isinstance(factors, list) else [factors])
    )
    return f'<ul style="margin:0.3rem 0 0 0;padding-left:1.2rem">{items}</ul>'


def render_heatwave_risk_card(heatwave_risk: dict) -> None:
    """Render heatwave risk card."""
    level = heatwave_risk.get("level", "—")
    score = heatwave_risk.get("score")
    factors = heatwave_risk.get("contributing_factors", [])
    color = risk_color(level)

    st.markdown(
        f"""
        <div class="glass-card" style="border-left:3px solid {color}">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">
            <div style="font-size:0.78rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em">
              🌊 Heatwave Risk
            </div>
            {render_badge(level)}
          </div>
          <div style="display:flex;align-items:baseline;gap:0.5rem;margin-bottom:0.6rem">
            <span style="font-size:2rem;font-weight:700;color:{color}">{_fmt(score, "", 1)}</span>
            <span style="font-size:0.8rem;color:#64748b">/ 100</span>
          </div>
          <div style="font-size:0.75rem;color:#64748b;font-weight:500;margin-bottom:0.3rem;text-transform:uppercase;letter-spacing:0.08em">
            Contributing Factors
          </div>
          {_factors_html(factors)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_thermal_stress_card(thermal_stress: Optional[dict], error: Optional[str] = None) -> None:
    """Render Human Thermal Stress card."""
    if error:
        st.markdown(
            f"""
            <div class="glass-card" style="border-left:3px solid #64748b">
              <div style="font-size:0.78rem;font-weight:600;color:#94a3b8;margin-bottom:0.5rem;text-transform:uppercase;letter-spacing:0.1em">
                🌡️ Human Thermal Stress
              </div>
              <div style="color:#64748b;font-size:0.85rem">Unavailable: {error}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if not thermal_stress:
        st.markdown(
            """
            <div class="glass-card" style="border-left:3px solid #64748b">
              <div style="font-size:0.78rem;font-weight:600;color:#94a3b8;margin-bottom:0.5rem;text-transform:uppercase;letter-spacing:0.1em">
                🌡️ Human Thermal Stress
              </div>
              <div style="color:#64748b;font-size:0.85rem">No thermal stress data available.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    level = thermal_stress.get("level", "—")
    score = thermal_stress.get("score")
    hi = thermal_stress.get("heat_index_celsius")
    factors = thermal_stress.get("contributing_factors", [])
    methodology = thermal_stress.get("methodology_note", "")
    color = risk_color(level)

    st.markdown(
        f"""
        <div class="glass-card" style="border-left:3px solid {color}">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">
            <div style="font-size:0.78rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em">
              🌡️ Human Thermal Stress Index
            </div>
            {render_badge(level)}
          </div>
          <div style="display:flex;gap:1.5rem;margin-bottom:0.6rem;flex-wrap:wrap">
            <div>
              <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Stress Score</div>
              <div style="font-size:1.7rem;font-weight:700;color:{color}">{_fmt(score, "", 1)}</div>
            </div>
            <div>
              <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Heat Index</div>
              <div style="font-size:1.7rem;font-weight:700;color:#f97316">{_fmt(hi, "°C")}</div>
            </div>
          </div>
          <div style="font-size:0.75rem;color:#64748b;font-weight:500;margin-bottom:0.3rem;text-transform:uppercase;letter-spacing:0.08em">
            Contributing Factors
          </div>
          {_factors_html(factors)}
          {f'<div style="margin-top:0.6rem;font-size:0.73rem;color:#475569;border-top:1px solid rgba(255,255,255,0.06);padding-top:0.5rem">{methodology}</div>' if methodology else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_mortality_card(
    mortality: Optional[dict],
    demographics: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """Render Mortality/Vulnerability Risk card."""
    if error:
        st.markdown(
            f"""
            <div class="glass-card" style="border-left:3px solid #64748b">
              <div style="font-size:0.78rem;font-weight:600;color:#94a3b8;margin-bottom:0.5rem;text-transform:uppercase;letter-spacing:0.1em">
                ⚠️ Mortality Risk
              </div>
              <div style="color:#64748b;font-size:0.85rem">Unavailable: {error}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if not mortality:
        st.markdown(
            """
            <div class="glass-card" style="border-left:3px solid #64748b">
              <div style="font-size:0.78rem;font-weight:600;color:#94a3b8;margin-bottom:0.5rem;text-transform:uppercase;letter-spacing:0.1em">
                ⚠️ Mortality Risk
              </div>
              <div style="color:#64748b;font-size:0.85rem">
                No demographic data available. Add demographic profile to enable mortality risk assessment.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    level = mortality.get("level", "—")
    score = mortality.get("score")
    vuln = mortality.get("vulnerability_factor")
    factors = mortality.get("contributing_factors", [])
    methodology = mortality.get("methodology_note", "")
    color = risk_color(level)

    demo_html = ""
    if demographics:
        pop = demographics.get("population_total")
        elderly = demographics.get("pct_elderly")
        children = demographics.get("pct_children")
        notes = demographics.get("vulnerability_notes", "")
        parts = []
        if pop is not None:
            parts.append(f"Population: <b>{int(pop):,}</b>")
        if elderly is not None:
            parts.append(f"Elderly (≥65): <b>{elderly:.1f}%</b>")
        if children is not None:
            parts.append(f"Children: <b>{children:.1f}%</b>")
        if notes:
            parts.append(f"Notes: <em>{notes}</em>")
        if parts:
            demo_html = (
                '<div style="margin-top:0.6rem;font-size:0.79rem;color:#94a3b8;'
                'border-top:1px solid rgba(255,255,255,0.06);padding-top:0.5rem">'
                + " &nbsp;·&nbsp; ".join(parts) + "</div>"
            )

    st.markdown(
        f"""
        <div class="glass-card" style="border-left:3px solid {color}">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem">
            <div style="font-size:0.78rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em">
              ⚠️ Mortality / Vulnerability Risk
            </div>
            {render_badge(level)}
          </div>
          <div style="display:flex;gap:1.5rem;margin-bottom:0.6rem;flex-wrap:wrap">
            <div>
              <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Risk Score</div>
              <div style="font-size:1.7rem;font-weight:700;color:{color}">{_fmt(score, "", 1)}</div>
            </div>
            <div>
              <div style="font-size:0.68rem;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Vulnerability Factor</div>
              <div style="font-size:1.7rem;font-weight:700;color:#f97316">{_fmt(vuln, "×", 2)}</div>
            </div>
          </div>
          <div style="font-size:0.75rem;color:#64748b;font-weight:500;margin-bottom:0.3rem;text-transform:uppercase;letter-spacing:0.08em">
            Contributing Factors
          </div>
          {_factors_html(factors)}
          {f'<div style="margin-top:0.6rem;font-size:0.73rem;color:#475569;border-top:1px solid rgba(255,255,255,0.06);padding-top:0.5rem">{methodology}</div>' if methodology else ''}
          {demo_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_weather_card(weather: dict) -> None:
    """Render environmental conditions summary card."""
    temp = weather.get("temperature")
    humidity = weather.get("humidity")
    wind = weather.get("wind_speed")
    precip = weather.get("precipitation")
    solar = weather.get("solar_radiation")
    ts = weather.get("timestamp", "")

    def _row(label, val):
        return (
            f'<div style="display:flex;justify-content:space-between;padding:0.35rem 0;'
            f'border-bottom:1px solid rgba(255,255,255,0.05)">'
            f'<span style="color:#64748b;font-size:0.82rem">{label}</span>'
            f'<span style="color:#f0f6ff;font-weight:500;font-size:0.82rem">{val}</span>'
            f'</div>'
        )

    rows = [
        _row("🌡️ Temperature", _fmt(temp, " °C")),
        _row("💧 Relative Humidity", _fmt(humidity, "%", 0)),
        _row("💨 Wind Speed", _fmt(wind, " km/h")),
        _row("🌧️ Precipitation", _fmt(precip, " mm")),
    ]
    if solar is not None:
        rows.append(_row("☀️ Solar Radiation", _fmt(solar, " W/m²")))

    ts_html = ""
    if ts:
        ts_html = f'<div style="font-size:0.72rem;color:#475569;margin-top:0.5rem">Observation: {ts}</div>'

    st.markdown(
        f"""
        <div class="glass-card">
          <div style="font-size:0.78rem;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.75rem">
            🌤️ Environmental Conditions
          </div>
          {''.join(rows)}
          {ts_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
