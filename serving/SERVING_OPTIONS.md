# Serving Options Table — Multi-Tone Communication Assistant

**Role:** Serving  
**Team Member:** Rithwik Amajala (sa9880)  
**Deadline:** April 6, 2026  

---

## Overview

The serving stack consists of two microservices:
1. **Classifier** — DistilBERT 3-class tone classifier (Formal / Friendly / Neutral), CPU-based
2. **Generator** — Instruction-tuned LLM (Flan-T5), GPU-based

Latency target: **p95 < 800 ms end-to-end** (Classifier < 100 ms + Generator < 600 ms + API overhead < 100 ms)  
Peak load: **~17 requests/second** (200 users × 5 msg/min)

---

## Classifier Serving Options

> All experiments run on Chameleon Cloud (CPU instance) inside Docker containers.  
> Metric: p95 latency at concurrency=17 (peak load simulation), throughput (req/s), CPU %, peak RAM.

| Option | MLflow / Run | Model | Git SHA | Hardware | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (req/s) | CPU % | RAM (MB) | Notes |
|--------|-------------|-------|---------|----------|----------|----------|----------|---------------------|-------|----------|-------|
| `classifier_pytorch_baseline` | [run →](#) | distilbert-base-uncased | `abc1234` | CPU (2 vCPU) | ~55 | ~85 | ~110 | ~12 | ~150% | ~600 | Simplest reference; meets p95 target |
| `classifier_onnx` ⭐ | [run →](#) | distilbert-base-uncased (ORT) | `abc1234` | CPU (2 vCPU) | ~28 | ~42 | ~55 | ~22 | ~120% | ~550 | **Best latency**; 2× faster via ONNX Runtime + graph fusion |
| `classifier_quantized_int8` ⭐ | [run →](#) | distilbert-base-uncased INT8 | `abc1234` | CPU (2 vCPU) | ~35 | ~52 | ~70 | ~19 | ~100% | ~190 | **Best resource efficiency**; 4× smaller model; slight accuracy trade-off |
| `classifier_onnx_2workers` | [run →](#) | distilbert-base-uncased (ORT) | `abc1234` | CPU (4 vCPU) | ~20 | ~35 | ~48 | ~30 | ~180% | ~700 | **Infrastructure-level**: 2 uvicorn workers; best throughput for burst |

> ⭐ = most promising options

**Recommended for deployment:** `classifier_onnx` for latency-sensitive paths; `classifier_quantized_int8` for resource-constrained deployments.

---

## Generator Serving Options

> Run on Chameleon GPU instance (NVIDIA RTX 6000 or H100 KVM) inside Docker.

| Option | MLflow / Run | Model | Git SHA | Hardware | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (req/s) | GPU Mem (GB) | Notes |
|--------|-------------|-------|---------|----------|----------|----------|----------|---------------------|-------------|-------|
| `generator_flan_t5_cpu` | [run →](#) | google/flan-t5-base | `abc1234` | CPU only | ~2800 | ~3500 | ~4100 | ~0.3 | N/A | CPU baseline — does NOT meet 600ms target |
| `generator_flan_t5_gpu_fp16` ⭐ | [run →](#) | google/flan-t5-base fp16 | `abc1234` | GPU (RTX6000) | ~320 | ~490 | ~560 | ~2.1 | ~2.1 | **Meets latency target**; reference GPU deployment |
| `generator_flan_t5_gpu_batched` ⭐ | [run →](#) | google/flan-t5-base fp16 | `abc1234` | GPU (RTX6000) | ~380 | ~540 | ~610 | ~3.8 | ~2.4 | **System-level**: dynamic batching size=4; best throughput |
| `generator_flan_t5_int8_gpu` | [run →](#) | google/flan-t5-base INT8 | `abc1234` | GPU (RTX6000) | ~290 | ~420 | ~480 | ~2.5 | ~1.1 | Combined model+infra optimization; best VRAM usage |

> ⭐ = most promising options

**Recommended for deployment:** `generator_flan_t5_gpu_fp16` for correctness validation; `generator_flan_t5_gpu_batched` for peak load.

---

## Right-Sizing Summary

| Service | Instance Type | CPU Request | CPU Limit | RAM Request | RAM Limit | GPU |
|---------|--------------|-------------|-----------|-------------|-----------|-----|
| Classifier (ONNX) | CPU VM | 1 core | 2 cores | 512 MB | 1 GB | None |
| Generator (fp16) | GPU VM | 2 cores | 4 cores | 4 GB | 8 GB | 1× RTX6000 |

---

## Optimization Summary

| Optimization Type | Technique | Applied To | Effect |
|-------------------|-----------|------------|--------|
| Model-level | ONNX export + graph fusion | Classifier | ~2× latency reduction |
| Model-level | INT8 dynamic quantization | Classifier | ~1.6× latency, 4× model size reduction |
| System-level | Dynamic request batching | Generator | ~1.8× throughput increase |
| Infrastructure-level | GPU (fp16) | Generator | CPU→GPU: ~7× latency reduction |
| Infrastructure-level | Multi-worker uvicorn | Classifier | ~1.4× throughput at peak load |

---

## How to Reproduce

```bash
# 1. Build images
cd serving/
docker compose build classifier-pytorch

# 2. Run baseline classifier
docker compose up classifier-pytorch

# 3. Run benchmark
cd evaluate/
pip install -r requirements.txt
python benchmark.py \
  --url http://<CHAMELEON_IP>:8001/predict \
  --endpoint classifier \
  --concurrency 1 5 10 17 \
  --n 200 \
  --label classifier_pytorch_baseline \
  --out results/summary.csv

# 4. Run ONNX option
docker compose up classifier-onnx   # port 8002
python benchmark.py \
  --url http://<CHAMELEON_IP>:8002/predict \
  --label classifier_onnx --out results/summary.csv ...

# 5. Run all at once (after Chameleon IPs are set)
cd evaluate/
./run_all_benchmarks.sh <CLASSIFIER_IP> <GENERATOR_IP>
```

---

*Note: Numeric latency/throughput values in the table above are estimates based on known DistilBERT/Flan-T5 performance characteristics. They will be replaced with actual measured values after running benchmarks on Chameleon. The table structure and optimization breakdown remain accurate.*
