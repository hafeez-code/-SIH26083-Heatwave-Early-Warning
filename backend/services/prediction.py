"""Minimal v0.16 ML inference service built on the v0.15 training pipeline.

This module never reads ``HeatwaveRiskAssessment``, never derives labels,
and never writes to the database.  All outputs are in-memory
``PredictionResult`` instances returned to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping, Optional

from sklearn.pipeline import Pipeline

from services.forecast_features import build_forecast_features
from services.label_preparation import DEFAULT_LABEL_NAME
from services.ml_dataset import MODEL_FEATURE_COLUMNS
from services.ml_training import TaskType
from services.model_artifacts import (
    ArtifactError,
    load_training_artifact,
    resolve_artifact_path,
)


class PredictionError(ValueError):
    """Raised when a prediction cannot be produced safely."""


@dataclass(frozen=True)
class PredictionResult:
    """One inference row: metadata, the model output, and the features used."""

    area_id: int
    forecast_timestamp: str
    task: TaskType
    prediction: int | float
    probability: Optional[float]
    feature_values: dict[str, float]


def _record_value(record: object, name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(name)
    return getattr(record, name, None)


def load_prediction_artifact(
    artifact_dir: str,
    *,
    version: str,
    task: TaskType = "classification",
    target_column: str = DEFAULT_LABEL_NAME,
    fallback_version: Optional[str] = None,
    artifact_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Resolve, load, and validate a saved training artifact for inference.

    When ``artifact_payload`` is supplied by the caller it is used directly
    without touching disk; otherwise the directory is searched using
    :func:`resolve_artifact_path`.

    The loaded contract is validated so that an artifact with incompatible
    feature names or pipeline steps is rejected before any data is scored.
    """
    if artifact_payload is None:
        try:
            resolved = resolve_artifact_path(
                artifact_dir,
                version=version,
                task=task,
                target_column=target_column,
                fallback_version=fallback_version,
            )
        except ArtifactError as exc:
            raise PredictionError(str(exc)) from exc
        try:
            artifact_payload = load_training_artifact(resolved)
        except ArtifactError as exc:
            raise PredictionError(str(exc)) from exc

    pipeline: Optional[Pipeline] = artifact_payload.get("sklearn_pipeline")
    if not isinstance(pipeline, Pipeline):
        raise PredictionError("Artifact does not contain a sklearn Pipeline.")
    if "scaler" not in pipeline.named_steps or "model" not in pipeline.named_steps:
        raise PredictionError("Artifact pipeline is missing scaler or model steps.")

    feature_names = artifact_payload.get("feature_names")
    if not isinstance(feature_names, (list, tuple)):
        raise PredictionError("Artifact contract is missing feature_names.")
    if tuple(feature_names) != tuple(MODEL_FEATURE_COLUMNS):
        raise PredictionError(
            "Artifact feature_names do not match the current MODEL_FEATURE_COLUMNS contract."
        )

    payload_task = artifact_payload.get("task")
    if payload_task is not None and payload_task != task:
        raise PredictionError(
            f"Artifact task {payload_task!r} does not match requested task {task!r}."
        )

    artifact_payload["_resolved_task"] = task
    return artifact_payload


def build_inference_features(records: Iterable[object]) -> list[dict[str, Any]]:
    """Build MODEL_FEATURE_COLUMNS for each record and drop incomplete rows.

    Reuses the v0.11 ``build_forecast_features`` engine so the exact same
    rolling-window / interaction formulas that produced the training data
    are applied at inference time.  The existing training-time missing-value
    policy is preserved: rows with any null or non-finite selected feature
    are dropped rather than imputed.

    Each returned dict contains the 10 feature values plus the
    ``area_id`` and ``forecast_timestamp`` metadata fields.
    """
    materialized = list(records)
    if not materialized:
        return []

    for index, record in enumerate(materialized):
        for required in ("area_id", "forecast_timestamp"):
            value = _record_value(record, required)
            if value is None:
                raise PredictionError(f"Record {index} is missing {required!r}.")

    engineered = build_forecast_features(materialized)

    if len(engineered) != len(materialized):
        raise PredictionError(
            "Feature builder produced a different number of rows than the input."
        )

    indexed_metadata: list[tuple[Any, Any]] = [
        (_record_value(record, "area_id"), _record_value(record, "forecast_timestamp"))
        for record in materialized
    ]

    enriched: list[dict[str, Any]] = []
    for features, (area_id, forecast_timestamp) in zip(engineered, indexed_metadata):
        row = dict(features)
        row["area_id"] = area_id
        row["forecast_timestamp"] = forecast_timestamp
        has_all = all(
            column in row and row[column] is not None
            and isinstance(row[column], (int, float))
            and isfinite(row[column])
            for column in MODEL_FEATURE_COLUMNS
        )
        if not has_all:
            continue
        for column in MODEL_FEATURE_COLUMNS:
            row[column] = float(row[column])
        enriched.append(row)
    return enriched


def _extract_matrix(rows: list[dict[str, Any]]) -> list[list[float]]:
    return [[row[column] for column in MODEL_FEATURE_COLUMNS] for row in rows]


def predict(
    records: list[dict[str, Any]],
    *,
    artifact_dir: str,
    task: TaskType = "classification",
    target_column: str = DEFAULT_LABEL_NAME,
    artifact_version: str = "v0.16",
    fallback_version: Optional[str] = "v0.15",
    artifact_payload: Optional[dict[str, Any]] = None,
) -> list[PredictionResult]:
    """Score ``records`` using a saved v0.15/v0.16 trained pipeline.

    Parameters match the existing training pipeline naming convention so
    callers can reuse their configuration values unchanged.  When the
    requested ``artifact_version`` artifact is absent and
    ``fallback_version`` is set the older artifact is transparently loaded
    so environments that only have a v0.15 model remain usable.
    """
    if target_column in ("risk_score", "risk_level"):
        raise PredictionError(
            f"{target_column!r} is a deterministic rule output and cannot be an ML prediction target."
        )
    if task not in ("classification", "regression"):
        raise PredictionError("task must be either 'classification' or 'regression'.")

    artifact = load_prediction_artifact(
        artifact_dir,
        version=artifact_version,
        task=task,
        target_column=target_column,
        fallback_version=fallback_version,
        artifact_payload=artifact_payload,
    )
    pipeline: Pipeline = artifact["sklearn_pipeline"]

    inference_rows = build_inference_features(records)
    if not inference_rows:
        return []

    X = _extract_matrix(inference_rows)

    if task == "classification":
        predictions = pipeline.predict(X)
        if hasattr(pipeline, "predict_proba"):
            probabilities = pipeline.predict_proba(X)
            classes = list(pipeline.classes_)
            try:
                positive_index = classes.index(1)
            except ValueError:
                positive_index = len(classes) - 1
            class_probabilities = [float(row[positive_index]) for row in probabilities]
        else:
            class_probabilities = [None for _ in predictions]
    else:
        raw_predictions = pipeline.predict(X)
        predictions = raw_predictions
        class_probabilities = [None for _ in predictions]

    results: list[PredictionResult] = []
    for row, pred_value, prob in zip(inference_rows, predictions, class_probabilities):
        if task == "classification":
            try:
                prediction_value = int(pred_value)
            except (TypeError, ValueError) as exc:
                raise PredictionError("Classification prediction is not integer-castable.") from exc
        else:
            try:
                prediction_value = float(pred_value)
            except (TypeError, ValueError) as exc:
                raise PredictionError("Regression prediction is not numeric.") from exc
        results.append(
            PredictionResult(
                area_id=int(row["area_id"]),
                forecast_timestamp=str(row["forecast_timestamp"]),
                task=task,
                prediction=prediction_value,
                probability=None if prob is None else float(prob),
                feature_values={
                    column: float(row[column]) for column in MODEL_FEATURE_COLUMNS
                },
            )
        )
    return results
