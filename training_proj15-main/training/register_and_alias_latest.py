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
  3) Registers model versions from run artifacts
  4) Sets aliases (default: canary,prod) on both registered models
"""

from __future__ import annotations

import argparse
import os
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
) -> str:
    _ensure_registered_model(client, model_name)
    source = f"runs:/{run_id}/{artifact_path}"
    mv = client.create_model_version(name=model_name, source=source, run_id=run_id)
    version = str(mv.version)
    _wait_until_ready(client, model_name, version)
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

    clf_ver = _register_and_alias(
        client,
        model_name=args.classifier_model_name,
        run_id=clf_run.info.run_id,
        artifact_path=args.classifier_artifact_path,
        aliases=aliases,
    )
    gen_ver = _register_and_alias(
        client,
        model_name=args.generator_model_name,
        run_id=gen_run.info.run_id,
        artifact_path=args.generator_artifact_path,
        aliases=aliases,
    )

    print("\nDone.")
    print(f"Classifier: models:/{args.classifier_model_name}@{aliases[0]} -> v{clf_ver}")
    print(f"Generator:  models:/{args.generator_model_name}@{aliases[0]} -> v{gen_ver}")


if __name__ == "__main__":
    main()

