"""
ml_prediction.py – AI Heatwave Forecast card for SIH26083.

Displays the prototype ML heatwave-event classification output.
Clearly labelled as a prototype — not a production-validated model,
not an official warning, and not a medical prediction.
"""
from __future__ import annotations

import streamlit as st

from components.metrics import render_badge


def render_ml_prediction_card(ml_prediction: dict | None) -> None:
    """Render the Prototype ML Heatwave Forecast card.

    When available=False (or ml_prediction is None), shows a clearly labelled
    "Currently unavailable" state.  The rest of the dashboard continues to
    function normally regardless of ML availability.
    """
    if not ml_prediction or not ml_prediction.get("available"):
        reason = (ml_prediction or {}).get("reason", "No forecast data available")
        st.markdown(
            f"""
            <div class="glass-card" style="border-left:3px solid #64748b">
              <div style="font-size:0.7rem;font-weight:700;color:#64748b;text-transform:uppercase;
                          letter-spacing:0.12em;margin-bottom:0.5rem">
                🤖 AI Heatwave Forecast
              </div>
              <div style="font-size:0.95rem;font-weight:600;color:#94a3b8;margin-bottom:0.35rem">
                Currently Unavailable
              </div>
              <div style="font-size:0.78rem;color:#475569;line-height:1.5;margin-bottom:0.5rem">
                <b>Reason:</b> {reason}
              </div>
              <div style="margin-top:0.6rem;padding-top:0.5rem;
                          border-top:1px solid rgba(255,255,255,0.06);
                          font-size:0.7rem;color:#475569">
                Prototype ML · v0.16 &nbsp;·&nbsp;
                Forecast-pattern heatwave event classifier
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # --- Available prediction ---
    label = ml_prediction.get("label", "UNKNOWN")
    prob = ml_prediction.get("probability")
    model_ver = ml_prediction.get("model_version", "v0.16")
    timestamp = ml_prediction.get("forecast_timestamp", "—")

    # Probability string — never fabricated; only shown when the backend
    # actually returns a numeric probability.
    prob_pct: str = "Unavailable"
    prob_color: str = "#94a3b8"
    if prob is not None:
        try:
            prob_f = float(prob)
            prob_pct = f"{prob_f * 100:.1f}%"
            if prob_f >= 0.70:
                prob_color = "#ef4444"
            elif prob_f >= 0.45:
                prob_color = "#f59e0b"
            else:
                prob_color = "#10b981"
        except (ValueError, TypeError):
            pass

    # Label styling
    is_heatwave = label == "HEATWAVE"
    label_color = "#ef4444" if is_heatwave else "#10b981"
    if label == "UNKNOWN":
        label_color = "#64748b"

    display_label = label.replace("_", " ")

    st.markdown(
        f"""
        <div class="glass-card" style="border-left:3px solid {label_color}">

          <!-- Header row -->
          <div style="display:flex;justify-content:space-between;align-items:center;
                      margin-bottom:0.6rem">
            <div style="font-size:0.7rem;font-weight:700;color:#64748b;
                        text-transform:uppercase;letter-spacing:0.12em">
              🤖 AI Heatwave Forecast
            </div>
            {render_badge(display_label)}
          </div>

          <!-- Prediction label -->
          <div style="font-size:1.3rem;font-weight:800;color:{label_color};
                      letter-spacing:0.04em;margin-bottom:0.4rem">
            {display_label}
          </div>

          <!-- Probability -->
          <div style="font-size:0.78rem;color:#94a3b8;margin-bottom:0.15rem">
            <span style="color:#64748b">Heatwave probability:</span>
            <span style="color:{prob_color};font-weight:700;margin-left:0.3rem">{prob_pct}</span>
          </div>

          <!-- Forecast timestamp -->
          <div style="font-size:0.75rem;color:#64748b;margin-bottom:0.15rem">
            <span>Forecast:</span>
            <span style="color:#94a3b8;margin-left:0.3rem">{timestamp}</span>
          </div>

          <!-- Source note -->
          <div style="font-size:0.73rem;color:#475569;margin-top:0.4rem;
                      font-style:italic">
            Prediction generated from forecast weather features.
          </div>

          <!-- Footer: model info + disclaimer -->
          <div style="margin-top:0.65rem;padding-top:0.5rem;
                      border-top:1px solid rgba(255,255,255,0.06);
                      font-size:0.7rem;color:#f59e0b;line-height:1.5">
            <b>Prototype ML · {model_ver}</b> &nbsp;·&nbsp;
            Forecast-pattern heatwave event classifier<br>
            <span style="color:#475569">
              ⚠️ Not an official warning or medical prediction.
            </span>
          </div>

        </div>
        """,
        unsafe_allow_html=True,
    )
