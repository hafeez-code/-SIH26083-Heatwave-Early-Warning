"""
app.py – SIH26083 Heatwave Intelligence & Early Warning Command Center.

Run with:
    cd streamlit_app
    streamlit run app.py

Configuration:
    Set STREAMLIT_BACKEND_URL env var to override the default backend URL.
    Default: http://127.0.0.1:5000/api
"""
from __future__ import annotations

import os
import sys

# Ensure the streamlit_app directory is on the path when run from repo root.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import streamlit as st

# ---------------------------------------------------------------------------
# Page configuration – must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SIH26083 · Heatwave Intelligence Command Center",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "SIH26083 – Heatwave Intelligence & Early Warning System\n\nBuilt for Smart India Hackathon 2026.",
    },
)

# ---------------------------------------------------------------------------
# Load CSS theme
# ---------------------------------------------------------------------------
_CSS_PATH = os.path.join(_HERE, "styles", "theme.css")
if os.path.exists(_CSS_PATH):
    with open(_CSS_PATH, "r") as _f:
        _css = _f.read()
    st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Import modules after path setup
# ---------------------------------------------------------------------------
import api.backend_client as client
from components.header import render_header
# pyrefly: ignore [missing-import]
from views import command_center, area_intelligence, forecast, alerts


# ---------------------------------------------------------------------------
# Backend health check
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def _health_check():
    return client.check_health()

@st.cache_data(ttl=60)
def _get_areas():
    return client.get_areas()

