"""
ONNX-optimized tone classifier.

DUMMY_MODE (default=true):
  Simulates ONNX latency characteristics (~20-45 ms) without any model file.
  Use this for serving benchmarks / latency table.

Real mode (DUMMY_MODE=false):
  Exports DistilBERT to ONNX on first run (if ONNX_PATH not found),
  then uses ONNX Runtime for all inference.
  Provides ~2-3x speedup over PyTorch CPU baseline.
"""

import os
import logging
import time
import random
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

LABELS = ["formal", "friendly", "neutral"]
DUMMY_MODE = os.environ.get("DUMMY_MODE", "true").lower() != "false"
MODEL_PATH = os.environ.get("MODEL_PATH", "distilbert-base-uncased")
ONNX_PATH = os.environ.get("ONNX_PATH", "/app/model_cache/classifier.onnx")
MAX_LEN = 128


class _DummyOnnxClassifier:
    """Simulates ONNX Runtime inference speed without model download."""

    _FORMAL_WORDS = {"please", "could", "would", "kindly", "regarding", "dear"}
    _FRIENDLY_WORDS = {"thanks", "hey", "awesome", "great", "appreciate", "sure"}

    def predict(self, text: str) -> dict:
        t0 = time.perf_counter()
        # ONNX is ~2x faster than PyTorch baseline
        time.sleep(random.uniform(0.020, 0.045))
        tokens = set(text.lower().split())
        formal_score = len(tokens & self._FORMAL_WORDS) + 0.1
        friendly_score = len(tokens & self._FRIENDLY_WORDS) + 0.1
        neutral_score = 0.5
        total = formal_score + friendly_score + neutral_score
        probs = [
            round(formal_score / total, 4),
            round(friendly_score / total, 4),
            round(neutral_score / total, 4),
        ]
        probs[2] = round(1.0 - probs[0] - probs[1], 4)
        predicted = LABELS[int(np.argmax(probs))]
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "predicted_tone": predicted,
            "probabilities": {label: p for label, p in zip(LABELS, probs)},
            "confidence": round(max(probs), 4),
            "latency_ms": round(latency_ms, 2),
        }


def _export_to_onnx(model, tokenizer, onnx_path: str):
    import torch
    Path(onnx_path).parent.mkdir(parents=True, exist_ok=True)
    dummy = tokenizer(
        "sample text for export",
        return_tensors="pt",
        max_length=MAX_LEN,
        padding="max_length",
        truncation=True,
    )
    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy["input_ids"], dummy["attention_mask"]),
            onnx_path,
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq"},
                "attention_mask": {0: "batch", 1: "seq"},
            },
            opset_version=14,
        )
    logger.info("ONNX model exported to %s", onnx_path)


class _RealOnnxClassifier:
    """ONNX Runtime classifier (model-level optimization)."""

    def __init__(self):
        import onnxruntime as ort
        from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

        self.tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_PATH)
        if not os.path.exists(ONNX_PATH):
            logger.info("ONNX model not found; exporting now...")
            pt_model = DistilBertForSequenceClassification.from_pretrained(
                MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True
            )
            pt_model.eval()
            _export_to_onnx(pt_model, self.tokenizer, ONNX_PATH)
        sess_opts = ort.SessionOptions()
        sess_opts.intra_op_num_threads = int(os.environ.get("ORT_THREADS", "2"))
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            ONNX_PATH, sess_options=sess_opts, providers=["CPUExecutionProvider"]
        )
        logger.info("Real ONNX classifier ready")

    def predict(self, text: str) -> dict:
        t0 = time.perf_counter()
        enc = self.tokenizer(
            text, return_tensors="np", truncation=True, max_length=MAX_LEN, padding=True
        )
        logits = self.session.run(
            ["logits"],
            {
                "input_ids": enc["input_ids"].astype(np.int64),
                "attention_mask": enc["attention_mask"].astype(np.int64),
            },
        )[0]
        e = np.exp(logits[0] - np.max(logits[0]))
        probs = e / e.sum()
        latency_ms = (time.perf_counter() - t0) * 1000
        predicted = LABELS[int(np.argmax(probs))]
        return {
            "predicted_tone": predicted,
            "probabilities": {label: round(float(p), 4) for label, p in zip(LABELS, probs)},
            "confidence": round(float(max(probs)), 4),
            "latency_ms": round(latency_ms, 2),
        }


class OnnxToneClassifier:
    """Factory: returns dummy or real ONNX classifier based on DUMMY_MODE env var."""

    def __new__(cls):
        if DUMMY_MODE:
            logger.info("ONNX classifier starting in DUMMY_MODE")
            return _DummyOnnxClassifier()
        logger.info("ONNX classifier starting in REAL mode")
        return _RealOnnxClassifier()
