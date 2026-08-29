"""Simple, reproducible baseline training for prepared ML datasets."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Literal

from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from services.ml_dataset import ChronologicalSplit, DatasetValidationError, PreparedDataset, chronological_split


TaskType = Literal["classification", "regression"]


class TrainingError(ValueError):
    """Raised when a baseline cannot be trained or evaluated safely."""


@dataclass(frozen=True)
class TrainingResult:
    """A fitted reusable preprocessing/model pipeline and split metrics."""

    task: TaskType
    model: Pipeline
    split: ChronologicalSplit
    metrics: dict[str, dict[str, Any]]


def _classification_metrics(model: Pipeline, dataset: PreparedDataset, labels: list[Any]) -> dict[str, Any]:
    predictions = model.predict(dataset.X)
    return {
        "accuracy": float(accuracy_score(dataset.y, predictions)),
        "precision": float(precision_score(dataset.y, predictions, average="weighted", zero_division=0)),
        "recall": float(recall_score(dataset.y, predictions, average="weighted", zero_division=0)),
        "f1": float(f1_score(dataset.y, predictions, average="weighted", zero_division=0)),
        "confusion_matrix": confusion_matrix(dataset.y, predictions, labels=labels).tolist(),
    }


def _regression_metrics(model: Pipeline, dataset: PreparedDataset) -> dict[str, Any]:
    predictions = model.predict(dataset.X)
    result = {
        "mae": float(mean_absolute_error(dataset.y, predictions)),
        "rmse": float(sqrt(mean_squared_error(dataset.y, predictions))),
        "r2": None,
    }
    if len(dataset.y) >= 2:
        result["r2"] = float(r2_score(dataset.y, predictions))
    return result


def train_baseline(dataset: PreparedDataset, *, task: TaskType) -> TrainingResult:
    """Chronologically split, fit, and evaluate an interpretable baseline.

    Classification uses scaled logistic regression; regression uses scaled
    ridge regression.  The fitted pipeline owns the exact preprocessing needed
    for a future inference integration.  No artifact is written to disk.
    """
    if task not in ("classification", "regression"):
        raise TrainingError("task must be either 'classification' or 'regression'.")
    try:
        split = chronological_split(dataset)
    except DatasetValidationError as exc:
        raise TrainingError(str(exc)) from exc
    if len(split.train.X) < 2:
        raise TrainingError("Training requires at least two chronological training rows.")
    if task == "classification":
        labels = sorted(set(dataset.y), key=str)
        if len(set(split.train.y)) < 2:
            raise TrainingError("Classification training requires at least two target classes in the training period.")
        estimator = LogisticRegression(max_iter=1000, random_state=42)
    else:
        try:
            tuple(float(value) for value in dataset.y)
        except (TypeError, ValueError) as exc:
            raise TrainingError("Regression training requires numeric targets.") from exc
        labels = []
        estimator = Ridge(alpha=1.0)

    model = Pipeline([("scaler", StandardScaler()), ("model", estimator)])
    model.fit(split.train.X, split.train.y)
    if task == "classification":
        metrics = {
            "train": _classification_metrics(model, split.train, labels),
            "validation": _classification_metrics(model, split.validation, labels),
            "test": _classification_metrics(model, split.test, labels),
        }
    else:
        metrics = {
            "train": _regression_metrics(model, split.train),
            "validation": _regression_metrics(model, split.validation),
            "test": _regression_metrics(model, split.test),
        }
    return TrainingResult(task=task, model=model, split=split, metrics=metrics)
