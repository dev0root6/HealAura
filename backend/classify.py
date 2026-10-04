import asyncio
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, time as _time_parse
from typing import Any, Optional

from models import VALID_SENTIMENTS, VALID_TYPES, Segment
import sarvam_client

logger = logging.getLogger(__name__)

# Verbatim system prompt from implementation.md (Sarvam Integration -> Classification call).
SYSTEM_PROMPT = """You are a segmentation and classification engine for a daily journaling app.
Input: a short daily entry, possibly in English, Tamil, Hindi, or code-mixed
(Tanglish/Hinglish).

Steps:
1. Split the input into distinct segments — each segment should cover one
   topic, memory, event, or task. A single sentence can contain more than
   one segment if it shifts topic (e.g. "X happened, also Y is tomorrow").
2. For each segment, classify:
   - type: "memory" (something that already happened, no action needed),
     "event" (has a specific date/time to be scheduled), or
     "task" (something the user says they need/plan to do, no fixed date/time)
   - sentiment: "positive", "negative", "neutral", or "mixed"
     - Base sentiment on evaluative language (e.g. "was great", "felt bad",
       "suvaiaa irundhichu"), NOT on the topic alone. A neutral fact
       ("I ate biryani") is neutral unless an opinion is attached
       ("it was tasty" -> positive).
   - date: ISO date if mentioned or inferable (e.g. "tomorrow"), else null
   - time: extracted time if present, else null
   - person: name or relation mentioned (e.g. "GF", "placement cell"), else null

Respond ONLY with a JSON array, no preamble, no markdown fences:
[
  {"segment_text": "...", "type": "...", "sentiment": "...",
   "date": "...", "time": "...", "person": "..."}
]"""

# Few-shot examples from implementation.md, formatted for the prompt.
FEW_SHOT_EXAMPLES = """
Examples:

Input: "naan inaiki biryani sapten"
Output: [
  {"segment_text": "naan inaiki biryani sapten", "type": "memory",
   "sentiment": "neutral", "date": null, "time": null, "person": null}
]

Input: "naan inaiki biryani sapten, athu suvaiaa irundhichu"
Output: [
  {"segment_text": "naan inaiki biryani sapten, athu suvaiaa irundhichu",
   "type": "memory", "sentiment": "positive", "date": null, "time": null,
   "person": null}
]

Input: "nalaiki en GF oda meeting iruku"
Output: [
  {"segment_text": "nalaiki en GF oda meeting iruku", "type": "event",
   "sentiment": "neutral", "date": "tomorrow", "time": null, "person": "GF"}
]

Input: "ellarum app pathi paratunanga aana enakku incomplete-aa irundhichu,
so inum develop pananum"
Output: [
  {"segment_text": "ellarum app pathi paratunanga aana enakku incomplete-aa
irundhichu, so inum develop pananum", "type": "task", "sentiment": "mixed",
   "date": null, "time": null, "person": null}
]"""

FULL_SYSTEM_PROMPT = SYSTEM_PROMPT + FEW_SHOT_EXAMPLES

_RELATIVE_DATES = {
    "today": lambda: date.today(),
    "tomorrow": lambda: date.today() + timedelta(days=1),
    "day after tomorrow": lambda: date.today() + timedelta(days=2),
    "yesterday": lambda: date.today() - timedelta(days=1),
    "tmr": lambda: date.today() + timedelta(days=1),
    "day after": lambda: date.today() + timedelta(days=2),
}

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text.strip())


def _resolve_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _RELATIVE_DATES:
            return _RELATIVE_DATES[key]()
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            pass
    return None


def _resolve_time(value: Any) -> Optional[_time_parse]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            return _time_parse.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def parse_segments(content: str) -> list[Segment]:
    """Parse the model's JSON array into validated Segment objects."""
    text = _strip_fences(content)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        _start = text.find("[")
        _end = text.rfind("]")
        if _start == -1 or _end <= _start:
            raise
        data = json.loads(text[_start : _end + 1])

    if not isinstance(data, list):
        raise ValueError("Expected a JSON array from model")

    segments: list[Segment] = []
    for item in data:
        if not isinstance(item, dict):
            logger.warning("Skipping non-object segment item: %r", item)
            continue
        try:
            valid = Segment(
                segment_text=str(item.get("segment_text", ""))[:2000],
                type=str(item.get("type", "")).strip().lower(),
                sentiment=str(item.get("sentiment", "")).strip().lower(),
                event_date=_resolve_date(item.get("date")),
                event_time=_resolve_time(item.get("time")),
                person=item.get("person") if isinstance(item.get("person"), str) else None,
            )
            # Validate type/sentiment against the allowed enumerations.
            if valid.type not in VALID_TYPES:
                raise ValueError(f"invalid type: {valid.type!r}")
            if valid.sentiment not in VALID_SENTIMENTS:
                raise ValueError(f"invalid sentiment: {valid.sentiment!r}")
        except (ValueError, TypeError) as exc:
            logger.warning("Dropping malformed segment: %s (%r)", exc, item)
            continue
        segments.append(valid)
    return segments


