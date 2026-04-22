#!/usr/bin/env bash
# run_all_benchmarks.sh
# Runs all serving option benchmarks and produces results/summary.csv
# Usage: ./run_all_benchmarks.sh <CLASSIFIER_HOST> <GENERATOR_HOST>
#   e.g. ./run_all_benchmarks.sh 192.5.87.10 192.5.87.10

set -euo pipefail

CLASSIFIER_HOST="${1:-localhost}"
GENERATOR_HOST="${2:-localhost}"
N=200
OUT="results/summary.csv"
mkdir -p results

echo "=== Benchmarking Serving Options ==="

# ── Classifier options ──────────────────────────────────────────────────────
echo "[1/4] Classifier: baseline_pytorch (port 8001)"
python benchmark.py \
  --url "http://${CLASSIFIER_HOST}:8001/predict" \
  --endpoint classifier \
  --concurrency 1 5 10 17 \
  --n ${N} \
  --label "classifier_pytorch_baseline" \
  --out "${OUT}"

echo "[2/4] Classifier: onnx (port 8002)"
python benchmark.py \
  --url "http://${CLASSIFIER_HOST}:8002/predict" \
  --endpoint classifier \
  --concurrency 1 5 10 17 \
  --n ${N} \
  --label "classifier_onnx" \
  --out "${OUT}"

echo "[3/4] Classifier: quantized_int8 (port 8003)"
python benchmark.py \
  --url "http://${CLASSIFIER_HOST}:8003/predict" \
  --endpoint classifier \
  --concurrency 1 5 10 17 \
  --n ${N} \
  --label "classifier_quantized_int8" \
  --out "${OUT}"

# ── Generator options ────────────────────────────────────────────────────────
echo "[4/4] Generator: flan-t5-base GPU (port 8010)"
python benchmark.py \
  --url "http://${GENERATOR_HOST}:8010/generate" \
  --endpoint generator \
  --concurrency 1 2 4 \
  --n 50 \
  --label "generator_flan_t5_gpu" \
  --out "${OUT}"

echo ""
echo "All benchmarks complete. Results in ${OUT}"
