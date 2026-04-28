# Deployment notes (Chameleon / MLflow)

## Environment variables

| Variable | Purpose |
|----------|---------|
| `MLFLOW_TRACKING_URI` | Tracking server URL. On the same VM as `mlflow server`: `http://127.0.0.1:5000`. From another host: `http://<FLOATING_IP>:5000`. |
| `GIT_SHA` | Optional; Docker build-arg so runs log `code_version_git_sha`. |

## MLflow server

- Bind for remote access: `--host 0.0.0.0 --port 5000`.
- If the UI reports invalid host or CORS errors, add your public URL (including port) to server flags supported by your MLflow version (`--allowed-hosts`, `--cors-allowed-origins`, etc.).

## Networking

- Open the tracking port (default **5000**) in the cloud security group / firewall.
- Attach the Chameleon **floating IP** to the instance that runs MLflow.
- Docker on the same VM as MLflow often uses `network_mode: host` (see `docker-compose.yml`) so containers can reach `127.0.0.1:5000`.

## Docker images

From repository root:

```bash
docker build --build-arg GIT_SHA="$(git rev-parse HEAD)" -f training/Dockerfile -t tone-train:proj15 ./training
docker build --build-arg GIT_SHA="$(git rev-parse HEAD)" -f training/Dockerfile.llm -t llm-train:proj15 ./training
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

Concrete checklists and file lists: `Q2_COURSE_SUBMISSION.md`, `Q2_2_REPOSITORY_ARTIFACTS.md`, `Q2_1_TRAINING_RUNS_TABLE_FILLED.md`.
