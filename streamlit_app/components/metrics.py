"""
metrics.py – KPI metric card components.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st


# ---------------------------------------------------------------------------
# Risk level helpers
# ---------------------------------------------------------------------------

def risk_color(level: Optional[str]) -> str:
    """CSS variable name for a given risk/status level string."""
    if not level:
        return "#94a3b8"
    l = level.upper()
    if l in ("CRITICAL", "EXTREME", "VERY HIGH"):
        return "#ef4444"
    if l in ("WARNING", "HIGH"):
        return "#f97316"
    if l in ("WATCH", "MODERATE"):
        return "#f59e0b"
    if l in ("NORMAL", "LOW"):
        return "#10b981"
    return "#94a3b8"


def risk_badge_class(level: Optional[str]) -> str:
    if not level:
        return "badge-normal"
    l = level.upper()
    if l in ("CRITICAL", "EXTREME"):
        return "badge-critical"
    if l in ("WARNING", "HIGH", "VERY HIGH"):
        return "badge-warning"
    if l in ("WATCH", "MODERATE"):
        return "badge-watch"
    return "badge-normal"


def render_badge(level: Optional[str], text: Optional[str] = None) -> str:
    """Return an HTML risk badge string."""
    display = text or level or "UNKNOWN"
    cls = risk_badge_class(level)
    return f'<span class="risk-badge {cls}">{display}</span>'


# ---------------------------------------------------------------------------
# KPI card
# ---------------------------------------------------------------------------

def kpi_card(icon: str, label: str, value: str, unit: str = "", color: Optional[str] = None) -> str:
    """Return HTML for a KPI card. Pass to st.markdown(unsafe_allow_html=True)."""
    val_style = f"color:{color};" if color else ""
    return f"""
    <div class="glass-card" style="text-align:center; padding:1.5rem 1rem;">
      <div style="font-size:1.5rem; margin-bottom:0.4rem;">{icon}</div>
      <div style="font-size:0.7rem; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.12em; margin-bottom:0.5rem;">{label}</div>
      <div style="font-size:1.7rem; font-weight:700; color:var(--text-primary); line-height:1; {val_style}">{value}</div>
      {f'<div style="font-size:0.8rem; color:var(--text-secondary); margin-top:0.3rem;">{unit}</div>' if unit else ''}
    </div>
    """


def render_kpi_row(metrics: list[dict]) -> None:
    """Render a row of KPI cards.

    Each dict must have: icon, label, value, unit (optional), color (optional).
    """
    n = len(metrics)
    cols = st.columns(n)
    for col, m in zip(cols, metrics):
        with col:
            st.markdown(
                kpi_card(
                    icon=m.get("icon", ""),
                    label=m.get("label", ""),
                    value=m.get("value", "—"),
                    unit=m.get("unit", ""),
                    color=m.get("color"),
                ),
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Section title
# ---------------------------------------------------------------------------

def section_title(text: str, icon: str = "") -> None:
    """Render a styled section title."""
    prefix = f"{icon} " if icon else ""
    st.markdown(
        f'<div class="section-title">{prefix}{text}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------

def empty_state(icon: str, title: str, body: str = "") -> None:
    """Professional empty / not-found state."""
    st.markdown(
        f"""
        <div class="empty-state">
          <div class="empty-state-icon">{icon}</div>
          <div class="empty-state-title">{title}</div>
          {'<div style="font-size:0.85rem;color:#64748b;max-width:380px;margin:0 auto;">' + body + '</div>' if body else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )
