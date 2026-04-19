# Tone Classifier Service
# Build:  docker build -t tone-classifier .
# Run (dummy mode, no model download — default):
#   docker run -p 8001:8001 tone-classifier
#
# Run (real PyTorch baseline):
#   docker run -e DUMMY_MODE=false -e SERVING_BACKEND=pytorch \
#              -e MODEL_PATH=distilbert-base-uncased -p 8001:8001 tone-classifier
#
# Run (real ONNX):
#   docker run -e DUMMY_MODE=false -e SERVING_BACKEND=onnx \
#              -v /mnt/model:/app/model_cache -p 8001:8001 tone-classifier

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install core deps only (no torch/transformers in dummy mode)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    "uvicorn[standard]==0.29.0" \
    pydantic==2.7.1 \
    numpy==1.26.4 \
    prometheus-client==0.20.0

COPY app.py audit_log.py model.py model_onnx.py model_quantized.py ./

# Non-root user for security
RUN useradd -m -u 1000 appuser
USER appuser

ENV DUMMY_MODE=true
ENV SERVING_BACKEND=pytorch
ENV MODEL_PATH=distilbert-base-uncased
ENV ONNX_PATH=/app/model_cache/classifier.onnx

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