async def classify_entry(raw_text: str) -> tuple[list[Segment], bool]:
    """Classify a raw journal entry into validated segments.

    Returns (segments, used_fallback). On total JSON failure, falls back to a
    single 'memory'/'neutral' segment so the raw text is still stored.
    """
    last_error: Optional[BaseException] = None
    had_api_error = False
    for _attempt in range(3):
        try:
            content = await sarvam_client.chat_completion(FULL_SYSTEM_PROMPT, raw_text)
        except RuntimeError as exc:
            last_error = exc
            had_api_error = True
            continue

        if not isinstance(content, str) or not content.strip():
            last_error = ValueError("Sarvam returned empty content")
            continue

        try:
            segments = parse_segments(content)
            if segments:
                return segments, False
            last_error = ValueError("No valid segments parsed")
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            continue

    if had_api_error:
        raise last_error if last_error else RuntimeError("Sarvam classification failed")
    logger.warning("Sarvam classification ultimately failed; using fallback. %s", last_error)
    return [_fallback_segment(raw_text)], True


def _fallback_segment(raw_text: str) -> Segment:
    return Segment(
        segment_text=raw_text[:2000],
        type="memory",
        sentiment="neutral",
    )

# --- confidence by self-consistency ----------------------------------------
#
# The model gives no usable probability, so confidence is estimated by asking
# again: CONFIDENCE_SAMPLES extra classifications run at a higher temperature,
# concurrently with the main one. A segment's confidence is the share of runs
# (main + successful extra samples) that gave its best-matching segment the
# same type and sentiment. Low-confidence segments are the ones worth asking
# the user about — the active-learning query step.

CONFIDENCE_SAMPLES = int(os.getenv("CONFIDENCE_SAMPLES", "2"))
_SAMPLE_TEMPERATURE = 0.7
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _best_match(segment: Segment, candidates: list[Segment]) -> Optional[Segment]:
    """The candidate segment whose words overlap `segment` the most (Jaccard)."""
    target = _words(segment.segment_text)
    best, best_score = None, 0.0
    for cand in candidates:
        words = _words(cand.segment_text)
        union = target | words
        score = len(target & words) / len(union) if union else 0.0
        if score > best_score:
            best, best_score = cand, score
    return best


def score_confidence(primary: list[Segment], samples: list[list[Segment]]) -> list[Segment]:
    """Return `primary` with ai_confidence filled from agreement with `samples`.

    With no samples there is nothing to compare against, so confidence stays None.
    """
    if not samples:
        return primary
    scored = []
    for seg in primary:
        agree = 1  # the primary run agrees with itself
        for sample in samples:
            match = _best_match(seg, sample)
            if match and match.type == seg.type and match.sentiment == seg.sentiment:
                agree += 1
        scored.append(seg.model_copy(update={"ai_confidence": round(agree / (1 + len(samples)), 3)}))
    return scored


async def _sample_once(raw_text: str) -> Optional[list[Segment]]:
    """One extra, higher-temperature classification. Any failure yields None."""
    try:
        content = await sarvam_client.chat_completion(
            FULL_SYSTEM_PROMPT, raw_text, temperature=_SAMPLE_TEMPERATURE
        )
        segments = parse_segments(content or "")
        return segments or None
    except (RuntimeError, ValueError):
        return None


async def classify_with_confidence(raw_text: str) -> tuple[list[Segment], bool]:
    """classify_entry plus a self-consistency confidence on each segment.

    Extra samples never fail the entry: if they error out, the segments are
    returned without a confidence, exactly as classify_entry would.
    """
    if CONFIDENCE_SAMPLES <= 0:
        return await classify_entry(raw_text)
    primary, *extra = await asyncio.gather(
        classify_entry(raw_text),
        *(_sample_once(raw_text) for _ in range(CONFIDENCE_SAMPLES)),
        return_exceptions=True,
    )
    if isinstance(primary, BaseException):
        raise primary
    segments, used_fallback = primary
    if used_fallback:
        return segments, used_fallback
    samples = [s for s in extra if isinstance(s, list)]
    return score_confidence(segments, samples), used_fallback
