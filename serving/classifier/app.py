"""
Tone Classifier Microservice — FastAPI
Supports three backends via SERVING_BACKEND env var:
  pytorch   – baseline PyTorch CPU (default)
  onnx      – ONNX Runtime (model-level optimization)
  quantized – INT8 dynamic quantization (model-level optimization)

Usage:
  SERVING_BACKEND=pytorch uvicorn app:app --host 0.0.0.0 --port 8001
"""

import os
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKEND = os.environ.get("SERVING_BACKEND", "pytorch").lower()

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter("classifier_requests_total", "Total classifier requests", ["status"])
LATENCY_HIST = Histogram(
    "classifier_latency_seconds",
    "Classifier inference latency",
    buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.5],
)

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class ClassifierRequest(BaseModel):
    message_id: str = Field(..., example="msg_0042")
    text: str = Field(..., min_length=1, max_length=2000, example="yo can u just fix the bug already its been 3 days lol")
    message_type: str = Field(default="stream", example="stream")

class ToneProbabilities(BaseModel):
    formal: float
    friendly: float
    neutral: float

class ClassifierResponse(BaseModel):
    message_id: str
    predicted_tone: str
    probabilities: ToneProbabilities
    confidence: float
    latency_ms: float
    backend: str


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
classifier = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global classifier
    logger.info("Loading classifier backend: %s", BACKEND)
    if BACKEND == "onnx":
        from model_onnx import OnnxToneClassifier
        classifier = OnnxToneClassifier()
    elif BACKEND == "quantized":
        from model_quantized import QuantizedToneClassifier
        classifier = QuantizedToneClassifier()
    else:
        from model import ToneClassifier
        classifier = ToneClassifier()
    logger.info("Classifier ready")
    yield
    classifier = None


app = FastAPI(
    title="Tone Classifier Service",
    description="DistilBERT-based 3-class tone classifier (Formal / Friendly / Neutral)",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "backend": BACKEND}


@app.post("/predict", response_model=ClassifierResponse)
def predict(request: ClassifierRequest):
    if classifier is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # Input sanitization: strip whitespace, reject empty after strip
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text field must not be blank")

    try:
        t_start = time.perf_counter()
        result = classifier.predict(text)
        wall_ms = (time.perf_counter() - t_start) * 1000
        REQUEST_COUNT.labels(status="ok").inc()
        LATENCY_HIST.observe(wall_ms / 1000)
        return ClassifierResponse(
            message_id=request.message_id,
            predicted_tone=result["predicted_tone"],
            probabilities=ToneProbabilities(**result["probabilities"]),
            confidence=result["confidence"],
            latency_ms=result["latency_ms"],
            backend=BACKEND,
        )
    except Exception as exc:
        REQUEST_COUNT.labels(status="error").inc()
        logger.exception("Prediction error: %s", exc)
        raise HTTPException(status_code=500, detail="Inference error") from exc


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
