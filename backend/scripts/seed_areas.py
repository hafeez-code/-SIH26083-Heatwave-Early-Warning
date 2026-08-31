"""
seed_areas.py – Idempotent area seeder for SIH26083.

Usage (from the backend/ directory):
    python3 scripts/seed_areas.py

This script inserts a set of real Indian cities into the Area table.
It is fully idempotent:
  - Existing areas (matched by name) are preserved unchanged.
  - Existing IDs are never altered.
  - Running the script multiple times produces no duplicates.
  - No existing data is deleted.

Demographic data is approximate from public census sources (Census 2011 /
Indian Population Survey 2021 estimates).  These values illustrate the
demographic vulnerability model; they are not medically precise.

Real coordinates sourced from geographical data.  Each city uses its own
lat/lon so each scheduler instance collects area-specific weather.
"""
from __future__ import annotations

import os
import sys

# Ensure the backend/ directory is on the path so imports work when
# the script is run from either the repo root or the backend/ directory.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app import create_app
from models.database_models import Area, AreaDemographics, db


# ---------------------------------------------------------------------------
# Seed data – real Indian city coordinates and approximate demographics
# ---------------------------------------------------------------------------

SEED_AREAS = [
    {
        "name": "Hyderabad",
        "latitude": 17.3850,
        "longitude": 78.4867,
        "demographics": {
            "population_total": 6_809_970,
            "pct_elderly": 6.2,
            "pct_children": 22.4,
            "vulnerability_notes": (
                "Major metropolitan heat island. High urbanisation, low green cover in core city."
            ),
        },
    },
    {
        "name": "Delhi",
        "latitude": 28.7041,
        "longitude": 77.1025,
        "demographics": {
            "population_total": 16_787_941,
            "pct_elderly": 5.4,
            "pct_children": 26.3,
            "vulnerability_notes": (
                "Severe urban heat island. Dense slum population with limited cooling access."
            ),
        },
    },
    {
        "name": "Ahmedabad",
        "latitude": 23.0225,
        "longitude": 72.5714,
        "demographics": {
            "population_total": 5_570_585,
            "pct_elderly": 6.0,
            "pct_children": 21.5,
            "vulnerability_notes": (
                "Historically severe heatwaves (2010 event >1000 deaths). "
                "High vulnerability among outdoor workers and slum dwellers."
            ),
        },
    },
    {
        "name": "Nagpur",
        "latitude": 21.1458,
        "longitude": 79.0882,
        "demographics": {
            "population_total": 2_405_665,
            "pct_elderly": 6.8,
            "pct_children": 20.1,
            "vulnerability_notes": (
                "One of India's hottest cities. Extreme summer temps regularly exceed 45°C."
            ),
        },
    },
    {
        "name": "Jaipur",
        "latitude": 26.9124,
        "longitude": 75.7873,
        "demographics": {
            "population_total": 3_073_350,
            "pct_elderly": 6.5,
            "pct_children": 24.8,
            "vulnerability_notes": (
                "Arid Rajasthan climate. High risk for outdoor workers during summer months."
            ),
        },
    },
    {
        "name": "Chennai",
        "latitude": 13.0827,
        "longitude": 80.2707,
        "demographics": {
            "population_total": 7_088_000,
            "pct_elderly": 7.1,
            "pct_children": 18.9,
            "vulnerability_notes": (
                "Coastal city with high humidity compounding heat stress. "
                "Significant elderly population in central districts."
            ),
        },
    },
    {
        "name": "Bengaluru",
        "latitude": 12.9716,
        "longitude": 77.5946,
        "demographics": {
            "population_total": 8_443_675,
            "pct_elderly": 5.8,
            "pct_children": 19.7,
            "vulnerability_notes": (
                "Historically mild but rising temperatures due to rapid urban expansion "
                "and loss of green cover."
            ),
        },
    },
    {
        "name": "Mumbai",
        "latitude": 19.0760,
        "longitude": 72.8777,
        "demographics": {
            "population_total": 12_478_447,
            "pct_elderly": 6.3,
            "pct_children": 21.2,
            "vulnerability_notes": (
                "High humidity coastal city. Dense informal settlements with poor ventilation."
            ),
        },
    },
    {
        "name": "Vijayawada",
        "latitude": 16.5062,
        "longitude": 80.6480,
        "demographics": {
            "population_total": 1_048_240,
            "pct_elderly": 7.0,
            "pct_children": 22.0,
            "vulnerability_notes": (
                "Located in the Krishna river delta. High humidity and temperature "
                "combination during summer."
            ),
        },
    },
    {
        "name": "Visakhapatnam",
        "latitude": 17.6868,
        "longitude": 83.2185,
        "demographics": {
            "population_total": 1_728_128,
            "pct_elderly": 6.9,
            "pct_children": 21.6,
            "vulnerability_notes": (
                "Coastal industrial city. Port and steel plant workers at high outdoor heat risk."
            ),
        },
    },
]


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------

def seed(dry_run: bool = False) -> None:
    """Insert seed areas if they do not already exist.

    Parameters
    ----------
    dry_run:
        If True, print what would be inserted without committing anything.
    """
    app = create_app("development")
    with app.app_context():
        existing_names = {a.name for a in Area.query.all()}
        print(f"[seed_areas] Existing areas: {sorted(existing_names) or '(none)'}")

        inserted: list[str] = []
        skipped: list[str] = []

        for spec in SEED_AREAS:
            name = spec["name"]
            if name in existing_names:
                skipped.append(name)
                continue

            if dry_run:
                print(f"  [DRY RUN] Would insert: {name} ({spec['latitude']}, {spec['longitude']})")
                inserted.append(name)
                continue

            area = Area(
                name=name,
                latitude=spec["latitude"],
                longitude=spec["longitude"],
            )
            db.session.add(area)
            db.session.flush()  # Assign area.id before adding demographics

            demo_spec = spec.get("demographics")
            if demo_spec:
                # Only add demographics if none exist for this area
                existing_demo = AreaDemographics.query.filter_by(area_id=area.id).one_or_none()
                if existing_demo is None:
                    demo = AreaDemographics(
                        area_id=area.id,
                        population_total=demo_spec.get("population_total"),
                        pct_elderly=demo_spec.get("pct_elderly"),
                        pct_children=demo_spec.get("pct_children"),
                        vulnerability_notes=demo_spec.get("vulnerability_notes"),
                    )
                    db.session.add(demo)

            inserted.append(name)
            print(f"  [INSERT] {name} (lat={spec['latitude']}, lon={spec['longitude']})")

        if not dry_run and inserted:
            db.session.commit()

        if skipped:
            print(f"[seed_areas] Skipped (already exist): {', '.join(skipped)}")
        print(f"[seed_areas] Done — inserted {len(inserted)}, skipped {len(skipped)}.")

        # Print final state
        all_areas = Area.query.order_by(Area.id.asc()).all()
        print(f"\n[seed_areas] Final area roster ({len(all_areas)} total):")
        for a in all_areas:
            print(f"  ID={a.id:3d}  {a.name:<20}  ({a.latitude:.4f}, {a.longitude:.4f})")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed SIH26083 area database.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted without committing.",
    )
    args = parser.parse_args()
    seed(dry_run=args.dry_run)
