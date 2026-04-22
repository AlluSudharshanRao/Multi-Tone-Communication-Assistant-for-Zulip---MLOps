"""Optional one-line JSON audit logs for log pipelines (low-PII by default)."""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

_AUDIT = os.environ.get("SERVING_AUDIT_LOG", "false").lower() == "true"
_INCLUDE_TEXT = os.environ.get("SERVING_AUDIT_LOG_INCLUDE_TEXT", "false").lower() == "true"
_TEXT_SNIPPET_MAX = int(os.environ.get("SERVING_AUDIT_LOG_TEXT_MAX", "48"))


def log_generator_audit(
    *,
    message_id: str,
    text: str,
    classifier_result: dict,
    variants: dict[str, dict],
    offensive_content_flagged: bool,
    total_latency_ms: float,
) -> None:
    if not _AUDIT:
        return
    lens = {k: len((variants.get(k) or {}).get("text") or "") for k in ("formal", "friendly", "neutral")}
    row: dict = {
        "serving_audit": True,
        "service": "generator",
        "message_id": message_id,
        "classifier_predicted_tone": classifier_result.get("predicted_tone"),
        "variant_char_len": lens,
        "offensive_content_flagged": offensive_content_flagged,
        "total_latency_ms": total_latency_ms,
        "text_char_len": len(text),
    }
    if _INCLUDE_TEXT and text:
        row["text_snippet"] = text[:_TEXT_SNIPPET_MAX]
    logger.info("%s", json.dumps(row, separators=(",", ":"), ensure_ascii=False))
