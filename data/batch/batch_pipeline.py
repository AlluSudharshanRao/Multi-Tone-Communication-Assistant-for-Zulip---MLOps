from __future__ import annotations

import json
import os
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path

import boto3
import pandas as pd
from botocore.client import Config

BUCKET = os.getenv("MINIO_BUCKET", "zulip-rewriter")
ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio.ml-platform.svc.cluster.local:9000")
ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
if not ACCESS_KEY or not SECRET_KEY:
    raise RuntimeError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set")
VERSION = os.getenv("DATA_VERSION", "v1")
BATCH_DATE = os.getenv("BATCH_DATE", datetime.utcnow().strftime("%Y-%m-%d"))
TONE_TO_BINARY = {"formal": 1, "neutral": 0, "friendly": -1}
DRIFT_FEATURES = [
    "word_count",
    "char_count",
    "polite_marker_count",
    "informal_marker_count",
    "has_question_mark",
    "has_exclamation",
    "estimated_formality",
]
POLITE_MARKERS = [r"\bplease\b", r"\bthank\b", r"\bcould you\b", r"\bwould you\b", r"\bi appreciate\b", r"\bkindly\b"]
INFORMAL_MARKERS = [r"\bhey\b", r"\byo\b", r"\bu\b", r"\bgonna\b", r"\bwanna\b", r"\bbtw\b", r"\bomg\b", r"\blol\b"]

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=ACCESS_KEY,
    aws_secret_access_key=SECRET_KEY,
    verify=False,
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)


def extract_features(text: str) -> dict[str, float]:
    lowered = (text or "").lower()
    words = lowered.split()
    polite = sum(1 for pattern in POLITE_MARKERS if re.search(pattern, lowered))
    informal = sum(1 for pattern in INFORMAL_MARKERS if re.search(pattern, lowered))
    return {
        "word_count": len(words),
        "char_count": len(text or ""),
        "polite_marker_count": polite,
        "informal_marker_count": informal,
        "has_question_mark": int("?" in (text or "")),
        "has_exclamation": int("!" in (text or "")),
        "estimated_formality": round((polite - informal) / max(len(words), 1), 4),
    }


def build_drift_baseline(df: pd.DataFrame) -> dict[str, object]:
    feature_df = pd.DataFrame([extract_features(text) for text in df["text"].dropna().astype(str)])
    stats = {}
    for feature in DRIFT_FEATURES:
        series = feature_df[feature].astype(float)
        stats[feature] = {
            "mean": round(float(series.mean()), 6),
            "std": round(float(series.std(ddof=0)), 6),
            "min": round(float(series.min()), 6),
            "max": round(float(series.max()), 6),
            "count": int(series.count()),
        }
    return {
        "baseline_type": "classifier_training_corpus_features",
        "created_at": datetime.utcnow().isoformat(),
        "feature_count": len(DRIFT_FEATURES),
        "sample_count": int(len(feature_df)),
        "features": stats,
    }


def load_parquet(key: str) -> pd.DataFrame:
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    return pd.read_parquet(BytesIO(obj["Body"].read()))


def list_json_records(prefix: str) -> list[tuple[str, dict[str, object]]]:
    paginator = s3.get_paginator("list_objects_v2")
    records: list[tuple[str, dict[str, object]]] = []
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj_meta in page.get("Contents", []):
            if not obj_meta["Key"].endswith(".json"):
                continue
            try:
                obj = s3.get_object(Bucket=BUCKET, Key=obj_meta["Key"])
                payload = json.loads(obj["Body"].read())
                if isinstance(payload, list):
                    for entry in payload:
                        records.append((obj_meta["Key"], entry))
                elif isinstance(payload, dict):
                    records.append((obj_meta["Key"], payload))
            except Exception as exc:
                print(f"Warning loading {obj_meta['Key']}: {exc}")
    return records


def build_online_index() -> tuple[pd.DataFrame, pd.DataFrame]:
    log_rows = []
    labeled_rows = []
    for key, entry in list_json_records("online_logs/"):
        payload = entry.get("input", {}) if isinstance(entry, dict) else {}
        output = entry.get("output", {}) if isinstance(entry, dict) else {}
        message_id = payload.get("message_id")
        original_text = payload.get("original_message", "")
        log_rows.append(
            {
                "message_id": message_id,
                "original_text": original_text,
                "rewrite_style": payload.get("rewrite_style", ""),
                "timestamp": payload.get("timestamp", ""),
                "key": key,
            }
        )
        variants = output.get("variants", {}) if isinstance(output, dict) else {}
        if isinstance(variants, dict):
            labeled_rows.append(
                {
                    "message_id": message_id,
                    "original_text": original_text,
                    "formal": ((variants.get("formal") or {}).get("text") if isinstance(variants.get("formal"), dict) else None),
                    "friendly": ((variants.get("friendly") or {}).get("text") if isinstance(variants.get("friendly"), dict) else None),
                    "neutral": ((variants.get("neutral") or {}).get("text") if isinstance(variants.get("neutral"), dict) else None),
                }
            )
    return pd.DataFrame(log_rows), pd.DataFrame(labeled_rows)


