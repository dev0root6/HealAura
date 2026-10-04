"""Benchmark HealAura's Sarvam-105B classifier on Tanglish sentiment (DravidianCodeMix).

Dataset: community-datasets/tamilmixsentiment (Chakravarthi et al.), test split.
Label mapping to HealAura's 4-class scheme:
    Positive -> positive, Negative -> negative, Mixed_feelings -> mixed,
    unknown_state -> neutral, not-Tamil -> excluded.

Conditions:
    fewshot  - the production pipeline, classify.classify_entry (system prompt + few-shot)
    zeroshot - same system prompt without the few-shot examples

HealAura may split one comment into several segments; a comment-level label is
derived as: no non-neutral segment -> neutral; exactly one distinct non-neutral
sentiment -> that sentiment; more than one -> mixed.

Results are cached per item in results_<condition>.jsonl so the run can resume.

Usage: python run_llm_eval.py [--n 500] [--seed 42] [--conditions fewshot zeroshot]
"""
import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import classify  # noqa: E402
import sarvam_client  # noqa: E402
from datasets import load_dataset  # noqa: E402

LABEL_MAP = {0: "positive", 1: "negative", 2: "mixed", 3: "neutral"}  # 4 = not-Tamil, dropped


def load_sample(n: int, seed: int) -> list[dict]:
    test = load_dataset("community-datasets/tamilmixsentiment", split="test")
    items = [
        {"idx": i, "text": r["text"], "gold": LABEL_MAP[r["label"]]}
        for i, r in enumerate(test)
        if r["label"] in LABEL_MAP
    ]
    random.Random(seed).shuffle(items)
    return items[:n]


def aggregate(sentiments: list[str]) -> str:
    polar = {s for s in sentiments if s != "neutral"}
    if not polar:
        return "neutral"
    if len(polar) == 1:
        return polar.pop()
    return "mixed"


async def classify_zeroshot(text: str):
    """Mirror of classify.classify_entry, but with the system prompt only."""
    last_error = None
    for _ in range(3):
        try:
            content = await sarvam_client.chat_completion(classify.SYSTEM_PROMPT, text)
        except RuntimeError as exc:
            last_error = exc
            continue
        if not content or not content.strip():
            continue
        try:
            segs = classify.parse_segments(content)
            if segs:
                return segs, False
        except ValueError:
            continue
    if isinstance(last_error, RuntimeError):
        raise last_error
    return [classify._fallback_segment(text)], True


async def run_one(item: dict, condition: str) -> dict:
    fn = classify.classify_entry if condition == "fewshot" else classify_zeroshot
    # Back off on HTTP 429 (rate limit) at the harness level; latency is taken
    # from the final, successful attempt only.
    for backoff in (5, 10, 20, 40, 60, 90, None):
        t0 = time.perf_counter()
        try:
            segs, fallback = await fn(item["text"])
            error = None
        except Exception as exc:  # API failure after the pipeline's own retries
            segs, fallback, error = [], False, str(exc)[:300]
        latency = time.perf_counter() - t0
        if error is None or "429" not in error or backoff is None:
            break
        await asyncio.sleep(backoff + random.random() * 3)
    sentiments = [s.sentiment for s in segs]
    return {
        **item,
        "condition": condition,
        "pred": aggregate(sentiments) if segs else None,
        "segments": [{"text": s.segment_text, "type": s.type, "sentiment": s.sentiment} for s in segs],
        "n_segments": len(segs),
        "fallback": fallback,
        "error": error,
        "latency_s": round(latency, 3),
    }


async def run_condition(items: list[dict], condition: str, concurrency: int) -> None:
    out = HERE / f"results_{condition}.jsonl"
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            if r["error"] is None:
                done.add(r["idx"])
    todo = [it for it in items if it["idx"] not in done]
    print(f"[{condition}] {len(done)} cached, {len(todo)} to run", flush=True)
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    finished = 0

    async def worker(it):
        nonlocal finished
        async with sem:
            res = await run_one(it, condition)
        async with lock:
            with out.open("a") as f:
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
            finished += 1
            if finished % 25 == 0:
                print(f"[{condition}] {finished}/{len(todo)}", flush=True)

    await asyncio.gather(*(worker(it) for it in todo))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--conditions", nargs="+", default=["fewshot", "zeroshot"])
    args = ap.parse_args()
    items = load_sample(args.n, args.seed)
    (HERE / "sample_ids.json").write_text(json.dumps([it["idx"] for it in items]))
    for c in args.conditions:
        await run_condition(items, c, args.concurrency)
    await sarvam_client.close_client()


if __name__ == "__main__":
    asyncio.run(main())
