"""
Tone Generator — instruction-tuned LLM (Flan-T5 base by default).
Rewrites a message in three tones: Formal, Friendly, Neutral.

DUMMY_MODE (default=true):
  Returns template-based rewrites instantly. No model download, no GPU needed.
  Realistic latency is simulated. Use this for serving benchmarks.

Real mode (DUMMY_MODE=false):
  Loads Flan-T5 (or fine-tuned checkpoint) and generates proper rewrites.
  Requires GPU for <600ms latency target.
  Switch: DUMMY_MODE=false MODEL_NAME=google/flan-t5-base

The generator is designed so that once the training team delivers a
fine-tuned checkpoint, only MODEL_NAME needs to change.
"""

import os
import logging
import time
import random
import re

logger = logging.getLogger(__name__)

TONES = ["formal", "friendly", "neutral"]
DUMMY_MODE = os.environ.get("DUMMY_MODE", "true").lower() != "false"
MODEL_NAME = os.environ.get("MODEL_NAME", "google/flan-t5-base")
MAX_INPUT_LEN = 256
MAX_NEW_TOKENS = 128


# ---------------------------------------------------------------------------
# Dummy: template-based rewriter (no model needed)
# ---------------------------------------------------------------------------

# Slang / informal → formal substitutions
_SLANG = {
    r"\byo\b": "Hello",
    r"\bu\b": "you",
    r"\br\b": "are",
    r"\blol\b": "",
    r"\bomg\b": "",
    r"\bbtw\b": "by the way",
    r"\bgonna\b": "going to",
    r"\bwanna\b": "want to",
    r"\bgotta\b": "have to",
    r"\bcant\b": "cannot",
    r"\bdont\b": "do not",
    r"\bwont\b": "will not",
    r"\bim\b": "I am",
    r"\bits\b": "it has",
    r"!!+": ".",
    r"\?\?+": "?",
}


def _clean(text: str) -> str:
    """Apply slang substitutions and clean up whitespace."""
    t = text
    for pattern, replacement in _SLANG.items():
        t = re.sub(pattern, replacement, t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" .,")
    # Capitalise first letter
    return t[0].upper() + t[1:] if t else text


class _DummyGenerator:
    """Template-based rewriter — exercises full API without any model."""

    def generate_all(self, text: str) -> dict:
        t_total = time.perf_counter()
        variants = {}
        cleaned = _clean(text)

        templates = {
            "formal": (
                f"{cleaned}. I would appreciate your prompt attention to this matter.",
                random.uniform(0.140, 0.200),
            ),
            "friendly": (
                f"Hey! Just wanted to check in — {cleaned.lower()}. Thanks so much!",
                random.uniform(0.140, 0.200),
            ),
            "neutral": (
                f"{cleaned}. Please address this when possible.",
                random.uniform(0.140, 0.200),
            ),
        }

        offensive = any(
            w in text.lower()
            for w in ["idiot", "stupid", "hate", "damn", "hell", "crap", "ass"]
        )

        for tone, (rewrite, sleep_s) in templates.items():
            time.sleep(sleep_s)  # simulate per-tone generation latency
            variants[tone] = {
                "text": rewrite,
                "tone_latency_ms": round(sleep_s * 1000, 2),
            }

        total_latency_ms = (time.perf_counter() - t_total) * 1000
        return {
            "variants": variants,
            "offensive_content_flagged": offensive,
            "total_latency_ms": round(total_latency_ms, 2),
        }


# ---------------------------------------------------------------------------
# Real: LLM-based generator
# ---------------------------------------------------------------------------

TONE_PROMPTS = {
    "formal": (
        "Rewrite the following message in a formal, professional tone suitable "
        "for a workplace communication platform. Preserve all original meaning. "
        "Output only the rewritten message.\n\nOriginal: {text}\n\nFormal rewrite:"
    ),
    "friendly": (
        "Rewrite the following message in a warm, friendly, and polite tone. "
        "Preserve all original meaning. "
        "Output only the rewritten message.\n\nOriginal: {text}\n\nFriendly rewrite:"
    ),
    "neutral": (
        "Rewrite the following message in a clear, neutral, and professional tone. "
        "Preserve all original meaning. Remove slang and overly casual phrasing. "
        "Output only the rewritten message.\n\nOriginal: {text}\n\nNeutral rewrite:"
    ),
}


class _RealGenerator:
    def __init__(self):
        import torch
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        from better_profanity import profanity

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("Loading generator model: %s on %s", MODEL_NAME, self._device)
        self._tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float16 if self._device == "cuda" else torch.float32,
        ).to(self._device)
        self._model.eval()
        profanity.load_censor_words()
        self._profanity = profanity
        self._torch = torch
        logger.info("Real generator ready on %s", self._device)

    def generate_all(self, text: str) -> dict:
        t_total = time.perf_counter()
        variants = {}
        offensive = False

        for tone in TONES:
            prompt = TONE_PROMPTS[tone].format(text=text)
            inputs = self._tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=MAX_INPUT_LEN
            ).to(self._device)
            t0 = time.perf_counter()
            with self._torch.no_grad():
                output_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    num_beams=4,
                    early_stopping=True,
                    no_repeat_ngram_size=3,
                )
            tone_latency_ms = (time.perf_counter() - t0) * 1000
            rewrite = self._tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
            if self._profanity.contains_profanity(rewrite):
                offensive = True
            variants[tone] = {"text": rewrite, "tone_latency_ms": round(tone_latency_ms, 2)}

        total_latency_ms = (time.perf_counter() - t_total) * 1000
        return {
            "variants": variants,
            "offensive_content_flagged": offensive,
            "total_latency_ms": round(total_latency_ms, 2),
        }


class ToneGenerator:
    """Factory: returns dummy or real generator based on DUMMY_MODE env var."""

    def __new__(cls):
        if DUMMY_MODE:
            logger.info("Generator starting in DUMMY_MODE (no model download)")
            return _DummyGenerator()
        logger.info("Generator starting in REAL mode (MODEL_NAME=%s)", MODEL_NAME)
        return _RealGenerator()