def build_feedback_rows(log_lookup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    feedback_examples = []
    generator_examples = []
    usable = 0
    approvals = 0
    feedback_records = list_json_records("feedback/")
    lookup = log_lookup.drop_duplicates(subset=["message_id"]).set_index("message_id") if not log_lookup.empty else pd.DataFrame()
    for _, rec in feedback_records:
        action = str(rec.get("user_action", "")).lower()
        if action not in {"thumbs_up", "thumbs_down", "selected", "edited"}:
            continue
        approvals += int(action in {"thumbs_up", "selected"})
        tone = str(rec.get("correct_tone") or rec.get("tone_shown") or "").lower()
        if tone not in TONE_TO_BINARY:
            continue
        preferred_text = str(rec.get("preferred_text") or "").strip()
        message_id = rec.get("message_id")
        joined = lookup.loc[message_id] if (message_id in lookup.index) else None
        original_text = str(joined["original_text"]).strip() if joined is not None else ""
        variant_formal = str(joined["formal"]).strip() if joined is not None and pd.notna(joined["formal"]) else ""
        variant_friendly = str(joined["friendly"]).strip() if joined is not None and pd.notna(joined["friendly"]) else ""
        variant_neutral = str(joined["neutral"]).strip() if joined is not None and pd.notna(joined["neutral"]) else ""
        chosen_text = preferred_text or {
            "formal": variant_formal,
            "friendly": variant_friendly,
            "neutral": variant_neutral,
        }.get(tone, "")
        if chosen_text:
            usable += 1
            feedback_examples.append(
                {
                    "text": chosen_text,
                    "tone": tone,
                    "split": "train",
                    "binary_label": TONE_TO_BINARY[tone],
                    "source": "feedback",
                }
            )
        if original_text and variant_formal and variant_friendly and variant_neutral:
            generator_row = {
                "original_text": original_text,
                "formal": preferred_text if tone == "formal" and preferred_text else variant_formal,
                "friendly": preferred_text if tone == "friendly" and preferred_text else variant_friendly,
                "neutral": preferred_text if tone == "neutral" and preferred_text else variant_neutral,
                "split": "train",
                "source": "feedback",
            }
            generator_examples.append(generator_row)
    manifest = {
        "batch_date": BATCH_DATE,
        "feedback_total_entries": len(feedback_records),
        "feedback_usable_for_training": usable,
        "approval_rate": round(approvals / max(len(feedback_records), 1), 4) if feedback_records else None,
    }
    return pd.DataFrame(feedback_examples), pd.DataFrame(generator_examples), manifest


def write_jsonl(df: pd.DataFrame, path: Path, columns: list[str]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as file_obj:
        for record in df[columns].to_dict("records"):
            file_obj.write(json.dumps(record, ensure_ascii=True) + "\n")
            count += 1
    return count


def upload_df(df: pd.DataFrame, key: str) -> None:
    buf = BytesIO()
    df.to_parquet(buf, index=False)
    s3.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())
    print(f"Uploaded {key} ({len(df)} rows)")


def upload_text(path: Path, key: str) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=path.read_bytes())
    print(f"Uploaded {key}")


print(f"Batch pipeline starting | version={VERSION} | date={BATCH_DATE}")

print("Step 1: Loading raw classifier and generator datasets from MinIO...")
df_raw = load_parquet(f"raw/{VERSION}/full.parquet")
df_pairs = load_parquet(f"raw/{VERSION}/pairs.parquet")
print(f"  Raw classifier rows: {len(df_raw)}")
print(f"  Raw generator pair rows: {len(df_pairs)}")

print("Step 2: Loading online logs for drift/feedback joins...")
df_online_logs, df_online_variants = build_online_index()
print(f"  Online log rows: {len(df_online_logs)}")
print(f"  Online variant rows: {len(df_online_variants)}")

print("Step 3: Loading feedback labels...")
df_feedback_classifier, df_feedback_generator, feedback_manifest = build_feedback_rows(df_online_variants)
print(f"  Feedback classifier rows: {len(df_feedback_classifier)}")
print(f"  Feedback generator rows: {len(df_feedback_generator)}")

print("Step 4: Building training-ready datasets...")
df_classifier = df_raw[["text", "tone", "split", "binary_label"]].copy()
df_classifier["source"] = "gyafc"
if not df_feedback_classifier.empty:
    df_classifier = pd.concat([df_classifier, df_feedback_classifier], ignore_index=True)

df_classifier["text"] = df_classifier["text"].astype(str).str.strip()
df_classifier = df_classifier[df_classifier["text"] != ""].drop_duplicates(subset=["text", "tone", "split"])
df_classifier_train = df_classifier[df_classifier["split"].isin(["train", "val"])].copy()
df_classifier_test = df_classifier[df_classifier["split"] == "test"].copy()

