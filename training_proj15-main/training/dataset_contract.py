from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def resolve_path(base_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else (base_dir / path).resolve()


def load_dataset_manifest(base_dir: Path, data_cfg: dict[str, Any]) -> dict[str, Any] | None:
    manifest_path = data_cfg.get("dataset_manifest_path")
    if not manifest_path:
        return None
    resolved = resolve_path(base_dir, str(manifest_path))
    manifest = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("dataset manifest must be a JSON object")
    return {"path": resolved, "manifest": manifest}


def resolve_manifest_artifact(
    manifest_bundle: dict[str, Any] | None,
    *,
    artifact_name: str,
    required_fields: tuple[str, ...],
) -> dict[str, Any] | None:
    if manifest_bundle is None:
        return None
    manifest = manifest_bundle["manifest"]
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("dataset manifest must include an artifacts object")
    artifact = artifacts.get(artifact_name)
    if not isinstance(artifact, dict):
        raise ValueError(f"dataset manifest missing artifacts.{artifact_name}")
    missing = [field for field in required_fields if not artifact.get(field)]
    if missing:
        raise ValueError(
            f"dataset manifest artifacts.{artifact_name} missing required fields: {', '.join(missing)}"
        )
    return artifact


def manifest_lineage(manifest_bundle: dict[str, Any], artifact_name: str) -> dict[str, Any]:
    manifest = manifest_bundle["manifest"]
    artifact = manifest.get("artifacts", {}).get(artifact_name, {})
    return {
        "dataset_manifest_path": str(manifest_bundle["path"]),
        "dataset_manifest_version": manifest.get("batch_version", "unknown"),
        "dataset_manifest_created_at": manifest.get("created_at", "unknown"),
        "dataset_artifact_name": artifact_name,
        "dataset_artifact": artifact,
    }
