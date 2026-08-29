"""Minimal on-disk storage for fitted sklearn training pipelines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import joblib
from sklearn.pipeline import Pipeline

from services.ml_training import TaskType


class ArtifactError(ValueError):
    """Raised when a model artifact cannot be saved or loaded."""


def artifact_stem(*, version: str, task: TaskType, target_column: str) -> str:
    """Return a deterministic, versioned filename stem."""
    safe_target = "".join(character if character.isalnum() or character in "-_" else "_" for character in target_column)
    return f"{version}__{task}__{safe_target}"


def artifact_paths(artifact_dir: str | Path, *, version: str, task: TaskType, target_column: str) -> tuple[Path, Path]:
    stem = artifact_stem(version=version, task=task, target_column=target_column)
    directory = Path(artifact_dir)
    return directory / f"{stem}.joblib", directory / f"{stem}.meta.json"


def save_training_artifact(
    pipeline: Pipeline,
    metadata: dict[str, Any],
    *,
    artifact_dir: str | Path,
    version: str,
    task: TaskType,
    target_column: str,
) -> Path:
    """Persist the fitted scaler+estimator pipeline and JSON metadata.

    Database objects are not accepted.  The joblib payload stores only the
    sklearn pipeline plus the small training contract needed to reload it.
    """
    if not isinstance(pipeline, Pipeline) or "scaler" not in pipeline.named_steps or "model" not in pipeline.named_steps:
        raise ArtifactError("Artifact pipeline must contain 'scaler' and 'model' steps.")
    joblib_path, meta_path = artifact_paths(
        artifact_dir, version=version, task=task, target_column=target_column
    )
    joblib_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "sklearn_pipeline": pipeline,
            "feature_names": list(metadata["feature_names"]),
            "target_column": target_column,
            "task": task,
            "artifact_version": version,
        },
        joblib_path,
    )
    meta_path.write_text(_metadata_json(metadata | {"artifact_path": str(joblib_path)}), encoding="utf-8")
    return joblib_path


def load_training_artifact(path: str | Path) -> dict[str, Any]:
    """Load a previously saved pipeline payload."""
    payload = joblib.load(Path(path))
    pipeline = payload.get("sklearn_pipeline")
    if not isinstance(pipeline, Pipeline):
        raise ArtifactError("Artifact does not contain a sklearn pipeline.")
    if "scaler" not in pipeline.named_steps or "model" not in pipeline.named_steps:
        raise ArtifactError("Saved pipeline is missing preprocessing or estimator steps.")
    return payload


def resolve_artifact_path(
    artifact_dir: str | Path,
    *,
    version: str,
    task: TaskType,
    target_column: str,
    fallback_version: Optional[str] = None,
) -> Path:
    """Resolve a saved artifact path by convention, with optional version fallback.

    Search order:
    1. Exact match for the requested (version, task, target_column).
    2. If ``fallback_version`` is set, try that version with the same
       task and target column.
    3. Otherwise, raise :class:`ArtifactError`.

    The returned path is guaranteed to exist on disk.
    """
    directory = Path(artifact_dir)
    joblib_path, _ = artifact_paths(directory, version=version, task=task, target_column=target_column)
    if joblib_path.exists():
        return joblib_path
    if fallback_version is not None:
        fallback_path, _ = artifact_paths(
            directory, version=fallback_version, task=task, target_column=target_column
        )
        if fallback_path.exists():
            return fallback_path
    raise ArtifactError(
        f"No artifact found at {joblib_path}"
        + (
            f" or {artifact_stem(version=fallback_version, task=task, target_column=target_column)}.joblib"
            if fallback_version is not None
            else ""
        )
        + "."
    )


def list_artifacts(artifact_dir: str | Path) -> list[dict[str, Any]]:
    """Return metadata summary for every ``*.joblib`` artifact in ``artifact_dir``.

    Each entry includes the file paths and, when present, the contract fields
    read from the artifact payload.  Missing or corrupt artifacts are skipped
    with no exception so partial directories remain browsable.
    """
    directory = Path(artifact_dir)
    results: list[dict[str, Any]] = []
    if not directory.exists():
        return results
    for joblib_path in sorted(directory.glob("*.joblib")):
        meta_path = joblib_path.parent / (joblib_path.stem + ".meta.json")
        entry: dict[str, Any] = {
            "artifact_path": str(joblib_path),
            "meta_path": str(meta_path) if meta_path.exists() else None,
        }
        try:
            payload = joblib.load(joblib_path)
        except Exception:
            results.append(entry)
            continue
        for key in ("artifact_version", "task", "target_column", "feature_names"):
            if key in payload:
                entry[key] = payload[key]
        results.append(entry)
    return results


def _metadata_json(metadata: dict[str, Any]) -> str:
    return json.dumps(metadata, indent=2, sort_keys=True)