df_generator = df_pairs[["original_text", "formal", "friendly", "neutral", "split"]].copy()
df_generator["source"] = "gyafc"
if not df_feedback_generator.empty:
    df_generator = pd.concat([df_generator, df_feedback_generator], ignore_index=True)
df_generator = df_generator.drop_duplicates(subset=["original_text", "formal", "friendly", "neutral", "split"])
df_generator_train = df_generator[df_generator["split"] == "train"].copy()
df_generator_val = df_generator[df_generator["split"] == "val"].copy()

print("Step 5: Building drift baseline from labeled training data only...")
drift_baseline = build_drift_baseline(df_classifier_train)
drift_baseline["batch_date"] = BATCH_DATE
drift_baseline["source_rows"] = int(len(df_classifier_train))
drift_baseline["online_rows_observed"] = int(len(df_online_logs))

print("Step 6: Uploading versioned datasets...")
batch_ver = f"{VERSION}_batch_{BATCH_DATE}"
latest_prefix = "batch/latest"
versioned_prefix = f"batch/{batch_ver}"

upload_df(df_classifier_train, f"{versioned_prefix}/train.parquet")
upload_df(df_classifier_test, f"{versioned_prefix}/test.parquet")
upload_df(df_classifier_train, f"{latest_prefix}/train.parquet")
upload_df(df_classifier_test, f"{latest_prefix}/test.parquet")

workdir = Path("/tmp/batch_assets")
workdir.mkdir(parents=True, exist_ok=True)
classifier_csv = workdir / "classifier_dataset.csv"
df_classifier[["text", "tone", "split"]].to_csv(classifier_csv, index=False)
upload_text(classifier_csv, f"{versioned_prefix}/classifier_dataset.csv")
upload_text(classifier_csv, f"{latest_prefix}/classifier_dataset.csv")

generator_train_path = workdir / "generator_train.jsonl"
generator_val_path = workdir / "generator_val.jsonl"
train_rows = write_jsonl(df_generator_train, generator_train_path, ["original_text", "formal", "friendly", "neutral"])
val_rows = write_jsonl(df_generator_val, generator_val_path, ["original_text", "formal", "friendly", "neutral"])
upload_text(generator_train_path, f"{versioned_prefix}/generator_train.jsonl")
upload_text(generator_train_path, f"{latest_prefix}/generator_train.jsonl")
upload_text(generator_val_path, f"{versioned_prefix}/generator_val.jsonl")
upload_text(generator_val_path, f"{latest_prefix}/generator_val.jsonl")

s3.put_object(Bucket=BUCKET, Key=f"batch/{BATCH_DATE}/feedback_manifest.json", Body=json.dumps(feedback_manifest, indent=2))
s3.put_object(Bucket=BUCKET, Key=f"{versioned_prefix}/drift_baseline.json", Body=json.dumps(drift_baseline, indent=2))
s3.put_object(Bucket=BUCKET, Key=f"{latest_prefix}/drift_baseline.json", Body=json.dumps(drift_baseline, indent=2))

manifest = {
    "batch_version": batch_ver,
    "created_at": datetime.utcnow().isoformat(),
    "classifier_rows_total": int(len(df_classifier)),
    "classifier_train_rows": int(len(df_classifier_train)),
    "classifier_test_rows": int(len(df_classifier_test)),
    "generator_train_rows": int(train_rows),
    "generator_val_rows": int(val_rows),
    "online_log_rows_observed": int(len(df_online_logs)),
    "feedback_rows_merged": int(len(df_feedback_classifier)),
    "feedback_approval_rate": feedback_manifest.get("approval_rate"),
    "drift_baseline_key": f"{versioned_prefix}/drift_baseline.json",
    "leakage_policy": "online logs are drift-only unless explicitly labeled through feedback",
    "artifacts": {
        "classifier_dataset_csv": f"{versioned_prefix}/classifier_dataset.csv",
        "generator_train_jsonl": f"{versioned_prefix}/generator_train.jsonl",
        "generator_val_jsonl": f"{versioned_prefix}/generator_val.jsonl",
        "latest_classifier_dataset_csv": f"{latest_prefix}/classifier_dataset.csv",
        "latest_generator_train_jsonl": f"{latest_prefix}/generator_train.jsonl",
        "latest_generator_val_jsonl": f"{latest_prefix}/generator_val.jsonl",
    },
}
s3.put_object(Bucket=BUCKET, Key=f"{versioned_prefix}/manifest.json", Body=json.dumps(manifest, indent=2))
s3.put_object(Bucket=BUCKET, Key=f"{latest_prefix}/manifest.json", Body=json.dumps(manifest, indent=2))
print("Batch pipeline complete!")
print(json.dumps(manifest, indent=2))
