#!/usr/bin/env python3
"""
Register latest successful training runs in MLflow Model Registry and set aliases.

One-shot usage (defaults align with this repo):
  python register_and_alias_latest.py --tracking-uri https://mlflow.<host> --insecure

If you see SSLCertVerificationError (self-signed cert), either pass --insecure or set:
  MLFLOW_TRACKING_INSECURE_TLS=true   (PowerShell: $env:MLFLOW_TRACKING_INSECURE_TLS='true')

What it does:
  1) Finds latest FINISHED classifier run by experiment/run-name
  2) Finds latest FINISHED generator run by experiment/run-name
  3) Optionally evaluates quality gates (--min-classifier-* / --max-generator-loss)
  4) Registers model versions from run artifacts only if gates pass (or --skip-quality-gates)
  5) Sets aliases (default: canary,prod) on both registered models

Evaluation (rubric): gates are task-specific — classifier: macro F1, accuracy, worst-class F1;
generator: loss cap on eval (preferred) or train loss fallback.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Iterable

import mlflow
from mlflow.entities import Run
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient


def _get_experiment_id(client: MlflowClient, name: str) -> str:
    exp = client.get_experiment_by_name(name)
    if exp is None:
        raise RuntimeError(f"Experiment not found: {name!r}")
    return exp.experiment_id


def _latest_finished_run(client: MlflowClient, experiment_name: str, run_name: str) -> Run:
    exp_id = _get_experiment_id(client, experiment_name)
    runs = client.search_runs(
        experiment_ids=[exp_id],
        filter_string=f"attributes.status = 'FINISHED' and tags.mlflow.runName = '{run_name}'",
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not runs:
        raise RuntimeError(
            f"No FINISHED runs found for experiment={experiment_name!r} run_name={run_name!r}"
        )
    return runs[0]


def _metric_map(run: Run) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in run.data.metrics:
        out[m.key] = float(m.value)
    return out


def _get_metric(metrics: dict[str, float], key: str) -> float | None:
    return metrics.get(key)


def _evaluate_classifier_gates(
    run: Run,
    *,
    min_f1_macro: float | None,
    min_accuracy: float | None,
    min_worst_class_f1: float | None,
) -> tuple[bool, dict[str, float | str]]:
    """Task-specific gates: 3-class tone — macro F1, accuracy, worst-class F1 (fairness)."""
    m = _metric_map(run)
    checks: dict[str, float | str] = {}
    ok = True
    if min_f1_macro is not None:
        v = _get_metric(m, "f1_macro")
        checks["f1_macro"] = v if v is not None else "missing"
        if v is None or v < min_f1_macro:
            ok = False
    if min_accuracy is not None:
        v = _get_metric(m, "accuracy")
        checks["accuracy"] = v if v is not None else "missing"
        if v is None or v < min_accuracy:
            ok = False
    if min_worst_class_f1 is not None:
        per = []
        for label in ("formal", "friendly", "neutral"):
            key = f"f1_{label}"
            fv = _get_metric(m, key)
            if fv is not None:
                per.append(fv)
        if not per:
            checks["worst_class_f1"] = "missing"
            ok = False
        else:
            worst = min(per)
            checks["worst_class_f1"] = worst
            if worst < min_worst_class_f1:
                ok = False
    return ok, checks


def _evaluate_generator_gates(
    run: Run,
    *,
    max_loss: float | None,
    min_reference_token_f1: float | None,
    min_reference_rouge_l_f1: float | None,
    max_copy_rate: float | None,
) -> tuple[bool, dict[str, float | str]]:
    """Prefer rewrite usefulness metrics; fall back to loss if they are not configured."""
    m = _metric_map(run)
    checks: dict[str, float | str] = {}
    passed = True
    if min_reference_token_f1 is not None:
        val = _get_metric(m, "generator_eval.avg_reference_token_f1")
        checks["avg_reference_token_f1"] = val if val is not None else "missing"
        if val is None or val < min_reference_token_f1:
            passed = False
    if min_reference_rouge_l_f1 is not None:
        val = _get_metric(m, "generator_eval.avg_reference_rouge_l_f1")
        checks["avg_reference_rouge_l_f1"] = val if val is not None else "missing"
        if val is None or val < min_reference_rouge_l_f1:
            passed = False
    if max_copy_rate is not None:
        val = _get_metric(m, "generator_eval.copy_rate")
        checks["copy_rate"] = val if val is not None else "missing"
        if val is None or val > max_copy_rate:
            passed = False
    if max_loss is not None:
        eval_l = _get_metric(m, "last_eval_loss")
        train_l = _get_metric(m, "last_train_loss")
        if eval_l is not None:
            checks["loss_used"] = "last_eval_loss"
            checks["loss_value"] = eval_l
            if eval_l > max_loss:
                passed = False
        elif train_l is not None:
            checks["loss_used"] = "last_train_loss"
            checks["loss_value"] = train_l
            checks["note"] = "no last_eval_loss; val_fraction may be 0 or metric name differs"
            if train_l > max_loss:
                passed = False
        else:
            checks["loss_value"] = "missing"
            passed = False
    return passed, checks


def _ensure_registered_model(client: MlflowClient, model_name: str) -> None:
    try:
        client.create_registered_model(model_name)
        print(f"[registry] created model: {model_name}")
    except MlflowException as exc:
        # RESOURCE_ALREADY_EXISTS varies slightly by backend/client version.
        msg = str(exc).lower()
        if "already exists" in msg or "resource_already_exists" in msg:
            print(f"[registry] model exists: {model_name}")
            return
        raise


def _wait_until_ready(client: MlflowClient, model_name: str, version: str, timeout_s: int = 120) -> None:
    start = time.time()
    while True:
        mv = client.get_model_version(name=model_name, version=version)
        status = (mv.status or "").upper()
        if status == "READY":
            return
        if status == "FAILED_REGISTRATION":
            raise RuntimeError(f"Model version registration failed: {model_name} v{version}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for READY: {model_name} v{version} (status={status})")
        time.sleep(2)


def _register_and_alias(
    client: MlflowClient,
    *,
    model_name: str,
    run_id: str,
    artifact_path: str,
    aliases: Iterable[str],
    version_tags: dict[str, str] | None = None,
) -> str:
    _ensure_registered_model(client, model_name)
    source = f"runs:/{run_id}/{artifact_path}"
    mv = client.create_model_version(name=model_name, source=source, run_id=run_id)
    version = str(mv.version)
    _wait_until_ready(client, model_name, version)
    tags = version_tags or {}
    for k, v in tags.items():
        try:
            client.set_model_version_tag(name=model_name, version=version, key=k, value=str(v))
        except (AttributeError, MlflowException):
            print(f"[warn] could not set model version tag {k!r} (API may not support tags)", file=sys.stderr)
    for alias in aliases:
        alias = alias.strip()
        if not alias:
            continue
        client.set_registered_model_alias(name=model_name, alias=alias, version=version)
        print(f"[alias] {model_name}@{alias} -> v{version}")
    return version


def main() -> None:
    p = argparse.ArgumentParser(
        description="Register latest successful runs and update MLflow aliases."
    )
    p.add_argument("--tracking-uri", default="", help="MLflow tracking URI. Falls back to env MLFLOW_TRACKING_URI.")
    p.add_argument("--classifier-experiment", default="teamchat_tone_clf")
    p.add_argument("--classifier-run-name", default="candidate_tone_distilbert")
    p.add_argument("--classifier-artifact-path", default="model")
    p.add_argument("--classifier-model-name", default="tone-classifier")
    p.add_argument("--generator-experiment", default="teamchat_tone_generator_llm")
    p.add_argument("--generator-run-name", default="smollm2_135m_lora_cpu")
    p.add_argument("--generator-artifact-path", default="lora_checkpoint")
    p.add_argument("--generator-model-name", default="tone-generator-lora")
    p.add_argument(
        "--aliases",
        default="canary,prod",
        help="Comma-separated aliases to update for both models (default: canary,prod).",
    )
    p.add_argument(
        "--insecure",
        action="store_true",
        help="Skip TLS certificate verification (use for self-signed MLflow HTTPS). "
        "Same as MLFLOW_TRACKING_INSECURE_TLS=true.",
    )
    p.add_argument(
        "--min-classifier-f1-macro",
        type=float,
        default=None,
        help="Quality gate: minimum macro F1 on held-out test (train.py logs f1_macro).",
    )
    p.add_argument(
        "--min-classifier-accuracy",
        type=float,
        default=None,
        help="Quality gate: minimum accuracy on held-out test.",
    )
    p.add_argument(
        "--min-classifier-worst-class-f1",
        type=float,
        default=None,
        help="Quality gate: minimum per-class F1 across formal/friendly/neutral (fairness).",
    )
    p.add_argument(
        "--max-generator-loss",
        type=float,
        default=None,
        help="Quality gate: max allowed last_eval_loss or last_train_loss (lower is better).",
    )
    p.add_argument(
        "--min-generator-reference-token-f1",
        type=float,
        default=None,
        help="Quality gate: minimum held-out reference token-F1 for generator rewrites.",
    )
    p.add_argument(
        "--min-generator-reference-rouge-l-f1",
        type=float,
        default=None,
        help="Quality gate: minimum held-out ROUGE-L F1 for generator rewrites.",
    )
    p.add_argument(
        "--max-generator-copy-rate",
        type=float,
        default=None,
        help="Quality gate: maximum fraction of rewrites that simply copy the source text.",
    )
    p.add_argument(
        "--skip-quality-gates",
        action="store_true",
        help="Register models even when --min-* / --max-* thresholds are not met (not recommended).",
    )
    args = p.parse_args()

    if args.insecure:
        os.environ["MLFLOW_TRACKING_INSECURE_TLS"] = "true"

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)
    client = MlflowClient()
    print(f"[mlflow] tracking_uri={mlflow.get_tracking_uri()}")

    aliases = [a.strip() for a in args.aliases.split(",") if a.strip()]
    if not aliases:
        raise ValueError("No aliases provided. Use --aliases canary,prod (or similar).")

    clf_run = _latest_finished_run(client, args.classifier_experiment, args.classifier_run_name)
    gen_run = _latest_finished_run(client, args.generator_experiment, args.generator_run_name)
    print(
        f"[selected] classifier run_id={clf_run.info.run_id} "
        f"(experiment={args.classifier_experiment}, run_name={args.classifier_run_name})"
    )
    print(
        f"[selected] generator run_id={gen_run.info.run_id} "
        f"(experiment={args.generator_experiment}, run_name={args.generator_run_name})"
    )

    gate_requested = any(
        x is not None
        for x in (
            args.min_classifier_f1_macro,
            args.min_classifier_accuracy,
            args.min_classifier_worst_class_f1,
            args.max_generator_loss,
            args.min_generator_reference_token_f1,
            args.min_generator_reference_rouge_l_f1,
            args.max_generator_copy_rate,
        )
    )
    clf_ok, clf_detail = _evaluate_classifier_gates(
        clf_run,
        min_f1_macro=args.min_classifier_f1_macro,
        min_accuracy=args.min_classifier_accuracy,
        min_worst_class_f1=args.min_classifier_worst_class_f1,
    )
    gen_ok, gen_detail = _evaluate_generator_gates(
        gen_run,
        max_loss=args.max_generator_loss,
        min_reference_token_f1=args.min_generator_reference_token_f1,
        min_reference_rouge_l_f1=args.min_generator_reference_rouge_l_f1,
        max_copy_rate=args.max_generator_copy_rate,
    )
    gates_passed = clf_ok and gen_ok

    if gate_requested:
        print("[gates] classifier:", json.dumps(clf_detail, indent=2))
        print("[gates] generator:", json.dumps(gen_detail, indent=2))
        if not gates_passed:
            print(
                "[gates] FAILED — model registration skipped. "
                "Adjust thresholds or retrain; use --skip-quality-gates only for debugging.",
                file=sys.stderr,
            )
            if not args.skip_quality_gates:
                sys.exit(2)
            print("[gates] --skip-quality-gates set: registering anyway.", file=sys.stderr)

    gate_status = "not_configured"
    if gate_requested:
        gate_status = "passed" if gates_passed else "failed"

    satisfied_str = "n/a" if not gate_requested else str(gates_passed)
    clf_tags = {
        "quality_gate_status": gate_status,
        "quality_gates_satisfied": satisfied_str,
        "registered_from_run_id": clf_run.info.run_id,
    }
    gen_tags = {
        "quality_gate_status": gate_status,
        "quality_gates_satisfied": satisfied_str,
        "registered_from_run_id": gen_run.info.run_id,
    }

    clf_ver = _register_and_alias(
        client,
        model_name=args.classifier_model_name,
        run_id=clf_run.info.run_id,
        artifact_path=args.classifier_artifact_path,
        aliases=aliases,
        version_tags=clf_tags,
    )
    gen_ver = _register_and_alias(
        client,
        model_name=args.generator_model_name,
        run_id=gen_run.info.run_id,
        artifact_path=args.generator_artifact_path,
        aliases=aliases,
        version_tags=gen_tags,
    )

    print("\nDone.")
    print(f"Classifier: models:/{args.classifier_model_name}@{aliases[0]} -> v{clf_ver}")
    print(f"Generator:  models:/{args.generator_model_name}@{aliases[0]} -> v{gen_ver}")


if __name__ == "__main__":
    main()

