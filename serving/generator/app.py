"""
Tone Generator Microservice — FastAPI
Calls the classifier first, then generates 3 tone variants.

  POST /generate   → full pipeline (classify + generate all 3 variants)
  GET  /health     → liveness check
  GET  /metrics    → Prometheus metrics

CLASSIFIER_URL env var: URL of the classifier service (default: http://classifier:8001)
"""

import os
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from audit_log import log_generator_audit
from model import ToneGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CLASSIFIER_URL = os.environ.get("CLASSIFIER_URL", "http://classifier:8001")
LATENCY_BUDGET_MS = float(os.environ.get("LATENCY_BUDGET_MS", "600"))

REQUEST_COUNT = Counter("generator_requests_total", "Total generator requests", ["status"])
LATENCY_HIST = Histogram(
    "generator_latency_seconds",
    "Generator inference latency",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0, 1.5, 2.0],
)
FEEDBACK_COUNT = Counter(
    "generator_feedback_total",
    "User feedback signals for generator outputs",
    ["user_action", "tone_shown"],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    message_id: str = Field(..., example="msg_0042")
    text: str = Field(..., min_length=1, max_length=2000,
                      example="yo can u just fix the bug already its been 3 days lol")
    message_type: str = Field(default="stream", example="stream")

class ToneVariant(BaseModel):
    text: str
    confidence: float | None = None

class GenerateResponse(BaseModel):
    message_id: str
    original_text: str
    variants: dict[str, ToneVariant]
    classifier_result: dict
    offensive_content_flagged: bool
    total_latency_ms: float


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
generator = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global generator
    generator = ToneGenerator()
    yield
    generator = None


app = FastAPI(
    title="Tone Generator Service",
    description="LLM-based multi-tone message rewriter (Formal / Friendly / Neutral)",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    if generator is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text field must not be blank")

    t_start = time.perf_counter()

    # Step 1: call classifier sidecar
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            cls_resp = await client.post(
                f"{CLASSIFIER_URL}/predict",
                json={"message_id": request.message_id, "text": text, "message_type": request.message_type},
            )
            cls_resp.raise_for_status()
            cls_result = cls_resp.json()
    except Exception as exc:
        logger.warning("Classifier call failed: %s — proceeding without classifier result", exc)
        cls_result = {"predicted_tone": "unknown", "probabilities": {}, "confidence": 0.0, "latency_ms": 0.0}

    # Step 2: generate tone variants
    try:
        gen_result = generator.generate_all(text)
    except Exception as exc:
        REQUEST_COUNT.labels(status="error").inc()
        logger.exception("Generation error: %s", exc)
        raise HTTPException(status_code=500, detail="Generation error") from exc

    total_ms = (time.perf_counter() - t_start) * 1000
    REQUEST_COUNT.labels(status="ok").inc()
    LATENCY_HIST.observe(total_ms / 1000)

    variants = {
        tone: ToneVariant(text=v["text"])
        for tone, v in gen_result["variants"].items()
    }

    log_generator_audit(
        message_id=request.message_id,
        text=text,
        classifier_result=cls_result,
        variants=gen_result["variants"],
        offensive_content_flagged=gen_result["offensive_content_flagged"],
        total_latency_ms=round(total_ms, 2),
    )

    return GenerateResponse(
        message_id=request.message_id,
        original_text=text,
        variants=variants,
        classifier_result=cls_result,
        offensive_content_flagged=gen_result["offensive_content_flagged"],
        total_latency_ms=round(total_ms, 2),
    )


@app.post("/feedback")
async def generator_feedback(payload: dict):
    """Record user feedback signal. Increments Prometheus counter for Grafana visibility."""
    action = str(payload.get("user_action", "unknown"))
    tone = str(payload.get("tone_shown", "unknown"))
    FEEDBACK_COUNT.labels(user_action=action, tone_shown=tone).inc()
    return {"status": "ok"}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
