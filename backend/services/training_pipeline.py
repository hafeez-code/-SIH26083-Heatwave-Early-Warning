"""Service-layer training workflow for independently labelled historical data.

This module does not reimplement feature engineering, dataset preparation, or
baseline estimators.  It never reads ``HeatwaveRiskAssessment`` and never
writes an artifact unless training on a legitimate labelled dataset succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from sklearn.pipeline import Pipeline

from services.historical_ml_integration import (
    HistoricalMLIntegrationError,
    load_labelled_historical_ml_dataset,
    match_historical_records_to_labels,
    prepare_labelled_historical_ml_dataset,
)
from services.label_preparation import DEFAULT_LABEL_NAME
from services.ml_dataset import (
    DatasetValidationError,
    PreparedDataset,
    RULE_DERIVED_TARGET_COLUMNS,
    TargetValidationError,
)
from services.ml_training import TaskType, TrainingError, TrainingResult, train_baseline
from services.model_artifacts import save_training_artifact


@dataclass(frozen=True)
class TrainingPipelineResult:
    """Evaluation summary and the location of a saved scaler+model pipeline."""

    task: TaskType
    target_column: str
    feature_names: tuple[str, ...]
    metrics: dict[str, dict[str, Any]]
    n_train: int
    n_validation: int
    n_test: int
    train_timestamp_range: tuple[str, str]
    validation_timestamp_range: tuple[str, str]
    test_timestamp_range: tuple[str, str]
    artifact_path: str
    artifact_version: str
    pipeline: Pipeline


def _timestamp_range(dataset: PreparedDataset) -> tuple[str, str]:
    timestamps = [str(item["forecast_timestamp"]) for item in dataset.metadata]
    return min(timestamps), max(timestamps)


def _run_training(
    dataset: PreparedDataset,
    *,
    task: TaskType,
    artifact_dir: str,
    artifact_version: str,
) -> TrainingPipelineResult:
    trained: TrainingResult = train_baseline(dataset, task=task)
    metadata = {
        "task": trained.task,
        "target_column": dataset.target_column,
        "feature_names": list(dataset.feature_names),
        "n_train": len(trained.split.train.X),
        "n_validation": len(trained.split.validation.X),
        "n_test": len(trained.split.test.X),
        "train_timestamp_range": _timestamp_range(trained.split.train),
        "validation_timestamp_range": _timestamp_range(trained.split.validation),
        "test_timestamp_range": _timestamp_range(trained.split.test),
        "metrics": trained.metrics,
        "artifact_version": artifact_version,
        "random_state": 42 if task == "classification" else None,
        "estimator": "LogisticRegression" if task == "classification" else "Ridge",
    }
    artifact_path = save_training_artifact(
        trained.model,
        metadata,
        artifact_dir=artifact_dir,
        version=artifact_version,
        task=trained.task,
        target_column=dataset.target_column,
    )
    return TrainingPipelineResult(
        task=trained.task,
        target_column=dataset.target_column,
        feature_names=dataset.feature_names,
        metrics=trained.metrics,
        n_train=len(trained.split.train.X),
        n_validation=len(trained.split.validation.X),
        n_test=len(trained.split.test.X),
        train_timestamp_range=_timestamp_range(trained.split.train),
        validation_timestamp_range=_timestamp_range(trained.split.validation),
        test_timestamp_range=_timestamp_range(trained.split.test),
        artifact_path=str(artifact_path),
        artifact_version=artifact_version,
        pipeline=trained.model,
    )


def train_prepared_dataset(
    dataset: PreparedDataset,
    *,
    task: TaskType,
    artifact_dir: str,
    artifact_version: str = "v0.15",
) -> TrainingPipelineResult:
    """Train from an already leakage-safe v0.12 dataset and save an artifact."""
    if dataset.target_column in RULE_DERIVED_TARGET_COLUMNS:
        raise TrainingError(
            f"{dataset.target_column!r} is a deterministic rule output and cannot be an ML target."
        )
    return _run_training(
        dataset,
        task=task,
        artifact_dir=artifact_dir,
        artifact_version=artifact_version,
    )


def train_from_historical_records(
    weather_records: Iterable[object],
    label_records: Iterable[object],
    *,
    task: TaskType,
    artifact_dir: str,
    target_column: str = DEFAULT_LABEL_NAME,
    artifact_version: str = "v0.15",
) -> TrainingPipelineResult:
    """Match independent labels, train the v0.12 baseline, and persist the pipeline."""
    if target_column in RULE_DERIVED_TARGET_COLUMNS:
        raise TrainingError(
            f"{target_column!r} is a deterministic rule output and cannot be an ML target."
        )
    try:
        matched = match_historical_records_to_labels(weather_records, label_records)
        dataset = prepare_labelled_historical_ml_dataset(matched, target_column=target_column)
    except (HistoricalMLIntegrationError, TargetValidationError, DatasetValidationError) as exc:
        raise TrainingError(str(exc)) from exc
    return _run_training(
        dataset,
        task=task,
        artifact_dir=artifact_dir,
        artifact_version=artifact_version,
    )


def train_from_database(
    db_session,
    *,
    task: TaskType,
    artifact_dir: str,
    target_column: str = DEFAULT_LABEL_NAME,
    artifact_version: str = "v0.15",
    area_ids: Optional[Sequence[int]] = None,
) -> TrainingPipelineResult:
    """Load persisted historical weather and validated labels, then train."""
    if target_column in RULE_DERIVED_TARGET_COLUMNS:
        raise TrainingError(
            f"{target_column!r} is a deterministic rule output and cannot be an ML target."
        )
    try:
        dataset = load_labelled_historical_ml_dataset(
            db_session, area_ids=area_ids, target_column=target_column
        )
    except (HistoricalMLIntegrationError, TargetValidationError, DatasetValidationError) as exc:
        raise TrainingError(str(exc)) from exc
    return _run_training(
        dataset,
        task=task,
        artifact_dir=artifact_dir,
        artifact_version=artifact_version,
    )
