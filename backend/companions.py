"""AI companions for the community channel, powered by Groq.

When a person posts, one or two companions reply after a short, human-feeling
delay, like peers in a student support group would. Companion replies are
stored with is_bot = true and shown with an "AI" label in the app; they are
never presented as real people.

Guard rails:
  - only human posts get replies (companions never talk to each other),
  - a global rate cap so a busy channel can't run up API usage,
  - a post that mentions self-harm or suicide gets one careful reply that points
    to helplines, instead of casual chat,
  - any Groq failure just means no reply.
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
from community_hub import hub
from models import CommunityMessageOut

logger = logging.getLogger(__name__)

ENABLED = os.getenv("COMMUNITY_COMPANIONS", "1") != "0"
# At most this many companion replies in any rolling 10-minute window.
_MAX_REPLIES_PER_WINDOW = int(os.getenv("COMMUNITY_COMPANIONS_PER_10MIN", "12"))
_WINDOW_SECONDS = 600
_DELAY_RANGE = (12, 45)  # seconds before a companion "types" its reply
# Another person posted in the channel within this window: a live conversation.
_CONVERSATION_MINUTES = 5

PERSONAS = [
    {
        "handle": "WarmLark",
        "who": "a final-year engineering student from Chennai, gentle and a little funny",
    },
    {
        "handle": "SteadyHeron",
        "who": "an MBA student from Pune, calm and practical",
    },
    {
        "handle": "QuietOwl",
        "who": "a night-owl postgraduate student who writes short, thoughtful messages in English",
    },
    {
        "handle": "BrightFinch",
        "who": "a first-year student, warm and encouraging, who remembers how overwhelming starting out felt",
    },
    {
        "handle": "KindKoala",
        "who": "a second-year arts student from Kochi who listens well and asks soft follow-up questions",
    },
]

_SYSTEM = """You are {handle}, {who}. You are an AI companion in HealAura's anonymous
student community channel, where students share how they're really doing.

How to reply:
- 1 to 3 short sentences, like a chat message from a kind peer. No lists, no headings.
- Always reply in exactly the same language mix as the post: Tanglish to Tanglish,
  Hinglish to Hinglish, English to English, whatever your own background.
- Acknowledge the feeling first. Don't invent personal experiences or claim feelings
  of your own; relate by noting that many students go through this.
- No diagnoses, no medical or clinical advice, no lecturing, no toxic positivity.
- Don't mention being an AI unless someone asks; if asked, say honestly that you are
  an AI companion here to keep people company.
- Never ask for personal details. Never use the poster's real name.
- Plain text only. Address the poster by their handle at most once."""

_CRISIS_SYSTEM = """You are {handle}, an AI companion in a student support community.
The post you're replying to mentions self-harm or not wanting to live.

Reply in 2 to 3 short, warm sentences in the post's language and style:
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
    if not text:
        return None
    return text[:500]


async def _reply(persona: dict, post: CommunityMessageOut, crisis: bool, delay: float) -> None:
    await asyncio.sleep(delay)
    if not _budget_ok():
        logger.info("Companion reply skipped (rate cap)")
        return
    _recent_replies.append(time.monotonic())

    system = (_CRISIS_SYSTEM if crisis else _SYSTEM).format(**persona)
    # A little channel context so replies don't feel detached.
    recent = await db.fetch_community_messages(post.channel_id, limit=8)
    context = "\n".join(f"{m.handle}: {m.content}" for m in recent if m.id != post.id)
    prompt = (
        (f"Recent messages in the channel:\n{context}\n\n" if context else "")
        + f"Reply to this post from {post.handle}:\n{post.content}"
    )
    try:
        text = _clean(await groq_client.chat(system, prompt, temperature=0.6 if crisis else 0.9))
    except RuntimeError as exc:
        logger.warning("Companion %s could not reply: %s", persona["handle"], exc)
        return
    if text:
        reply = await db.insert_community_message(
            post.channel_id, persona["handle"], text, is_bot=True, reply_to=post.id
        )
        await hub.broadcast({"type": "message", "message": reply.model_dump(mode="json")})


def respond_later(post: CommunityMessageOut) -> None:
    """Schedule companion replies to a human post. Returns immediately."""
    if not (ENABLED and groq_client.available()) or post.is_bot or post.channel_id is None:
        return
    task = asyncio.create_task(_plan(post))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _plan(post: CommunityMessageOut) -> None:
    crisis = safety.matches_crisis_phrase(post.content)
    # When real people are already talking to each other, companions step
    # back, except for a crisis post, which always gets the helpline reply.
    others = await db.recent_human_handles(post.channel_id, _CONVERSATION_MINUTES) - {post.handle}
    if others and not crisis:
        return
    count = 1 if crisis else random.choice([1, 1, 2])
    personas = random.sample(PERSONAS, count)
    delay = 0.0
    for persona in personas:
        delay += random.uniform(*_DELAY_RANGE)
        task = asyncio.create_task(_reply(persona, post, crisis, delay))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
