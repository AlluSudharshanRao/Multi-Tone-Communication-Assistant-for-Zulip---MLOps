# Q2.1 — Training runs table (draft for PDF export)

**Requirement:** Runs must be executed on **Chameleon** inside **Docker**, logged to the **same** MLflow server you submit for Q2.4.

## 1. Set your public MLflow base URL

Replace `FLOATING_IP` everywhere below (and in Word/PDF hyperlinks) with your VM’s floating IP. MLflow defaults to port **5000** (not 80).

```text
BASE = http://FLOATING_IP:5000
```

**Smoke-test before PDF export**

- `{BASE}/` — UI loads  
- `{BASE}/#/experiments` — experiment list  
- `{BASE}/#/experiments/<N>` — open `teamchat_tone_clf` and `teamchat_tone_generator_llm`; note each numeric id `<N>` from the browser URL  

**Run URL pattern**

```text
{BASE}/#/experiments/<EXPERIMENT_ID>/runs/<RUN_UUID>
```

Copy `<RUN_UUID>` from the MLflow UI address bar for each run.

## 1b. All links in one place (replace placeholders)

Set **once:** `FLOATING_IP` = your Chameleon floating IP. In MLflow UI open each experiment and copy the numeric **experiment id** from the URL bar (`#/experiments/<id>`). Open each run and copy **Run ID** (UUID).

| What | URL |
|------|-----|
| MLflow home | `http://FLOATING_IP:5000/` |
| Experiment list | `http://FLOATING_IP:5000/#/experiments` |
| Tone clf experiment (list of runs) | `http://FLOATING_IP:5000/#/experiments/TONE_EXP` |
| LLM generator experiment | `http://FLOATING_IP:5000/#/experiments/LLM_EXP` |
| Run — baseline NB | `http://FLOATING_IP:5000/#/experiments/TONE_EXP/runs/RUN_BASELINE` |
| Run — logistic + Optuna | `http://FLOATING_IP:5000/#/experiments/TONE_EXP/runs/RUN_LR` |
| Run — random forest + Optuna | `http://FLOATING_IP:5000/#/experiments/TONE_EXP/runs/RUN_RF` |
| Run — DistilBERT | `http://FLOATING_IP:5000/#/experiments/TONE_EXP/runs/RUN_DB` |
| Run — LLM LoRA | `http://FLOATING_IP:5000/#/experiments/LLM_EXP/runs/RUN_LLM` |

`TONE_EXP` = id for **`teamchat_tone_clf`**. `LLM_EXP` = id for **`teamchat_tone_generator_llm`**. All four tone candidates usually share the same `TONE_EXP`.

## 2. Table (paste into Word / LaTeX; add hyperlinks after substituting IDs)

| Candidate | MLflow run link | Code version | Key hyperparams | Key model metrics | Key cost metrics | Notes |
|-----------|-----------------|--------------|-----------------|-------------------|------------------|-------|
| baseline — Multinomial NB + TF-IDF | `{BASE}/#/experiments/<TONE_EXP>/runs/<RUN_BASELINE>` | `code_version_git_sha` | `baseline_tone_nb.yaml` | accuracy, f1_macro, f1_* | fit_wall_seconds, fit_samples_per_second, training_gpu_hours | Run name `baseline_tone_multinomial_nb` |
| Logistic + Optuna | `{BASE}/#/experiments/<TONE_EXP>/runs/<RUN_LR>` | tag as above | `candidate_tone_logistic.yaml` | as logged (+ nested optuna) | tuning_wall_seconds, fit_wall_seconds, time_per_solver_iter_seconds | `candidate_tone_logistic` |
| Random forest + Optuna | `{BASE}/#/experiments/<TONE_EXP>/runs/<RUN_RF>` | tag as above | `candidate_tone_random_forest.yaml` | as logged | tuning_wall_seconds, time_per_estimator_seconds, … | `candidate_tone_random_forest` |
| DistilBERT | `{BASE}/#/experiments/<TONE_EXP>/runs/<RUN_DB>` | tag as above | `candidate_tone_distilbert.yaml` | as logged | fit_wall_seconds, cost_avg_epoch_wall_seconds, … | `candidate_tone_distilbert` |
| LLM LoRA | `{BASE}/#/experiments/<LLM_EXP>/runs/<RUN_LLM>` | tag as above | `llm_generator_small.yaml` | last_* (TRL) | train_wall_seconds, cost_avg_epoch_wall_seconds, training_gpu_hours | Experiment `teamchat_tone_generator_llm`; run `smollm2_135m_lora_cpu` |

Highlight the rows you recommend; use **Notes** for quality vs latency vs cost.

## 3. Manager summary (short paragraph under the table)

- Best metric (name it).  
- Best cost/speed at acceptable quality.  
- Next experiment.

## 4. Reproduce (Chameleon)

```bash
export GIT_SHA=$(git rev-parse HEAD) MLFLOW_TRACKING_URI=http://127.0.0.1:5000
docker compose -f training/docker-compose.yml build tone-train llm-train
docker compose -f training/docker-compose.yml run --rm tone-train --config /app/configs/baseline_tone_nb.yaml
# … other tone configs …
docker compose -f training/docker-compose.yml run --rm llm-train --config /app/configs/llm_generator_small.yaml
```

Use `127.0.0.1` only when the client shares the host with MLflow and Docker uses host networking; **PDF links for staff** use `{BASE}` with the floating IP.

---

Export to **PDF** with **tested** hyperlinks per LMS instructions. See also `DEPLOYMENT.md` and `Q2_COURSE_SUBMISSION.md`.
