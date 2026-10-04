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

Separately, set "crisis" to true ONLY if the user mentions wanting to die,
suicide, ending their life, or hurting themselves, in any language. Sadness,
stress, or hopelessness without that is NOT a crisis. A crisis always also
needs support.

Respond ONLY with JSON, no markdown fences:
{"reply": "...", "needs_support": true|false, "crisis": true|false}

Examples:
Input: "naan inaiki biryani sapten, athu suvaiaa irundhichu"
Output: {"reply": "aha, nalla iruku", "needs_support": false, "crisis": false}

Input: "presentation went badly today, felt stupid the whole time"
Output: {"reply": "hmm. that sucks", "needs_support": false, "crisis": false}

Input: "i don't see the point anymore, nothing is getting better"
Output: {"reply": "i'm here. keep talking", "needs_support": true, "crisis": false}

Input: "enakku saaganum pola iruku, ellam mudinjiduchu"
Output: {"reply": "naan inga irukken. please stay", "needs_support": true, "crisis": true}

Input: "s.u.i.c.i.d.e is all i think about"
Output: {"reply": "i'm here with you. please stay.", "needs_support": true, "crisis": true}"""

CONVERSE_PROMPT = """You are HealAura, a warm, attentive companion in a personal reflection app.
The user has chosen "conversation" mode: they want you to actually talk with them,
not just acknowledge. You are NOT a therapist and you don't diagnose.

How to reply:
- 2 to 4 short sentences, like a caring friend who listens well.
- First show you understood: reflect the specific thing they said and how it felt.
- Then ask ONE gentle, open question that helps them go a little deeper
  ("what part of it stayed with you most?", "how did you feel after?").
- Remember what they said earlier in this conversation and refer back when it fits.
- Match their language and register exactly: Tanglish to Tanglish, Hinglish to
  Hinglish, English to English.
- No lists, no lectures, no "have you tried", no emoji. Advice only if they ask for it.
- If they mention self-harm or not wanting to live: say clearly that you're glad
  they told you, that they matter, and urge them to call Tele-MANAS on 14416 or
  112 if in immediate danger. Keep that reply short and caring.

Also judge "needs_support" (sustained distress, hopelessness, self-harm, explicit
request for help; NOT ordinary bad days) and "crisis" (mentions wanting to die,
suicide, ending their life or hurting themselves, in any language).

Respond ONLY with JSON, no markdown fences:
{"reply": "...", "needs_support": true|false, "crisis": true|false}"""

# Most recent turns sent to the model in conversation mode.
_HISTORY_TURNS = 12
# Conversation replies are longer than back-channel noises.
_MAX_CONVERSE_CHARS = 700

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


def _parse(content: str, max_chars: int = _MAX_REPLY_CHARS) -> Optional[tuple[str, bool, bool]]:
    text = _FENCE_RE.sub("", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        # The model sometimes answers in plain text instead of JSON. The words
        # are still a good reply; the flags just default to off (the phrase
        # safety net in safety.py still checks the user's own words).
        plain = text.strip().strip('"').strip()
        return (plain[:max_chars], False, False) if plain else None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return None
    crisis = data.get("crisis") is True
    return reply.strip()[:max_chars], bool(data.get("needs_support")) or crisis, crisis


def _with_language(system_prompt: str, language: Optional[str], name: Optional[str] = None) -> str:
    """Add the person's language preference (and name) to a system prompt.

    The examples in the prompts are Tamil/Tanglish; without this, an ambiguous
    English message could get a Tamil reply. The person's own words always win.
    """
    from models import LANGUAGES

    label = LANGUAGES.get(language or "", "English")
    note = (
        "\n\nLanguage: reply in the same language and script the person just wrote in. "
        "If their message is plain English, reply in plain English: do NOT switch to Tamil, "
        "Tanglish, Hindi or Hinglish unless their own message uses it. The examples above are "
        "only examples of matching style, not a language to use. "
        f"If the language is unclear, use their preferred language: {label}."
    )
    if name:
        note += f" They like to be called {name}; use it occasionally, not every time."
    return system_prompt + note


async def respond(
    raw_text: str, language: Optional[str] = None, name: Optional[str] = None
) -> tuple[str, bool, bool]:
    """Return (reply, needs_support, crisis) for one entry.

    `crisis` here is only the model's judgement; callers combine it with the
    phrase safety net in safety.py, which also covers the fallback paths below.

    Never raises: a failed backchannel must not fail the entry it belongs to.
    """
    try:
        content = await sarvam_client.chat_completion(
            _with_language(BACKCHANNEL_PROMPT, language), raw_text, temperature=0.7, max_tokens=200
        )
    except RuntimeError as exc:
        logger.warning("Backchannel call failed: %s", exc)
        return random.choice(FALLBACK_REPLIES), False, False

    parsed = _parse(content or "")
    if parsed is None:
        logger.warning("Unparseable backchannel response: %r", (content or "")[:200])
        return random.choice(FALLBACK_REPLIES), False, False
    return parsed


def _format_history(history: list[tuple[str, str]]) -> str:
    lines = [f"{'User' if role == 'user' else 'HealAura'}: {content}" for role, content in history]
    return "\n".join(lines[-_HISTORY_TURNS:])


async def converse(
    raw_text: str,
    history: list[tuple[str, str]],
    language: Optional[str] = None,
    name: Optional[str] = None,
) -> tuple[str, bool, bool]:
    """Conversation mode: (reply, needs_support, crisis), using today's earlier turns.

    Never raises: on any failure it falls back to the short back-channel reply.
    """
    context = _format_history(history)
    prompt = (f"Earlier in this conversation:\n{context}\n\n" if context else "") + f"User now says:\n{raw_text}"
    try:
        content = await sarvam_client.chat_completion(
            _with_language(CONVERSE_PROMPT, language, name), prompt, temperature=0.7, max_tokens=500
        )
    except RuntimeError as exc:
        logger.warning("Conversation reply failed, using back-channel: %s", exc)
        return await respond(raw_text, language)
    parsed = _parse(content or "", max_chars=_MAX_CONVERSE_CHARS)
    if parsed is None:
        logger.warning("Unparseable conversation reply: %r", (content or "")[:200])
        return await respond(raw_text, language)
    return parsed


async def suggest(raw_text: str, language: Optional[str] = None) -> str:
    """Answer an explicit request for advice about what the user wrote."""
    content = await sarvam_client.chat_completion(
        _with_language(SUGGEST_PROMPT, language), raw_text, temperature=0.5, max_tokens=400
    )
    return (content or "").strip()
