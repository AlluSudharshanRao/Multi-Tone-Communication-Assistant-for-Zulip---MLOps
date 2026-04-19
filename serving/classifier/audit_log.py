"""Optional one-line JSON audit logs for log pipelines (low-PII by default)."""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_AUDIT = os.environ.get("SERVING_AUDIT_LOG", "false").lower() == "true"
_INCLUDE_TEXT = os.environ.get("SERVING_AUDIT_LOG_INCLUDE_TEXT", "false").lower() == "true"
_TEXT_SNIPPET_MAX = int(os.environ.get("SERVING_AUDIT_LOG_TEXT_MAX", "48"))


def log_classifier_audit(
    *,
    message_id: str,
    text: str,
    predicted_tone: str,
    confidence: float,
    backend: str,
    inference_latency_ms: float,
) -> None:
    if not _AUDIT:
        return
    row: dict = {
        "serving_audit": True,
        "service": "classifier",
        "message_id": message_id,
        "predicted_tone": predicted_tone,
        "confidence": confidence,
        "backend": backend,
        "inference_latency_ms": inference_latency_ms,
        "text_char_len": len(text),
    }
    if _INCLUDE_TEXT and text:
        row["text_snippet"] = text[:_TEXT_SNIPPET_MAX]
    logger.info("%s", json.dumps(row, separators=(",", ":"), ensure_ascii=False))
