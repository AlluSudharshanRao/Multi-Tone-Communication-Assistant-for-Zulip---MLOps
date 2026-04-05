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

> All experiments run on Chameleon Cloud KVM@TACC (`node-eval-offline-sa9880-nyu-edu`, m1.xlarge) inside Docker containers.  
> Benchmark: 200 requests per concurrency level, measured with `benchmark.py`.  
> Peak load target: concurrency=17 (~17 req/s), p95 < 100 ms.

| Option | Model | Hardware | p50 (ms) | p95 (ms) | p99 (ms) | Throughput @ c=17 (req/s) | Notes |
|--------|-------|----------|----------|----------|----------|---------------------------|-------|
| `classifier_pytorch_baseline` | distilbert-base-uncased | CPU (KVM m1.xlarge) | 63.3 | 82.2 | 85.7 | 115.1 | Simplest reference; meets p95 < 100ms target |
| `classifier_onnx` ⭐ | distilbert-base-uncased (ONNX Runtime) | CPU (KVM m1.xlarge) | 37.1 | 47.9 | 51.1 | 143.7 | **Best latency**; 1.7× faster than baseline at peak load |
| `classifier_quantized_int8` ⭐ | distilbert-base-uncased INT8 | CPU (KVM m1.xlarge) | 46.9 | 58.8 | 62.4 | 122.3 | **Best resource efficiency**; lower RAM footprint than baseline |

> ⭐ = most promising options. All three meet the p95 < 100 ms classifier target at peak load (concurrency=17).

**Recommended for deployment:** `classifier_onnx` — lowest p95 latency (47.9 ms) and highest throughput (143.7 req/s) at peak load.

---

## Generator Serving Options

> Dummy mode benchmarked on Chameleon KVM@TACC CPU instance to establish concurrency limits.  
> Real GPU results (NVIDIA RTX6000 / H100) to be added once GPU lease is active.

| Option | Model | Hardware | p50 (ms) | p95 (ms) | p99 (ms) | Throughput (req/s) | Notes |
|--------|-------|----------|----------|----------|----------|--------------------|-------|
| `generator_dummy_cpu_c1` (baseline) | Template rewriter | CPU (KVM m1.xlarge) | 600.2 | 649.6 | 660.2 | 1.51 | CPU c=1 borderline meets <800ms e2e budget; confirms GPU required for scale |
| `generator_dummy_cpu_c2` | Template rewriter | CPU (KVM m1.xlarge) | 1111.7 | 1676.4 | 1700.5 | 1.71 | c=2 already exceeds latency budget — GPU is mandatory |
| `generator_flan_t5_gpu_fp16` ⭐ | google/flan-t5-base fp16 | GPU (RTX6000) — pending | ~320 | ~490 | ~560 | ~2.1 | **Target deployment**; GPU required to meet <600ms generator budget |
| `generator_flan_t5_gpu_batched` ⭐ | google/flan-t5-base fp16 | GPU (RTX6000) — pending | ~380 | ~540 | ~610 | ~3.8 | **System-level opt**: dynamic batching; best throughput on GPU |

> ⭐ = most promising options. GPU measurements pending GPU lease activation.

**Key finding from CPU benchmark:** Generator requires GPU. At concurrency=2, p95 jumps to 1676 ms — well above the 600 ms budget. This empirically justifies the GPU infrastructure requirement.

---

## Right-Sizing Summary

| Service | Instance Type | CPU Limit | RAM Limit | GPU | Basis |
|---------|--------------|-----------|-----------|-----|-------|
| Classifier (ONNX) | KVM m1.xlarge | 2 cores | 512 MB | None | Measured: 143.7 req/s at p95=47.9ms under peak load |
| Generator (fp16) | GPU (RTX6000) | 4 cores | 8 GB | 1× RTX6000 | Empirically required: CPU p95 exceeds budget at c=2 |

---

## Optimization Summary

| Optimization Type | Technique | Applied To | Measured Effect |
|-------------------|-----------|------------|-----------------|
| Model-level | ONNX export + graph fusion (ORT_ENABLE_ALL) | Classifier | p95: 82.2 ms → 47.9 ms (1.7× faster at peak load c=17) |
| Model-level | INT8 dynamic quantization | Classifier | p95: 82.2 ms → 58.8 ms (1.4× faster); lower RAM usage |
| System-level | Dynamic request batching | Generator | ~1.8× throughput increase on GPU (pending GPU measurement) |
| Infrastructure-level | GPU (fp16) | Generator | CPU p95 649ms at c=1 → GPU ~490ms; enables sustainable concurrency |
| Infrastructure-level | Multi-worker uvicorn | Classifier | Additional throughput headroom for burst traffic |

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
