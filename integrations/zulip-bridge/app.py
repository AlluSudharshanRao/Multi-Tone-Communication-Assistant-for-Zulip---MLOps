"""
HTTP bridge: Zulip outgoing webhook / slash-command style payloads → tone generator /generate.

- Validates optional ZULIP_WEBHOOK_SECRET against body.token (Zulip outgoing webhooks).
- Returns Zulip-compatible JSON: {"content": "..."} for bot replies.
- Rate limit: simple in-process limiter per client IP (demo-grade; use Redis in real prod).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import deque
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GENERATOR_URL = os.environ.get("GENERATOR_URL", "http://tone-generator-prod:8010").rstrip("/")
ZULIP_WEBHOOK_SECRET = os.environ.get("ZULIP_WEBHOOK_SECRET", "").strip()
MAX_MESSAGE_LEN = int(os.environ.get("MAX_MESSAGE_LEN", "2000"))
MAX_BODY_BYTES = int(os.environ.get("MAX_BODY_BYTES", "65536"))
RATE_PER_MINUTE = int(os.environ.get("RATE_PER_MINUTE", "60"))
REDACT_LOGS = os.environ.get("REDACT_LOGS", "true").lower() in ("1", "true", "yes")

app = FastAPI(title="Zulip tone bridge", version="1.0.0")

# --- naive sliding-window rate limit per IP ---
_window: deque[tuple[float, str]] = deque()


def _rate_ok(client_ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - 60.0
    while _window and _window[0][0] < cutoff:
        _window.popleft()
    recent = sum(1 for t, ip in _window if ip == client_ip)
    if recent >= RATE_PER_MINUTE:
        return False
    _window.append((now, client_ip))
    return True


def _redact(s: str, max_len: int = 80) -> str:
    if not s:
        return ""
    s = s.replace("\n", " ")
    return (s[:max_len] + "…") if len(s) > max_len else s


def _extract_user_text(payload: dict[str, Any]) -> tuple[str, str]:
    """Returns (message_id, plain_text_for_model)."""
    # Direct API (curl / tests): same shape as contracts/classifier_input.json
    if "text" in payload and isinstance(payload["text"], str):
        mid = str(payload.get("message_id") or payload.get("id") or "zulip-0")
        return mid, payload["text"].strip()

    # Zulip outgoing webhook / generic bot payload
    msg = payload.get("message")
    if isinstance(msg, dict):
        content = (msg.get("content") or "").strip()
        mid = str(msg.get("id") or payload.get("message_id") or "zulip-0")
        # Strip common leading @**bot** ... mentions (best-effort)
        content = re.sub(r"^\s*@\*\*[^\n]+\*\*\s*", "", content)
        return mid, content.strip()

    data = payload.get("data")
    if isinstance(data, str) and data.strip():
        return str(payload.get("message_id") or "zulip-0"), data.strip()

    raise ValueError("No usable text in payload (expected `text` or `message.content`)")


def _zulip_reply_markdown(gen_json: dict[str, Any]) -> str:
    lines = ["### Tone suggestions", ""]
    variants = gen_json.get("variants") or {}
    for tone, body in variants.items():
        if isinstance(body, dict):
            text = (body.get("text") or "").strip()
        else:
            text = str(body).strip()
        lines.append(f"- **{tone}:** {text}")
    lines.append("")
    cr = gen_json.get("classifier_result") or {}
    tone = cr.get("predicted_tone") or cr.get("label") or "unknown"
    lines.append(f"_Classifier: `{tone}`_")
    return "\n".join(lines)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/zulip/webhook")
async def zulip_webhook(request: Request) -> JSONResponse:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")

    client = request.client.host if request.client else "unknown"
    if not _rate_ok(client):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="invalid JSON") from exc

    if ZULIP_WEBHOOK_SECRET:
        token = str(payload.get("token") or "")
        if token != ZULIP_WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="invalid webhook token")

    try:
        message_id, text = _extract_user_text(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not text:
        return JSONResponse({"content": "_No text to rewrite._"})

    if len(text) > MAX_MESSAGE_LEN:
        text = text[:MAX_MESSAGE_LEN]

    if REDACT_LOGS:
        logger.info("bridge request id=%s text_len=%s", message_id, len(text))
    else:
        logger.info("bridge request id=%s text=%s", message_id, _redact(text))

    gen_payload = {
        "message_id": message_id,
        "text": text,
        "message_type": str(payload.get("message_type") or "stream"),
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client_http:
            r = await client_http.post(
                f"{GENERATOR_URL}/generate",
                json=gen_payload,
            )
            r.raise_for_status()
            gen_json = r.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("generator HTTP error: %s", exc)
        return JSONResponse(
            {"content": f"_Generator error (`{exc.response.status_code}`). Try again later._"},
            status_code=200,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("generator call failed: %s", exc)
        return JSONResponse(
            {"content": "_Tone service temporarily unavailable._"},
            status_code=200,
        )

    return JSONResponse({"content": _zulip_reply_markdown(gen_json)})


@app.post("/generate")
async def proxy_generate(request: Request) -> Response:
    """Passthrough POST body to generator /generate (smoke tests)."""
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    ct = request.headers.get("content-type", "application/json")
    async with httpx.AsyncClient(timeout=120.0) as client_http:
        r = await client_http.post(
            f"{GENERATOR_URL}/generate",
            content=body,
            headers={"Content-Type": ct},
        )
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )
