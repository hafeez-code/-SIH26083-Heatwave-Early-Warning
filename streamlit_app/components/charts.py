"""
charts.py – Plotly chart components for SIH26083.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st


# ---------------------------------------------------------------------------
# Common Plotly layout defaults
# ---------------------------------------------------------------------------

_DARK_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(15,31,56,0.6)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=11),
    margin=dict(l=10, r=10, t=35, b=10),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8"),
    ),
    xaxis=dict(
        gridcolor="rgba(255,255,255,0.05)",
        linecolor="rgba(255,255,255,0.1)",
        tickfont=dict(color="#64748b"),
    ),
    yaxis=dict(
        gridcolor="rgba(255,255,255,0.05)",
        linecolor="rgba(255,255,255,0.1)",
        tickfont=dict(color="#64748b"),
    ),
)

_RISK_COLOR_MAP = {
    "LOW": "#10b981",
    "MODERATE": "#f59e0b",
    "HIGH": "#f97316",
    "VERY HIGH": "#ef4444",
    "EXTREME": "#ef4444",
}


def _apply_layout(fig: go.Figure, title: str = "", height: int = 300) -> go.Figure:
    layout = dict(**_DARK_LAYOUT, height=height)
    if title:
        layout["title"] = dict(text=title, font=dict(color="#f0f6ff", size=13), x=0.01)
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Weather forecast charts
# ---------------------------------------------------------------------------

def forecast_temperature_chart(forecasts: list[dict], height: int = 280) -> Optional[go.Figure]:
    """Line chart of forecast temperature over time."""
    if not forecasts:
        return None

    df = pd.DataFrame(forecasts)
    if "forecast_timestamp" not in df.columns or "temperature" not in df.columns:
        return None

    df = df.dropna(subset=["temperature"])
    if df.empty:
        return None

    df["forecast_timestamp"] = pd.to_datetime(df["forecast_timestamp"], errors="coerce")
    df = df.sort_values("forecast_timestamp")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["forecast_timestamp"],
        y=df["temperature"],
        mode="lines+markers",
        name="Temperature",
        line=dict(color="#ef4444", width=2.5, shape="spline"),
        marker=dict(size=5, color="#ef4444"),
        fill="tozeroy",
        fillcolor="rgba(239,68,68,0.08)",
    ))

    fig.update_yaxes(title_text="°C", title_font=dict(color="#94a3b8"))
    return _apply_layout(fig, "🌡️  Temperature Forecast (°C)", height)


def forecast_humidity_chart(forecasts: list[dict], height: int = 240) -> Optional[go.Figure]:
    """Line chart of forecast humidity over time."""
    if not forecasts:
        return None

    df = pd.DataFrame(forecasts)
    if "forecast_timestamp" not in df.columns or "humidity" not in df.columns:
        return None

    df = df.dropna(subset=["humidity"])
    if df.empty:
        return None

    df["forecast_timestamp"] = pd.to_datetime(df["forecast_timestamp"], errors="coerce")
    df = df.sort_values("forecast_timestamp")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["forecast_timestamp"],
        y=df["humidity"],
        mode="lines",
        name="Humidity",
        line=dict(color="#06b6d4", width=2, shape="spline"),
        fill="tozeroy",
        fillcolor="rgba(6,182,212,0.07)",
    ))

    fig.update_yaxes(title_text="%", title_font=dict(color="#94a3b8"))
    return _apply_layout(fig, "💧  Relative Humidity (%)", height)


def forecast_wind_chart(forecasts: list[dict], height: int = 240) -> Optional[go.Figure]:
    """Line chart of forecast wind speed over time."""
    if not forecasts:
        return None

    df = pd.DataFrame(forecasts)
    if "forecast_timestamp" not in df.columns or "wind_speed" not in df.columns:
        return None

    df = df.dropna(subset=["wind_speed"])
    if df.empty:
        return None

    df["forecast_timestamp"] = pd.to_datetime(df["forecast_timestamp"], errors="coerce")
    df = df.sort_values("forecast_timestamp")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["forecast_timestamp"],
        y=df["wind_speed"],
        mode="lines",
        name="Wind Speed",
        line=dict(color="#8b5cf6", width=2, shape="spline"),
        fill="tozeroy",
        fillcolor="rgba(139,92,246,0.07)",
    ))

    fig.update_yaxes(title_text="km/h", title_font=dict(color="#94a3b8"))
    return _apply_layout(fig, "💨  Wind Speed (km/h)", height)


def forecast_precipitation_chart(forecasts: list[dict], height: int = 220) -> Optional[go.Figure]:
    """Bar chart of forecast precipitation."""
    if not forecasts:
        return None

    df = pd.DataFrame(forecasts)
    if "forecast_timestamp" not in df.columns or "precipitation" not in df.columns:
        return None

    df = df.dropna(subset=["precipitation"])
    if df.empty:
        return None

    df["forecast_timestamp"] = pd.to_datetime(df["forecast_timestamp"], errors="coerce")
    df = df.sort_values("forecast_timestamp")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["forecast_timestamp"],
        y=df["precipitation"],
        name="Precipitation",
        marker_color="rgba(6,182,212,0.6)",
        marker_line_color="#06b6d4",
        marker_line_width=1,
    ))

    fig.update_yaxes(title_text="mm", title_font=dict(color="#94a3b8"))
    return _apply_layout(fig, "🌧️  Precipitation (mm)", height)


# ---------------------------------------------------------------------------
# Risk forecast chart
# ---------------------------------------------------------------------------

def risk_trajectory_chart(deterministic_risks: list[dict], height: int = 280) -> Optional[go.Figure]:
    """Scatter + line chart of deterministic risk score over forecast timestamps."""
    if not deterministic_risks:
        return None

    df = pd.DataFrame(deterministic_risks)
    if "timestamp" not in df.columns or "risk_score" not in df.columns:
        return None

    df = df.dropna(subset=["risk_score"])
    if df.empty:
        return None

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.sort_values("timestamp")
    df["color"] = df["risk_level"].map(
        lambda l: _RISK_COLOR_MAP.get((l or "").upper(), "#94a3b8")
    )

    fig = go.Figure()

    # Line
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["risk_score"],
        mode="lines",
        name="Risk Score",
        line=dict(color="rgba(249,115,22,0.5)", width=1.5, dash="dot"),
        showlegend=False,
    ))

    # Colored markers by level
    for level, grp in df.groupby("risk_level", dropna=False):
        color = _RISK_COLOR_MAP.get((level or "").upper(), "#94a3b8")
        fig.add_trace(go.Scatter(
            x=grp["timestamp"],
            y=grp["risk_score"],
            mode="markers",
            name=str(level or "Unknown"),
            marker=dict(size=9, color=color, line=dict(color="#0f1f38", width=1.5)),
        ))

    fig.add_hline(y=60, line_dash="dot", line_color="rgba(245,158,11,0.4)",
                  annotation_text="WATCH", annotation_font_color="#f59e0b",
                  annotation_position="right")
    fig.add_hline(y=80, line_dash="dot", line_color="rgba(239,68,68,0.4)",
                  annotation_text="HIGH RISK", annotation_font_color="#ef4444",
                  annotation_position="right")

    fig.update_yaxes(title_text="Risk Score", title_font=dict(color="#94a3b8"), range=[0, 105])
    return _apply_layout(fig, "📈  Risk Score Trajectory", height)


# ---------------------------------------------------------------------------
# Contributing factors bar chart
# ---------------------------------------------------------------------------

def factors_chart(factors: list[str], title: str = "Contributing Factors", height: int = 220) -> Optional[go.Figure]:
    """Horizontal bar chart from a list of factor strings."""
    if not factors:
        return None

    # Parse "Factor: value" format if possible
    labels = []
    values = []
    for f in factors:
        if ":" in f:
            parts = f.split(":", 1)
            label = parts[0].strip()
            try:
                val = float(parts[1].strip().split()[0])
                labels.append(label)
                values.append(abs(val))
            except (ValueError, IndexError):
                labels.append(f[:40])
                values.append(1)
        else:
            labels.append(f[:40])
            values.append(1)

    if not values:
        return None

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker_color="rgba(37,99,235,0.7)",
        marker_line_color="rgba(37,99,235,0.9)",
        marker_line_width=1,
    ))

    # Build merged layout to avoid duplicate-keyword errors when _DARK_LAYOUT
    # already defines margin, xaxis, or yaxis and we need to override them.
    layout: dict = {
        **_DARK_LAYOUT,
        "height": height,
        "title": dict(text=title, font=dict(color="#f0f6ff", size=12), x=0.01),
        # Override margin (deep-merge so any _DARK_LAYOUT margin keys are kept
        # unless explicitly overridden here).
        "margin": {
            **_DARK_LAYOUT.get("margin", {}),
            "l": 130,
            "r": 10,
            "t": 35,
            "b": 10,
        },
        # Override xaxis to hide the axis while preserving dark-theme grid/line
        # colours that are already set in _DARK_LAYOUT["xaxis"].
        "xaxis": {
            **_DARK_LAYOUT.get("xaxis", {}),
            "visible": False,
        },
        # Preserve yaxis from _DARK_LAYOUT and add factors-specific tick style.
        "yaxis": {
            **_DARK_LAYOUT.get("yaxis", {}),
            "tickfont": dict(size=10, color="#94a3b8"),
        },
    }
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def plot_chart(fig: Optional[go.Figure], config: Optional[dict] = None) -> None:
    """Render a Plotly figure or skip silently if None."""
    if fig is None:
        return
    cfg = dict(displayModeBar=False, responsive=True)
    if config:
        cfg.update(config)
    st.plotly_chart(fig, use_container_width=True, config=cfg)