@st.cache_data(ttl=60)
def _get_ew(area_id: int):
    return client.get_early_warning(area_id)


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
def _render_sidebar() -> str:
    with st.sidebar:
        st.markdown(
            """
            <div style="padding:1rem 0 0.5rem;text-align:center">
              <div style="font-size:2rem;margin-bottom:0.4rem">🌡️</div>
              <div style="font-size:0.75rem;font-weight:700;color:#94a3b8;text-transform:uppercase;letter-spacing:0.18em">SIH26083</div>
              <div style="font-size:0.68rem;color:#64748b;margin-top:0.15rem">Heatwave Intelligence</div>
            </div>
            <hr style="border-color:rgba(255,255,255,0.08);margin:0.75rem 0">
            """,
            unsafe_allow_html=True,
        )

        page = st.radio(
            "Navigation",
            options=[
                "🏠  Command Center",
                "🔬  Area Intelligence",
                "📈  Forecast",
                "🚨  Alert Center",
                "ℹ️  Methodology",
            ],
            label_visibility="collapsed",
            key="nav_radio",
        )

        st.markdown(
            """
            <hr style="border-color:rgba(255,255,255,0.06);margin:1rem 0">
            <div style="font-size:0.7rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.1em;padding:0 0.5rem;margin-bottom:0.5rem">
              Monitored Areas
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Dynamic Areas List
        areas, err = _get_areas()
        if not err and areas:
            for a in areas:
                aid = a["id"]
                name = a["name"]
                
                ew, ew_err = _get_ew(aid)
                temp = "—"
                level = "NORMAL"
                color = "#34d399"
                
                if not ew_err and ew:
                    w = ew.get("weather", {})
                    t = w.get("temperature")
                    if t is not None:
                        temp = f"{float(t):.1f}°"
                    
                    status = ew.get("overall_status", "NORMAL")
                    level = status
                    
                    if status == "WATCH": color = "#fbbf24"
                    elif status == "WARNING": color = "#fb923c"
                    elif status in ["CRITICAL", "EXTREME", "VERY HIGH"]: color = "#f87171"
                else:
                    temp = "Unavail"
                    color = "#64748b"

                st.markdown(
                    f"""
                    <div style="padding:0.4rem 0.6rem;margin-bottom:0.3rem;border-radius:6px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.04);display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <div style="font-size:0.8rem;color:#f8fafc;font-weight:500;">{name}</div>
                            <div style="font-size:0.65rem;color:{color};font-weight:600;margin-top:2px">{level}</div>
                        </div>
                        <div style="font-size:0.9rem;font-weight:600;color:#f8fafc">{temp}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
        else:
            st.markdown('<div style="font-size:0.8rem;color:#64748b;padding:0 0.5rem">Unavailable</div>', unsafe_allow_html=True)

        st.markdown(
            """
            <hr style="border-color:rgba(255,255,255,0.06);margin:1rem 0 0.5rem">
            <div style="font-size:0.7rem;color:#475569;padding:0 0.5rem">
              <div style="margin-bottom:0.3rem;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.1em">Risk Legend</div>
              <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.2rem">
                <span style="width:10px;height:10px;border-radius:50%;background:#34d399;display:inline-block"></span>
                <span>NORMAL</span>
              </div>
              <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.2rem">
                <span style="width:10px;height:10px;border-radius:50%;background:#fbbf24;display:inline-block"></span>
                <span>WATCH</span>
              </div>
              <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.2rem">
                <span style="width:10px;height:10px;border-radius:50%;background:#fb923c;display:inline-block"></span>
                <span>WARNING</span>
              </div>
              <div style="display:flex;align-items:center;gap:0.5rem">
                <span style="width:10px;height:10px;border-radius:50%;background:#f87171;display:inline-block"></span>
                <span>CRITICAL</span>
              </div>
            </div>
            <hr style="border-color:rgba(255,255,255,0.06);margin:0.75rem 0">
            <div style="font-size:0.68rem;color:#3d5272;text-align:center;padding-bottom:0.5rem">
              v0.20 &nbsp;·&nbsp; Smart India Hackathon 2026
            </div>
            """,
            unsafe_allow_html=True,
        )

        return page


# ---------------------------------------------------------------------------
# Methodology page (inline, no import needed)
# ---------------------------------------------------------------------------
def _render_methodology() -> None:
    st.markdown(
        """
        <div style="max-width:760px">
          <div style="font-size:1.3rem;font-weight:700;color:#f0f6ff;margin-bottom:0.5rem">
            🧠 System Intelligence & Methodology
          </div>
          <div style="font-size:0.85rem;color:#94a3b8;margin-bottom:1.5rem">
            How the SIH26083 platform computes risk and generates early warnings
          </div>
        """,
        unsafe_allow_html=True,
    )

    steps = [
        (
            "🌤️  Weather Data Ingestion",
            "Real-time meteorological observations are ingested from external weather APIs "
            "and stored per monitored area. Each observation includes temperature, humidity, "
            "wind speed, precipitation, and solar radiation.",
        ),
        (
            "⚙️  Feature Engineering",
            "Raw observations are normalised and processed into ML-ready feature vectors. "
            "Derived features (e.g., apparent temperature, humidity-temperature interaction) "
            "are computed from validated meteorological formulas.",
        ),
        (
            "🌊  Heatwave Risk Assessment",
            "A deterministic rule-based engine evaluates meteorological thresholds to compute "
            "a Heatwave Risk Score (0–100) and assign a risk level: LOW → MODERATE → HIGH → VERY HIGH → EXTREME. "
            "Contributing factors are explicitly logged for transparency.",
        ),
        (
            "🌡️  Human Thermal Stress Index",
            "The Heat Index (Rothfusz equation) and Humidex are combined with solar radiation "
            "and wind correction factors to produce a Human Thermal Stress Index (HTSI). "
            "This reflects the perceived thermal burden on the human body.",
        ),
        (
            "👥  Demographic Vulnerability",
            "Where demographic data exists (% elderly ≥65, % children <18), a vulnerability "
            "multiplier is applied to amplify risk for high-risk population groups. "
            "This enables targeted interventions for the most at-risk communities.",
        ),
        (
            "⚠️  Mortality / Vulnerability Risk",
            "The HTSI and demographic vulnerability factor are combined into a Mortality Risk "
            "Index that quantifies population-level heat-related mortality risk. "
            "This is the primary driver for emergency alert generation.",
        ),
        (
            "🤖  ML-Enhanced Forecasting",
            "Trained scikit-learn models generate probabilistic heatwave event predictions "
            "over 24–48 hour forecast windows. Classification models output event probability; "
            "regression models estimate risk score magnitude.",
        ),
        (
            "🚨  Early Warning & Alerts",
            "When any risk layer (heatwave, thermal stress, or mortality) crosses configured "
            "thresholds, the alert service generates deduplicated early warnings. "
            "Alerts are classified as INFORMATIONAL, WATCH, or WARNING and broadcast to "
            "authorities for preemptive intervention.",
        ),
    ]

    for i, (title, body) in enumerate(steps):
        connector = '<div style="text-align:center;margin:0.1rem 0;color:#2563eb;font-size:1.2rem">↓</div>' if i < len(steps) - 1 else ""
        st.markdown(
            f"""
            <div class="glass-card" style="margin-bottom:0">
              <div style="font-weight:600;color:#f0f6ff;margin-bottom:0.4rem;font-size:0.95rem">{title}</div>
              <div style="color:#94a3b8;font-size:0.83rem;line-height:1.6">{body}</div>
            </div>
            {connector}
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div style="margin-top:1.5rem;padding:1rem;background:rgba(37,99,235,0.08);border:1px solid rgba(37,99,235,0.2);border-radius:10px">
          <div style="font-size:0.78rem;font-weight:600;color:#60a5fa;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:0.5rem">
            🎯 Key Design Principles
          </div>
          <ul style="margin:0;padding-left:1.2rem;color:#94a3b8;font-size:0.83rem;line-height:1.8">
            <li>No synthetic or fabricated data — all risk scores derive from real ingested observations</li>
            <li>Transparent contributing factors for every risk assessment</li>
            <li>Demographic equity — higher-risk populations receive amplified alerts</li>
            <li>Deterministic rule engine + ML probability for defence-in-depth warning</li>
            <li>GIS-ready output with real area coordinates for hyper-local targeting</li>
          </ul>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
def main() -> None:
    # Health check
    backend_online, backend_msg = _health_check()

    # Render header
    render_header(backend_online, backend_msg)

    # Sidebar – refresh button
    page = _render_sidebar()

    # Global refresh in main area
    col_r = st.columns([6, 1])[1]
    with col_r:
        if st.button("🔄 Refresh", key="global_refresh"):
            st.cache_data.clear()
            st.rerun()

    # Page routing
    if "Command Center" in page:
        command_center.render(backend_online)
    elif "Area Intelligence" in page:
        area_intelligence.render(backend_online)
    elif "Forecast" in page:
        forecast.render(backend_online)
    elif "Alert Center" in page:
        alerts.render(backend_online)
    elif "Methodology" in page:
        _render_methodology()


if __name__ == "__main__":
    main()
