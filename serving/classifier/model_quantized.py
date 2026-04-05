"""
INT8 quantized tone classifier (model-level optimization).

DUMMY_MODE (default=true):
  Simulates INT8 quantized latency (~30-55 ms, fast and low RAM) without
  any model download. Use this for serving benchmarks.

Real mode (DUMMY_MODE=false):
  Applies dynamic INT8 quantization to DistilBERT linear layers.
  Reduces model size ~4x, speeds up CPU inference.
"""

import os
import logging
import time
import random
import numpy as np

logger = logging.getLogger(__name__)

LABELS = ["formal", "friendly", "neutral"]
DUMMY_MODE = os.environ.get("DUMMY_MODE", "true").lower() != "false"
MODEL_PATH = os.environ.get("MODEL_PATH", "distilbert-base-uncased")
MAX_LEN = 128


class _DummyQuantizedClassifier:
    """Simulates INT8 quantized inference: faster than ONNX, much smaller RAM."""

    _FORMAL_WORDS = {"please", "could", "would", "kindly", "regarding", "dear"}
    _FRIENDLY_WORDS = {"thanks", "hey", "awesome", "great", "appreciate", "sure"}

    def predict(self, text: str) -> dict:
        t0 = time.perf_counter()
        # INT8 quantized — slightly slower than ONNX but uses ~4x less RAM
        time.sleep(random.uniform(0.030, 0.055))
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


class _RealQuantizedClassifier:
    """Dynamic INT8 quantized DistilBERT classifier."""

    def __init__(self):
        import torch
        from torch.quantization import quantize_dynamic
        from transformers import DistilBertTokenizerFast, DistilBertForSequenceClassification

        self.tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_PATH)
        base = DistilBertForSequenceClassification.from_pretrained(
            MODEL_PATH, num_labels=3, ignore_mismatched_sizes=True
        )
        base.eval()
        self.model = quantize_dynamic(base, {torch.nn.Linear}, dtype=torch.qint8)
        self._torch = torch
        logger.info("Real INT8 quantized classifier ready")

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


class QuantizedToneClassifier:
    """Factory: returns dummy or real quantized classifier based on DUMMY_MODE env var."""

    def __new__(cls):
        if DUMMY_MODE:
            logger.info("Quantized classifier starting in DUMMY_MODE")
            return _DummyQuantizedClassifier()
        logger.info("Quantized classifier starting in REAL mode")
        return _RealQuantizedClassifier()
