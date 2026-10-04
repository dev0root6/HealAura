"""HealAura, the AI member of the community, powered by Groq.

It posts as "HealAura" with an AI label in the app, and replies when:
  - someone @mentions it (always, quickly),
  - a post mentions self-harm or suicide (always: a careful reply pointing to helplines),
  - a person posts into a quiet channel where nobody else is around (sometimes),
    so a lonely message isn't met with silence.
It stays out of live conversations between people unless asked.

Guard rails: a global rate cap, it never replies to itself, and any Groq failure
just means no reply.
"""

import asyncio
import logging
import os
import random
import time
from collections import deque
from typing import Optional

import db
import groq_client
import safety
from community_hub import AI_ALIAS, hub
from models import CommunityMessageOut

logger = logging.getLogger(__name__)

ENABLED = os.getenv("COMMUNITY_COMPANIONS", "1") != "0"
# At most this many AI replies in any rolling 10-minute window.
_MAX_REPLIES_PER_WINDOW = int(os.getenv("COMMUNITY_COMPANIONS_PER_10MIN", "12"))
_WINDOW_SECONDS = 600
_ASKED_DELAY = (2, 5)  # seconds: answering a direct @HealAura
_QUIET_DELAY = (12, 35)  # seconds: greeting a post in a quiet channel
_QUIET_REPLY_CHANCE = 0.5
# Another person posted in the channel within this window: a live conversation.
_CONVERSATION_MINUTES = 30

_SYSTEM = f"""You are {AI_ALIAS}, the AI member of HealAura's student community, a place
where students share how they're really doing. Everyone knows you are an AI.

How to reply:
- 1 to 3 short sentences, like a chat message from a kind, steady friend. No lists or headings.
- Always reply in exactly the same language mix as the message: Tanglish to Tanglish,
  Hinglish to Hinglish, English to English.
- Acknowledge the feeling first. If they asked you something, answer it plainly.
- Don't invent personal experiences or claim feelings of your own; you can note that
  many students go through this.
- No diagnoses, no medical or clinical advice, no lecturing, no toxic positivity.
- Never ask for personal details. Start by addressing the person as @their_alias.
- Plain text only."""

_CRISIS_SYSTEM = f"""You are {AI_ALIAS}, the AI member of a student support community.
The message you're replying to mentions self-harm or not wanting to live.

Reply in 2 to 3 short, warm sentences in the message's language and style, starting
with @their_alias:
- Say you're really glad they shared and that they matter.
- Gently urge them to talk to someone right now: Tele-MANAS on 14416 (free, 24x7),
  or 112 if they are in immediate danger.
- No advice beyond reaching out, no lecturing. Plain text only."""

_recent_replies: deque[float] = deque()
_tasks: set[asyncio.Task] = set()


def _budget_ok() -> bool:
    now = time.monotonic()
    while _recent_replies and now - _recent_replies[0] > _WINDOW_SECONDS:
        _recent_replies.popleft()
    return len(_recent_replies) < _MAX_REPLIES_PER_WINDOW


def _clean(text: str) -> Optional[str]:
    text = text.strip().strip('"').strip()
    return text[:600] or None


async def _reply(post: CommunityMessageOut, crisis: bool, delay: float) -> None:
    await asyncio.sleep(delay)
    if not _budget_ok():
        logger.info("HealAura reply skipped (rate cap)")
        return
    _recent_replies.append(time.monotonic())

    recent = await db.fetch_community_messages(post.channel_id, limit=10)
    context = "\n".join(f"{m.handle}: {m.content}" for m in recent if m.id != post.id and m.content)
    prompt = (
        (f"Recent messages in the channel:\n{context}\n\n" if context else "")
        + f"Reply to this message from @{post.handle}:\n{post.content or '(shared an image)'}"
    )
    try:
        text = _clean(
            await groq_client.chat(
                _CRISIS_SYSTEM if crisis else _SYSTEM, prompt, temperature=0.6 if crisis else 0.8
            )
        )
    except RuntimeError as exc:
        logger.warning("HealAura could not reply: %s", exc)
        return
    if text:
        reply = await db.insert_community_message(
            post.channel_id, AI_ALIAS, text, is_bot=True, reply_to=post.id
        )
        await hub.broadcast({"type": "message", "message": reply.model_dump(mode="json")})


def respond_later(post: CommunityMessageOut, *, asked: bool = False) -> None:
    """Decide (in the background) whether HealAura replies to a person's post."""
    if not (ENABLED and groq_client.available()) or post.is_bot or post.channel_id is None:
        return
    task = asyncio.create_task(_plan(post, asked))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _plan(post: CommunityMessageOut, asked: bool) -> None:
    crisis = safety.matches_crisis_phrase(post.content)
    if asked or crisis:
        await _reply(post, crisis, random.uniform(*_ASKED_DELAY))
        return
    others = await db.recent_human_handles(post.channel_id, _CONVERSATION_MINUTES) - {post.handle}
    if not others and random.random() < _QUIET_REPLY_CHANCE:
        await _reply(post, False, random.uniform(*_QUIET_DELAY))
