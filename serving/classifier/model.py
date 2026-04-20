"""
Tone classifier model loader — PyTorch baseline.

DUMMY_MODE (default=true):
  Returns deterministic fake probabilities based on simple heuristics.
  No model download required. Use this for serving benchmarks.

Real mode (DUMMY_MODE=false):
  Loads DistilBERT from MODEL_PATH. Swap in once training team delivers
  a fine-tuned checkpoint.

Switch:  DUMMY_MODE=false  MODEL_PATH=/mnt/model

Automated handoff (optional):
  Preferred: set CLASSIFIER_MODEL_URI=models:/<registered_name>@<alias>
  Optional fallback: set MLFLOW_RUN_ID (+ MLFLOW_TRACKING_URI) to download
  a run artifact folder. This removes manual unzip/copy from training to serving.
"""

import os
import time
import logging
import random
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

LABELS = ["formal", "friendly", "neutral"]
DUMMY_MODE = os.environ.get("DUMMY_MODE", "true").lower() != "false"
MODEL_PATH = os.environ.get("MODEL_PATH", "distilbert-base-uncased")
CLASSIFIER_MODEL_URI = os.environ.get("CLASSIFIER_MODEL_URI", "").strip()
MLFLOW_RUN_ID = os.environ.get("MLFLOW_RUN_ID", "").strip()
MLFLOW_ARTIFACT_PATH = os.environ.get("MLFLOW_ARTIFACT_PATH", "model").strip() or "model"
MLFLOW_DOWNLOAD_DIR = os.environ.get("MLFLOW_DOWNLOAD_DIR", "/tmp/mlflow_artifacts").strip()
MAX_LEN = 128


def _resolve_model_path() -> str:
    if not CLASSIFIER_MODEL_URI and not MLFLOW_RUN_ID:
        return MODEL_PATH
    try:
        import mlflow
        from mlflow.tracking import MlflowClient

        tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        target_dir = Path(MLFLOW_DOWNLOAD_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        if CLASSIFIER_MODEL_URI:
            downloaded = mlflow.artifacts.download_artifacts(
                artifact_uri=CLASSIFIER_MODEL_URI,
                dst_path=str(target_dir),
            )
            logger.info(
                "Downloaded classifier model via registry uri=%s -> %s",
                CLASSIFIER_MODEL_URI,
                downloaded,
            )
        else:
            client = MlflowClient()
            downloaded = client.download_artifacts(
                run_id=MLFLOW_RUN_ID,
                path=MLFLOW_ARTIFACT_PATH,
                dst_path=str(target_dir),
            )
            logger.info(
                "Downloaded classifier artifact from MLflow run=%s path=%s -> %s",
                MLFLOW_RUN_ID,
                MLFLOW_ARTIFACT_PATH,
                downloaded,
            )
        return downloaded
    except Exception as exc:
        logger.exception(
            "Failed to resolve classifier model from MLflow (model_uri=%s run_id=%s path=%s)",
            CLASSIFIER_MODEL_URI,
            MLFLOW_RUN_ID,
            MLFLOW_ARTIFACT_PATH,
        )
        raise RuntimeError("Unable to resolve MODEL_PATH from MLflow") from exc


class _DummyClassifier:
    """Deterministic stub — exercises full API without any model download."""

    # Simple keyword heuristics so outputs are at least plausible
    _FORMAL_WORDS = {"please", "could", "would", "kindly", "regarding", "dear", "sincerely"}
    _FRIENDLY_WORDS = {"thanks", "hey", "awesome", "great", "appreciate", "sure", "happy"}

    def predict(self, text: str) -> dict:
        t0 = time.perf_counter()
        tokens = set(text.lower().split())
        # Simulate ~40-80 ms CPU inference time
        time.sleep(random.uniform(0.04, 0.08))
        formal_score = len(tokens & self._FORMAL_WORDS) + 0.1
        friendly_score = len(tokens & self._FRIENDLY_WORDS) + 0.1
        neutral_score = 0.5
        total = formal_score + friendly_score + neutral_score
        probs = [
            round(formal_score / total, 4),
            round(friendly_score / total, 4),
            round(neutral_score / total, 4),
        ]
        # Normalise to exactly 1.0
        probs[2] = round(1.0 - probs[0] - probs[1], 4)
        predicted = LABELS[int(np.argmax(probs))]
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "predicted_tone": predicted,
            "probabilities": {label: p for label, p in zip(LABELS, probs)},
            "confidence": round(max(probs), 4),
            "latency_ms": round(latency_ms, 2),
        }


class _RealClassifier:
    """PyTorch DistilBERT classifier (CPU). Requires MODEL_PATH."""

    def __init__(self):
        import torch
        from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification
        resolved_path = _resolve_model_path()
        logger.info("Loading tokenizer from %s", resolved_path)
        self.tokenizer = DistilBertTokenizerFast.from_pretrained(resolved_path)
        logger.info("Loading model from %s", resolved_path)
        self.model = DistilBertForSequenceClassification.from_pretrained(
            resolved_path, num_labels=3, ignore_mismatched_sizes=True
        )
        self.model.eval()
        self._torch = torch
        logger.info("Real PyTorch classifier ready")

    def predict(self, text: str) -> dict:
        t0 = time.perf_counter()
        inputs = self.tokenizer(
            text, return_tensors="pt", truncation=True, max_length=MAX_LEN, padding=True
        )
        with self._torch.no_grad():
            logits = self.model(**inputs).logits
        probs = self._torch.softmax(logits, dim=-1).squeeze().tolist()
        latency_ms = (time.perf_counter() - t0) * 1000
        predicted = LABELS[int(np.argmax(probs))]
        return {
            "predicted_tone": predicted,
            "probabilities": {label: round(p, 4) for label, p in zip(LABELS, probs)},
            "confidence": round(max(probs), 4),
            "latency_ms": round(latency_ms, 2),
        }


class ToneClassifier:
    """Factory: returns dummy or real classifier based on DUMMY_MODE env var."""

    def __new__(cls):
        if DUMMY_MODE:
            logger.info("Classifier starting in DUMMY_MODE (no model download)")
            return _DummyClassifier()
        logger.info("Classifier starting in REAL mode (MODEL_PATH=%s)", MODEL_PATH)
        return _RealClassifier()
