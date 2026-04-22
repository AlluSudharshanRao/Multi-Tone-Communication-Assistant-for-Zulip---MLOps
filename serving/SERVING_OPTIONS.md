# Serving Options

This file is a lightweight reference for the supported serving modes in the repo.

## Classifier options

- PyTorch serving path
- optional ONNX backend
- optional quantized backend

The current integrated Zulip path uses the PyTorch classifier deployments in `staging`, `canary`, and `prod`.

## Generator options

- dummy mode for lightweight integration and fallback behavior
- seq2seq real mode
- causal or LoRA-backed real mode when configured

The current cluster uses the tiered generator deployments under `k8s/inference/`.

## Practical recommendation

- use `staging` for low-risk validation
- use `canary` for pre-production checks
- use `prod` for the Zulip bridge target

## Important tradeoff

The current generator quality improvements rely partly on fallback cleanup logic. That improves bad outputs noticeably, but it is not a substitute for better training data or a stronger model.
