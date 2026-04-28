from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


TONE_LABELS = ("formal", "friendly", "neutral")


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_seed_classifier(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            text = _normalize_text(row.get("text", ""))
            tone = (row.get("tone") or "").strip()
            if text and tone in TONE_LABELS:
                rows.append({"text": text, "tone": tone, "source": "seed"})
    return rows


def _load_seed_generator(path: Path) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            original = _normalize_text(obj.get("original_text", ""))
            if not original:
                continue
            example = {"original_text": original}
            if all(_normalize_text(obj.get(tone, "")) for tone in TONE_LABELS):
                for tone in TONE_LABELS:
                    example[tone] = _normalize_text(obj[tone])
                examples.append(example)
    return examples


def _extract_feedback_rows(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, list):
        out: list[dict[str, Any]] = []
        for item in obj:
            out.extend(_extract_feedback_rows(item))
        return out
    if isinstance(obj, dict):
        if "records" in obj and isinstance(obj["records"], list):
            return _extract_feedback_rows(obj["records"])
        return [obj]
    return []


def _load_feedback_rows(feedback_dir: Path | None) -> list[dict[str, Any]]:
    if feedback_dir is None or not feedback_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(feedback_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    rows.extend(_extract_feedback_rows(json.loads(line)))
        elif path.suffix.lower() == ".json":
            rows.extend(_extract_feedback_rows(_load_json(path)))
    return rows


def _feedback_tone_label(row: dict[str, Any]) -> str | None:
    for key in ("tone", "tone_requested", "selected_tone", "rewrite_style"):
        tone = str(row.get(key) or "").strip().lower()
        if tone in TONE_LABELS:
            return tone
    return None


def _feedback_original_text(row: dict[str, Any]) -> str:
    candidates = [
        row.get("original_text"),
        row.get("original_message"),
        (row.get("input") or {}).get("original_message") if isinstance(row.get("input"), dict) else None,
        (row.get("input") or {}).get("text") if isinstance(row.get("input"), dict) else None,
        row.get("text"),
    ]
    for value in candidates:
        text = _normalize_text(str(value or ""))
        if text:
            return text
    return ""


def _feedback_rewrite_text(row: dict[str, Any]) -> str:
    candidates = [
        row.get("rewritten_text"),
        row.get("selected_rewrite"),
        row.get("rewrite_text"),
        row.get("text"),
        (row.get("output") or {}).get("rewritten_message") if isinstance(row.get("output"), dict) else None,
        (row.get("output") or {}).get("text") if isinstance(row.get("output"), dict) else None,
    ]
    for value in candidates:
        text = _normalize_text(str(value or ""))
        if text:
            return text
    return ""


def _feedback_helpful(row: dict[str, Any]) -> bool:
    helpful = row.get("helpful")
    if isinstance(helpful, bool):
        return helpful
    if isinstance(helpful, str):
        return helpful.strip().lower() in {"1", "true", "yes", "accepted", "upvote"}
    reaction = str(row.get("reaction") or row.get("label") or "").strip().lower()
    return reaction in {"up", "thumbs_up", "+1", "helpful", "accepted"}


def _build_classifier_rows(
    seed_rows: list[dict[str, str]],
    feedback_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    dedup: dict[tuple[str, str], dict[str, str]] = {
        (row["text"], row["tone"]): dict(row) for row in seed_rows
    }
    added_feedback = 0
    for row in feedback_rows:
        tone = _feedback_tone_label(row)
        text = _feedback_original_text(row)
        if tone and text:
            key = (text, tone)
            if key not in dedup:
                dedup[key] = {"text": text, "tone": tone, "source": "feedback"}
                added_feedback += 1
    return list(dedup.values()), {
        "seed_rows": len(seed_rows),
        "feedback_rows_used": added_feedback,
        "final_rows": len(dedup),
    }


def _build_generator_examples(
    seed_examples: list[dict[str, str]],
    feedback_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    examples: dict[str, dict[str, str]] = {
        ex["original_text"]: dict(ex) for ex in seed_examples
    }
    feedback_updates = 0
    coverage = defaultdict(int)
    for row in feedback_rows:
        if not _feedback_helpful(row):
            continue
        original = _feedback_original_text(row)
        tone = _feedback_tone_label(row)
        rewrite = _feedback_rewrite_text(row)
        if not (original and tone and rewrite):
            continue
        current = examples.setdefault(original, {"original_text": original})
        if current.get(tone) != rewrite:
            current[tone] = rewrite
            feedback_updates += 1
            coverage[tone] += 1

    full_examples = [ex for ex in examples.values() if all(ex.get(tone) for tone in TONE_LABELS)]
    full_examples.sort(key=lambda ex: ex["original_text"])
    return full_examples, {
        "seed_examples": len(seed_examples),
        "feedback_updates": feedback_updates,
        "feedback_tone_coverage": dict(coverage),
        "final_examples": len(full_examples),
    }


def _write_classifier_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "tone"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"text": row["text"], "tone": row["tone"]})


def _write_generator_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _split_examples(rows: list[dict[str, str]], eval_fraction: float) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    if len(rows) < 2 or eval_fraction <= 0:
        return rows, []
    eval_count = max(1, int(round(len(rows) * eval_fraction)))
    eval_count = min(eval_count, len(rows) - 1)
    return rows[:-eval_count], rows[-eval_count:]


def main() -> None:
    p = argparse.ArgumentParser(description="Prepare manifest-backed training datasets from latest batch + feedback.")
    p.add_argument("--batch-root", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--classifier-seed-csv", type=Path, default=Path("data/tone_seed.csv"))
    p.add_argument("--generator-seed-jsonl", type=Path, default=Path("data/generator_train.jsonl"))
    p.add_argument("--feedback-dir", type=Path, default=None)
    p.add_argument("--eval-fraction", type=float, default=0.2)
    args = p.parse_args()

    base = Path(__file__).resolve().parent
    batch_root = args.batch_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    batch_manifest_path = batch_root / "manifest.json"
    batch_manifest = _load_json(batch_manifest_path) if batch_manifest_path.exists() else {}
    feedback_rows = _load_feedback_rows(args.feedback_dir.resolve() if args.feedback_dir else None)

    classifier_seed = _load_seed_classifier((base / args.classifier_seed_csv).resolve())
    classifier_rows, classifier_stats = _build_classifier_rows(classifier_seed, feedback_rows)
    classifier_path = output_dir / "classifier_tone.csv"
    _write_classifier_csv(classifier_path, classifier_rows)

    generator_seed = _load_seed_generator((base / args.generator_seed_jsonl).resolve())
    generator_examples, generator_stats = _build_generator_examples(generator_seed, feedback_rows)
    generator_train, generator_eval = _split_examples(generator_examples, args.eval_fraction)
    generator_train_path = output_dir / "generator_train.jsonl"
    generator_eval_path = output_dir / "generator_eval.jsonl"
    _write_generator_jsonl(generator_train_path, generator_train)
    _write_generator_jsonl(generator_eval_path, generator_eval)

    training_manifest = {
        "batch_version": batch_manifest.get("batch_version", "unknown"),
        "created_at": batch_manifest.get("created_at", "unknown"),
        "source_batch_manifest": str(batch_manifest_path),
        "live_feedback_rows_seen": len(feedback_rows),
        "artifacts": {
            "classifier_tone_csv": {
                "train_path": str(classifier_path),
                "label_classes": list(TONE_LABELS),
                "stats": classifier_stats,
            },
            "generator_rewrites": {
                "train_path": str(generator_train_path),
                "eval_path": str(generator_eval_path),
                "tones": list(TONE_LABELS),
                "stats": {
                    **generator_stats,
                    "train_examples": len(generator_train),
                    "eval_examples": len(generator_eval),
                },
            },
        },
        "limitations": {
            "classifier": "Friendly tone coverage remains weak unless feedback or curated labels are added.",
            "generator": "Generator improves most when helpful user feedback exists; otherwise seed examples dominate.",
        },
    }
    manifest_path = output_dir / "dataset_manifest.json"
    manifest_path.write_text(json.dumps(training_manifest, indent=2), encoding="utf-8")
    print(json.dumps(training_manifest, indent=2))


if __name__ == "__main__":
    main()
