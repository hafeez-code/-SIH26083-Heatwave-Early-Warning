"""Tests for independent-label validation, provenance, and persistence."""

import os
import sys

import pytest
from flask import Flask

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from models.database_models import Area, HistoricalEventLabel, db
from services.label_preparation import (
    LabelPreparationError,
    attach_independent_labels,
    prepare_independent_label,
    prepare_independent_labels,
    persist_independent_labels,
)


def _label(area_id=1, timestamp="2026-07-01T12:00", **overrides):
    return {
        "area_id": area_id,
        "event_timestamp": timestamp,
        "label_value": 1,
        "label_source": "district health register",
        "source_reference": "DHR-2026-001",
        "validation_status": "validated",
        "provenance_type": "independent_validated",
        **overrides,
    }


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add_all([
            Area(name="Delhi", latitude=28.6, longitude=77.2),
            Area(name="Mumbai", latitude=19.0, longitude=72.8),
        ])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


def test_valid_label_preserves_independent_provenance_and_is_deterministic():
    first = prepare_independent_label(_label())
    assert first.event_timestamp == "2026-07-01T12:00:00"
    assert first.label_source == "district health register"
    labels = prepare_independent_labels([_label(2), _label(1, "2026-07-01T11:00")])
    assert [(label.area_id, label.event_timestamp) for label in labels] == [
        (1, "2026-07-01T11:00:00"), (2, "2026-07-01T12:00:00")
    ]


@pytest.mark.parametrize("overrides, message", [
    ({"label_value": None}, "binary"),
    ({"label_source": ""}, "label_source"),
    ({"validation_status": "unverified"}, "validation_status"),
    ({"label_name": "risk_score"}, "rule-derived"),
    ({"label_name": "risk_level"}, "rule-derived"),
    ({"derived_from": ["temperature", "humidity"]}, "weather features"),
    ({"provenance_type": "rule_based"}, "independent"),
])
def test_rejects_missing_or_non_independent_labels(overrides, message):
    with pytest.raises(LabelPreparationError, match=message):
        prepare_independent_label(_label(**overrides))


def test_empty_input_multi_area_attachment_and_idempotent_persistence(app):
    assert prepare_independent_labels([]) == []
    labels = prepare_independent_labels([_label(1), _label(2)])
    features = [
        {"area_id": 1, "forecast_timestamp": "2026-07-01T12:00:00"},
        {"area_id": 2, "forecast_timestamp": "2026-07-01T12:00:00"},
    ]
    assert [row["validated_heatwave_event"] for row in attach_independent_labels(features, labels)] == [1, 1]
    with app.app_context():
        persist_independent_labels([labels[0]], db.session)
        db.session.commit()
        update = prepare_independent_label(_label(label_value=0, source_reference="DHR-2026-002"))
        persist_independent_labels([update], db.session)
        db.session.commit()
        stored = HistoricalEventLabel.query.one()
        assert stored.label_value == 0
        assert stored.source_reference == "DHR-2026-002"
        assert HistoricalEventLabel.query.count() == 1
