"""Community: Discord-style anonymous channels with a live WebSocket feed.

People post under a per-day anonymous handle (see community_hub.handle_for);
messages and channels are never linked back to an account in the API.
"""

import asyncio
import json
import logging
import re
import time
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

import auth
import companions
import db
from community_hub import handle_for, hub
from models import ChannelIn, ChannelOut, CommunityMessageIn, CommunityMessageOut, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/community", tags=["community"])

_AUTH_TIMEOUT_SECONDS = 10
_TYPING_EVERY_SECONDS = 2.0
_MAX_NEW_CHANNELS_PER_DAY = 3
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-")[:32]


async def _channel_or_404(channel_id: UUID) -> ChannelOut:
    channel = await db.get_channel(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


# --- channels ---

@router.get("/channels", response_model=list[ChannelOut])
async def list_channels(_user: UserOut = Depends(auth.get_current_user)) -> list[ChannelOut]:
    return await db.list_channels()


@router.post("/channels", response_model=ChannelOut)
async def create_channel(
    payload: ChannelIn, user: UserOut = Depends(auth.get_current_user)
) -> ChannelOut:
    """Anyone can open a channel (a few a day, to keep the list tidy)."""
    slug = _slugify(payload.name)
    if len(slug) < 2:
        raise HTTPException(status_code=422, detail="Use at least 2 letters or numbers in the name.")
    if await db.channels_created_since(user.id, 24) >= _MAX_NEW_CHANNELS_PER_DAY:
        raise HTTPException(status_code=429, detail="You can create up to 3 channels a day.")
    try:
        channel = await db.create_channel(slug, payload.description.strip(), user.id)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail=f"#{slug} already exists.") from exc
    await hub.broadcast({"type": "channel", "channel": channel.model_dump(mode="json")})
    return channel


@router.get("/channels/{channel_id}/messages", response_model=list[CommunityMessageOut])
async def channel_messages(
    channel_id: UUID, _user: UserOut = Depends(auth.get_current_user)
) -> list[CommunityMessageOut]:
    await _channel_or_404(channel_id)
    return await db.fetch_community_messages(channel_id)


@router.post("/channels/{channel_id}/messages", response_model=CommunityMessageOut)
async def post_message(
    channel_id: UUID, payload: CommunityMessageIn, user: UserOut = Depends(auth.get_current_user)
) -> CommunityMessageOut:
    """Post under today's anonymous handle; everyone connected sees it live."""
    await _channel_or_404(channel_id)
    posted = await db.insert_community_message(channel_id, handle_for(user.id), payload.content.strip())
    await hub.broadcast({"type": "message", "message": posted.model_dump(mode="json")})
    companions.respond_later(posted)
    return posted


@router.get("/me")
async def my_handle(user: UserOut = Depends(auth.get_current_user)) -> dict:
    """The caller's anonymous handle for today, so the app can mark their own messages."""
    return {"handle": handle_for(user.id)}


# --- live socket ---

@router.websocket("/ws")
async def community_socket(ws: WebSocket) -> None:
    """Live feed for all channels.

    Client -> server frames:
      {"type": "auth", "token": "..."}   first frame, required (token stays out of URLs/logs)
      {"type": "view", "channel_id": ...} which channel this tab is showing
      {"type": "typing"}                  the person is typing in the viewed channel
    Server -> client frames: hello, message, channel, presence, typing.
    """
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), _AUTH_TIMEOUT_SECONDS))
        token = str(first.get("token", "")) if first.get("type") == "auth" else ""
        user = await db.fetch_user_by_token(token) if token else None
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect):
        user = None
    if user is None:
        await ws.close(code=4401, reason="Not authenticated")
        return

    handle = handle_for(user.id)
    await ws.send_text(json.dumps({"type": "hello", "handle": handle}))
    await hub.join(ws, handle)
    viewing: str | None = None
    last_typing = 0.0
    try:
        while True:
            try:
                event = json.loads(await ws.receive_text())
            except ValueError:
                continue
            kind = event.get("type")
            if kind == "view" and isinstance(event.get("channel_id"), str):
                viewing = event["channel_id"]
                await hub.view(ws, viewing)
            elif kind == "typing" and viewing and time.monotonic() - last_typing > _TYPING_EVERY_SECONDS:
                last_typing = time.monotonic()
                await hub.broadcast(
                    {"type": "typing", "handle": handle, "channel_id": viewing},
                    exclude=ws,
                    channel=viewing,
                )
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(ws)
