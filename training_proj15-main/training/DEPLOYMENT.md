# Training Deployment Notes

This training code is intended to run either in containers locally or through the Kubernetes jobs in `k8s/training/`.

## Environment

- `MLFLOW_TRACKING_URI`
- `MLFLOW_S3_ENDPOINT_URL`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_S3_FORCE_PATH_STYLE=true`

## Build examples

```bash
docker build -f training/Dockerfile -t tone-train ./training
docker build -f training/Dockerfile.llm -t llm-train ./training
```

## Manifest-backed retraining

To tie retraining to the latest batch dataset instead of only the local seed files:

1. Prepare a batch bundle under `batch/latest/` in MinIO or on disk with at least `manifest.json`.
2. Export `DATASET_MANIFEST_PATH` to the generated `dataset_manifest.json`.
3. Run `prepare_training_data.py` before `train.py` or `train_llm.py`.

Example on a VM after syncing `batch/latest/` and `feedback/` locally:

```bash
python training/prepare_training_data.py \
  --batch-root /data/batch/latest \
  --feedback-dir /data/feedback \
  --output-dir /tmp/training_data

export DATASET_MANIFEST_PATH=/tmp/training_data/dataset_manifest.json
export GENERATOR_EVAL_PATH=/tmp/training_data/generator_eval.jsonl
python training/train.py --config training/configs/candidate_tone_distilbert.yaml
python training/train_llm.py --config training/configs/llm_generator_small.yaml
```

The generated manifest reports how many rows came from live feedback versus curated seed data. That makes the training pipeline more honest about whether it is really learning from production behavior or mostly replaying bootstrap examples.

## Course submission (Q2)
## Cluster path

The normal cluster path is:

1. data prepared in `ml-data`
2. classifier and generator training jobs in `ml-training`
3. registry job assigns aliases
4. serving loads models by alias

For current operational usage, prefer the Kubernetes path documented in [k8s/training/README.md](C:\Users\sudha\OneDrive\Desktop\MLOps\Multi-Tone-Communication-Assistant-for-Zulip---MLOps\k8s\training\README.md).
