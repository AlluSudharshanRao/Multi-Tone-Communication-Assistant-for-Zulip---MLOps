# training_proj15

ML training for Chameleon Cloud: **tone classifier** (`training/train.py`) and **LoRA LLM generator** (`training/train_llm.py`). API samples: `samples/`.

## Quick start

```bash
# Tone (sklearn / DistilBERT)
docker build --build-arg GIT_SHA="$(git rev-parse HEAD)" -f training/Dockerfile -t tone-train:proj15 ./training
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000   # adjust for your setup
docker run --rm --network host -e MLFLOW_TRACKING_URI tone-train:proj15 --config /app/configs/baseline_tone_nb.yaml

# LLM (LoRA)
docker build --build-arg GIT_SHA="$(git rev-parse HEAD)" -f training/Dockerfile.llm -t llm-train:proj15 ./training
docker run --rm --network host -e MLFLOW_TRACKING_URI llm-train:proj15 --config /app/configs/llm_generator_small.yaml
```

Compose (Linux / Chameleon): `docker compose -f training/docker-compose.yml build` then `run` services `tone-train` / `llm-train`.

## Layout

| Path | Content |
|------|---------|
| `training/train.py` | Classifier: YAML config, sklearn + optional DistilBERT, Optuna, MLflow |
| `training/train_llm.py` | Generator: LoRA SFT, MLflow |
| `training/configs/*.yaml` | Training configurations |
| `training/Dockerfile` | Classifier image |
| `training/Dockerfile.llm` | LLM image |
| `training/Dockerfile.dev` | Dev image (optional) |
| `training/docker-compose.yml` | `tone-train` + `llm-train`, host network |

## Documentation

| Document | Description |
|----------|-------------|
| [training/DEPLOYMENT.md](training/DEPLOYMENT.md) | MLflow, firewall, Docker |
| [training/Q2_COURSE_SUBMISSION.md](training/Q2_COURSE_SUBMISSION.md) | Course Q2 checklist |
| [training/Q2_2_REPOSITORY_ARTIFACTS.md](training/Q2_2_REPOSITORY_ARTIFACTS.md) | Artifact upload list |
| [training/Q2_1_TRAINING_RUNS_TABLE_FILLED.md](training/Q2_1_TRAINING_RUNS_TABLE_FILLED.md) | Q2.1 table draft |
| `DOCS/` | Course PDFs |

## Rubric alignment (summary)

- Training via **Docker** on Chameleon; **MLflow** tracking.
- **Config-driven** (`train.py` / `train_llm.py` + YAML); **Optuna** where enabled for sklearn.
- Submission details: `Q2_COURSE_SUBMISSION.md`.
