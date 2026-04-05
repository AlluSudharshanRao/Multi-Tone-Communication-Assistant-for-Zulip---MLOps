# Tone Generator Service
# Build:  docker build -t tone-generator .
# Run (dummy mode, no GPU needed — default):
#   docker run -p 8010:8010 tone-generator
#
# Run (real LLM on GPU):
#   docker run --gpus all \
#     -e DUMMY_MODE=false \
#     -e MODEL_NAME=google/flan-t5-base \
#     -e CLASSIFIER_URL=http://classifier:8001 \
#     -p 8010:8010 tone-generator

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install core deps only (no torch in dummy mode)
RUN pip install --no-cache-dir \
    fastapi==0.111.0 \
    "uvicorn[standard]==0.29.0" \
    pydantic==2.7.1 \
    numpy==1.26.4 \
    prometheus-client==0.20.0 \
    httpx==0.27.0

COPY app.py model.py ./

# Non-root user
RUN useradd -m -u 1000 appuser
USER appuser

ENV DUMMY_MODE=true
ENV MODEL_NAME=google/flan-t5-base
ENV CLASSIFIER_URL=http://classifier:8001
ENV LATENCY_BUDGET_MS=600

EXPOSE 8010

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:8010/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
