"""
header.py – Command-center header component for SIH26083.
"""
from __future__ import annotations

import streamlit as st
from datetime import datetime


def _status_html(online: bool, msg: str = "") -> str:
    if online:
        return (
            '<span style="color:#34d399;font-weight:600;font-size:0.8rem;">'
            '● SYSTEM ONLINE</span>'
        )
    return (
        '<span style="color:#f87171;font-weight:600;font-size:0.8rem;">'
        f'● SYSTEM OFFLINE &nbsp;|&nbsp; <span style="font-weight:400">{msg}</span></span>'
    )

def render_header(backend_online: bool, backend_msg: str = "") -> None:
    """Render the top command-center header banner."""
    now = datetime.now().strftime("%d %b %Y  %H:%M:%S")
    
    # Try to get currently selected area info from session state / cached areas if possible
    area_name = "System Overview"
    coords = ""
    
    selected = st.session_state.get("cmd_area_select")
    if selected:
        area_name = selected
        # Try to find coords from areas
        try:
            import api.backend_client as client
            areas, _ = client.get_areas()
            if areas:
                for a in areas:
                    if a.get("name") == selected:
                        lat = a.get("latitude")
                        lon = a.get("longitude")
                        if lat is not None and lon is not None:
                            coords = f"{float(lat):.4f}° N, {float(lon):.4f}° E"
                        break
        except Exception:
            pass
            
    coord_html = f'<div style="font-size:0.8rem;color:#cbd5e1;margin-top:0.3rem">📍 {area_name} &nbsp;·&nbsp; {coords}</div>' if coords else f'<div style="font-size:0.8rem;color:#cbd5e1;margin-top:0.3rem">📍 {area_name}</div>'

    st.markdown(
        f"""
        <div class="cmd-header">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:0.75rem;">
            <div>
              <div class="cmd-header-badge">SIH26083 &nbsp;·&nbsp; Government of India &nbsp;·&nbsp; Smart India Hackathon</div>
              <div class="cmd-header-title">AI-ASSISTED HEATWAVE EARLY-WARNING SYSTEM</div>
              {coord_html}
            </div>
            <div style="text-align:right;min-width:220px;">
              <div style="font-family:'JetBrains Mono',monospace;font-size:0.8rem;color:#cbd5e1;margin-bottom:0.4rem;font-weight:500">{now}</div>
              {_status_html(backend_online, backend_msg)}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
