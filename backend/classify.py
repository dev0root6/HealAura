import json
import logging
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