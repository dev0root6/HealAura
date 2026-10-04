"""Community: Discord-style channels with a live WebSocket feed.

People post under a community alias they choose (unique, never linked to their
login in the API). @alias mentions notify that person live; @HealAura asks the
AI. Messages and images disappear after 24 hours.
"""

import asyncio
import io
import json
import logging
import re
import time
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, WebSocket, WebSocketDisconnect
from PIL import Image, ImageOps, UnidentifiedImageError

import auth
import companions
import db
from community_hub import AI_ALIAS, alias_problem, hub, mentions
from models import AliasIn, ChannelIn, ChannelOut, CommunityMessageIn, CommunityMessageOut, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/community", tags=["community"])

_AUTH_TIMEOUT_SECONDS = 10
_TYPING_EVERY_SECONDS = 2.0
_MAX_NEW_CHANNELS_PER_DAY = 3
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_MAX_IMAGE_BYTES = 8 * 1024 * 1024
_MAX_IMAGE_SIDE = 1600


def _slugify(name: str) -> str:
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-")[:32]


async def _channel_or_404(channel_id: UUID) -> ChannelOut:
    channel = await db.get_channel(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return channel


async def _require_alias(user: UserOut) -> str:
    alias = await db.get_alias(user.id)
    if not alias:
        raise HTTPException(status_code=409, detail="Choose a community alias first.")
    return alias


# --- alias ---

@router.get("/alias")
async def get_my_alias(user: UserOut = Depends(auth.get_current_user)) -> dict:
    return {"alias": await db.get_alias(user.id)}


@router.get("/alias/check")
async def check_alias(
    name: str = Query(min_length=1, max_length=40), user: UserOut = Depends(auth.get_current_user)
) -> dict:
    """Live availability check while someone types an alias."""
    problem = alias_problem(name)
    if problem:
        return {"available": False, "reason": problem}
    owner = await db.alias_owner(name)
    if owner and owner != user.id:
        return {"available": False, "reason": f"@{name} is already taken."}
    return {"available": True, "reason": None}


@router.put("/alias")
async def set_my_alias(payload: AliasIn, user: UserOut = Depends(auth.get_current_user)) -> dict:
    alias = payload.alias.strip()
    problem = alias_problem(alias)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    try:
        await db.set_alias(user.id, alias)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail=f"@{alias} is already taken.") from exc
    await hub.rename(user.id, alias)
    return {"alias": alias}


@router.get("/members")
async def search_members(
    q: str = Query(default="", max_length=20), user: UserOut = Depends(auth.get_current_user)
) -> list[dict]:
    """Aliases for @mention autocomplete. HealAura (the AI) is always offered."""
    found = await db.search_aliases(q.strip(), limit=8)
    mine = await db.get_alias(user.id)
    people = [{"alias": a, "is_ai": False} for a in found if a != mine]
    ai = [{"alias": AI_ALIAS, "is_ai": True}] if AI_ALIAS.lower().startswith(q.strip().lower()) else []
    return ai + people


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
    """Post under the person's alias; everyone connected sees it live, and @mentions are notified."""
    channel = await _channel_or_404(channel_id)
    alias = await _require_alias(user)
    content = payload.content.strip()
    if not content and not payload.image_id:
        raise HTTPException(status_code=422, detail="Write something or attach an image.")

    posted = await db.insert_community_message(channel_id, alias, content, image_id=payload.image_id)
    await hub.broadcast({"type": "message", "message": posted.model_dump(mode="json")})

    tagged = mentions(content)
    people = await db.users_for_aliases([a for a in tagged if a.lower() != AI_ALIAS.lower()])
    notify = {uid for uid in people.values() if uid != user.id}
    if notify:
        await hub.send_to_users(
            notify,
            {
                "type": "mention",
                "channel_id": str(channel_id),
                "channel_name": channel.name,
                "from": alias,
                "message": posted.model_dump(mode="json"),
            },
        )
    companions.respond_later(posted, asked=any(a.lower() == AI_ALIAS.lower() for a in tagged))
    return posted


# --- images (auto-deleted after 24 hours) ---

@router.post("/images")
async def upload_image(
    file: UploadFile = File(...), _user: UserOut = Depends(auth.get_current_user)
) -> dict:
    """Accept a photo, re-encode it (drops EXIF/GPS and anything hidden in the file), store it for 24 h."""
    raw = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Images can be up to 8 MB.")

    def process() -> tuple[bytes, int, int]:
        with Image.open(io.BytesIO(raw)) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((_MAX_IMAGE_SIDE, _MAX_IMAGE_SIDE))
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            out = io.BytesIO()
            img.save(out, format="WEBP", quality=82, method=4)
            return out.getvalue(), img.width, img.height

    try:
        data, width, height = await asyncio.to_thread(process)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="That file isn't an image we can read.") from exc
    image_id = await db.insert_image(data, "image/webp", width, height)
    return {"id": str(image_id), "url": f"/community/images/{image_id}", "width": width, "height": height}


@router.get("/images/{image_id}")
async def get_image(image_id: UUID) -> Response:
    """Serve a shared image. Ids are random and expire after 24 hours."""
    image = await db.get_image(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="This image has expired.")
    return Response(
        content=image["data"],
        media_type=image["mime"],
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


# --- live socket ---

@router.websocket("/ws")
async def community_socket(ws: WebSocket) -> None:
    """Live feed for all channels.

    Client -> server frames:
      {"type": "auth", "token": "..."}   first frame, required (token stays out of URLs/logs)
      {"type": "view", "channel_id": ...} which channel this tab is showing
      {"type": "typing"}                  the person is typing in the viewed channel
    Server -> client frames: hello, message, channel, presence, typing, mention.
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

    alias = await db.get_alias(user.id)
    await ws.send_text(json.dumps({"type": "hello", "handle": alias}))
    await hub.join(ws, alias or f"guest-{str(user.id)[:6]}", user.id)
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
                current = hub.handle_of(ws)  # kept up to date by hub.rename
                if current and not current.startswith("guest-"):
                    await hub.broadcast(
                        {"type": "typing", "handle": current, "channel_id": viewing},
                        exclude=ws,
                        channel=viewing,
                    )
    except WebSocketDisconnect:
        pass
    finally:
        await hub.leave(ws)
