# SIH26083 – Heatwave Intelligence & Early Warning Command Center

A professional Streamlit-based command-center frontend for the SIH26083 Heatwave Early Warning System.

## Prerequisites

- Python 3.10+
- The SIH26083 Flask backend running at `http://127.0.0.1:5000`

## Installation

```bash
cd streamlit_app
pip install -r requirements.txt
```

## Running

**Step 1: Start the backend**

```bash
cd backend
python app.py
```

**Step 2: Start the Streamlit app**

```bash
cd streamlit_app
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Configuration

Set the `STREAMLIT_BACKEND_URL` environment variable to override the default backend URL:

```bash
STREAMLIT_BACKEND_URL=http://127.0.0.1:5000/api streamlit run app.py
```

## Features

| Page | Description |
|------|-------------|
| 🏠 Command Center | Live KPI metrics, GIS risk map, area overview table, active alerts quick-view |
| 🔬 Area Intelligence | Per-area heatwave risk, thermal stress, mortality risk, demographics, alert details |
| 📈 Forecast | 24–48h weather trend charts, risk trajectory, ML predictions, early-warning trajectory |
| 🚨 Alert Center | Full alert listing with filtering, severity grouping, intervention framework |
| ℹ️ Methodology | System intelligence pipeline explanation for non-technical reviewers |

## Architecture

```
streamlit_app/
├── app.py                    ← Entry point
├── api/
│   └── backend_client.py     ← Centralized Flask API client
├── components/
│   ├── header.py             ← Command-center header
│   ├── metrics.py            ← KPI cards, badges, section titles
│   ├── risk_cards.py         ← Risk assessment cards
│   ├── charts.py             ← Plotly chart components
│   └── map.py                ← Folium GIS map component
├── pages/
│   ├── command_center.py     ← Main dashboard
│   ├── area_intelligence.py  ← Area deep-dive
│   ├── forecast.py           ← Forecast analysis
│   └── alerts.py             ← Alert center
├── styles/
│   └── theme.css             ← Dark navy command-center theme
└── requirements.txt
```

## Backend API Contract

The frontend uses the following backend endpoints (read-only):

- `GET /api/health`
- `GET /api/areas`
- `GET /api/areas/<id>/early-warning`
- `GET /api/weather/forecast?area_id=<id>&stored=true`
- `GET /api/risk/forecast?area_id=<id>`
- `GET /api/alerts`

No backend files are modified by this frontend.
