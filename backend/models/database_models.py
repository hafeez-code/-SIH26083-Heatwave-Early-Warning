"""
database_models.py – SQLAlchemy ORM models for SIH26083.

Sprint 2: Database foundation.
Only the Area model is defined here; additional models will be added
in later sprints as the schema evolves.
"""

from flask_sqlalchemy import SQLAlchemy

# Shared SQLAlchemy extension instance.
# Imported by app.py for initialisation and by models for db.Model.
db = SQLAlchemy()


class Area(db.Model):
    """A geographic area monitored for heatwave risk."""

    __tablename__ = "area"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Area id={self.id} name={self.name!r}>"
