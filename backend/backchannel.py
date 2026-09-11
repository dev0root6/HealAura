"""Minimal conversational responses to a journal entry.

The app listens more than it talks: after an entry the user gets a short
acknowledgement ("hmm", "is it so?"), not analysis and not advice. Advice is a
separate, explicit action — see suggest().
"""

import json
import logging
import random
import re
from typing import Optional

import sarvam_client

logger = logging.getLogger(__name__)

BACKCHANNEL_PROMPT = """You are a quiet listener in a personal journaling app.
The user has just told you about their day. You are NOT a therapist and NOT an
assistant — you are the sound someone makes when they are listening.

Rules:
- Reply with at most 6 words. Usually 1-3.
- Acknowledge, do not analyse. No advice, no reframing, no "have you tried".
- No praise, no "that's wonderful", no emoji.
- Match the user's language and register exactly. If they wrote Tanglish,
  reply in Tanglish. If Hindi, reply in Hindi. If English, English.
- Occasionally (not every time) a short natural question is fine:
  "aprom?", "then what happened?", "you okay?"
- Never repeat the user's own words back at them.

Also judge whether the user sounds like they are struggling enough that a
human should check in — sustained distress, hopelessness, self-harm, or an
explicit request for help. Ordinary bad days are NOT this.

Respond ONLY with JSON, no markdown fences:
{"reply": "...", "needs_support": true|false}

Examples:
Input: "naan inaiki biryani sapten, athu suvaiaa irundhichu"
Output: {"reply": "aha, nalla iruku", "needs_support": false}

Input: "presentation went badly today, felt stupid the whole time"
Output: {"reply": "hmm. that sucks", "needs_support": false}

Input: "i don't see the point anymore, nothing is getting better"
Output: {"reply": "i'm here. keep talking", "needs_support": true}"""

SUGGEST_PROMPT = """You are a calm, practical companion in a journaling app.
The user has explicitly asked you for a suggestion about what they wrote.

Rules:
- At most 3 sentences.
- One concrete, small, doable thing — not a list, not a lifestyle overhaul.
- No diagnosis, no clinical language, no "as an AI".
- Match the user's language, including code-mixed Tanglish/Hinglish.
- If the entry suggests real distress, say plainly that talking to someone
  would help more than anything you can offer, and stop there.

Respond with plain text only."""

# Used when Sarvam is unreachable or returns nothing usable. Deliberately
# content-free — a wrong guess is worse than a neutral noise.
FALLBACK_REPLIES = ["hmm", "mm", "i see", "go on", "okay"]

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")
_MAX_REPLY_CHARS = 120


def _parse(content: str) -> Optional[tuple[str, bool]]:
    text = _FENCE_RE.sub("", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return None
    return reply.strip()[:_MAX_REPLY_CHARS], bool(data.get("needs_support"))


async def respond(raw_text: str) -> tuple[str, bool]:
    """Return (reply, needs_support) for one entry.

    Never raises: a failed backchannel must not fail the entry it belongs to.
    """
    try:
        content = await sarvam_client.chat_completion(
            BACKCHANNEL_PROMPT, raw_text, temperature=0.7, max_tokens=200
        )
    except RuntimeError as exc:
        logger.warning("Backchannel call failed: %s", exc)
        return random.choice(FALLBACK_REPLIES), False

    parsed = _parse(content or "")
    if parsed is None:
        logger.warning("Unparseable backchannel response: %r", (content or "")[:200])
        return random.choice(FALLBACK_REPLIES), False
    return parsed


async def suggest(raw_text: str) -> str:
    """Answer an explicit request for advice about what the user wrote."""
    content = await sarvam_client.chat_completion(
        SUGGEST_PROMPT, raw_text, temperature=0.5, max_tokens=400
    )
    return (content or "").strip()
