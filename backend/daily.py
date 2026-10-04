"""'Your daily day life': a diary page written from a day's entries.

HealAura is a diary at heart. At any point in the day, this turns what the
person said (and what HealAura picked up: memories, events, tasks, feelings)
into a short first-person diary page, in their language. It is regenerated only
when there are new entries since the last page, so revisiting is free.
"""

import json
import logging
import re
from datetime import date
from typing import Optional
from uuid import UUID

import db
import sarvam_client
from models import LANGUAGES, UserOut

logger = logging.getLogger(__name__)

PROMPT = """You write the person's diary for them. You are given everything they told
their journaling app today, plus what the app picked up (memories, events, tasks, and
how each moment felt). Write today's diary page.

Rules:
- First person, as the person themself ("Today I ..."), warm and honest, like a real diary.
- 90 to 170 words for "body". Weave the moments into a flowing story of the day, in order.
  Keep their own words and small details where you can. Don't invent anything.
- Name feelings plainly; don't diagnose or give advice. If the day was hard, be gentle.
- If they mentioned self-harm or not wanting to live, don't repeat details; write one gentle
  line that today was very heavy and that reaching out matters.
- Write in the language they mostly wrote in today (Tanglish stays Tanglish, Hinglish stays
  Hinglish, English stays English). If unclear, use: {language}.

Respond ONLY with JSON, no markdown fences:
{{"title": "a short title for the day, 3-7 words",
  "body": "the diary page",
  "mood": "one or two words for the overall feeling",
  "highlights": ["up to 3 short moments worth remembering"],
  "looking_ahead": ["upcoming events or tasks they mentioned, short; empty if none"]}}"""

_FENCE_RE = re.compile(r"^```(?:json)?\\s*|\\s*```$")


def _material(messages, entries) -> str:
    lines = ["What they said today (in order):"]
    for m in messages:
        if m.role == "user":
            lines.append(f"- [{m.created_at.strftime('%H:%M')}] {m.content}")
    if entries:
        lines.append("\nWhat the app picked up:")
        for e in entries:
            kind = e.corrected_type or e.entry_type
            feel = e.corrected_sentiment or e.sentiment
            extra = ", ".join(
                x for x in (
                    f"with {e.person}" if e.person else "",
                    f"on {e.event_date}" if e.event_date else "",
                    f"at {e.event_time.strftime('%H:%M')}" if e.event_time else "",
                ) if x
            )
            lines.append(f"- {kind} ({feel}){': ' + extra if extra else ''}: {e.segment_text}")
    return "\n".join(lines)


def _parse(content: str) -> Optional[dict]:
    text = _FENCE_RE.sub("", (content or "").strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    title, body = str(data.get("title", "")).strip(), str(data.get("body", "")).strip()
    if not title or not body:
        return None

    def strings(key: str) -> list[str]:
        value = data.get(key) or []
        return [str(v).strip()[:160] for v in value if str(v).strip()][:5] if isinstance(value, list) else []

    return {
        "title": title[:120],
        "body": body[:3000],
        "mood": (str(data.get("mood") or "").strip()[:40] or None),
        "highlights": strings("highlights"),
        "looking_ahead": strings("looking_ahead"),
    }


async def summary_for(user: UserOut, day: date, *, refresh: bool = False) -> Optional[dict]:
    """The diary page for one day, generating it if it's missing or out of date.

    Returns None when the person wrote nothing that day. Raises RuntimeError if
    the model can't be reached and there's no earlier page to show.
    """
    messages = [m for m in await db.fetch_messages_by_date(user.id, day) if m.role == "user"]
    if not messages:
        return None
    existing = await db.get_day_summary(user.id, day)
    if existing and existing["entry_count"] == len(messages) and not refresh:
        return existing

    entries = await db.fetch_entries_by_date(user.id, day)
    language = LANGUAGES.get(user.language or "", "English")
    try:
        content = await sarvam_client.chat_completion(
            PROMPT.format(language=language), _material(messages, entries), temperature=0.6, max_tokens=900
        )
    except RuntimeError:
        if existing:
            return existing  # stale beats nothing
        raise
    data = _parse(content)
    if data is None:
        logger.warning("Unparseable day summary: %r", (content or "")[:200])
        if existing:
            return existing
        raise RuntimeError("Couldn't write today's page right now. Try again in a moment.")
    return await db.save_day_summary(user.id, day, data, len(messages))
