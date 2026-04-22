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

## Course submission (Q2)

Concrete checklists and file lists: `Q2_COURSE_SUBMISSION.md`, `Q2_2_REPOSITORY_ARTIFACTS.md`, `Q2_1_TRAINING_RUNS_TABLE_FILLED.md`.
