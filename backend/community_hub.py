"""Real-time fan-out for the community, plus alias and @mention rules.

Every open Community tab holds one WebSocket here. New messages (from people
and from companions), who-is-typing hints and the online count are pushed to
all of them, so the channel works as a live chat room.

State is in-process: run the API as a single worker (the default for
`uvicorn main:app`). Several workers would each have their own room.
"""

import asyncio
import json
import re
from uuid import UUID

from fastapi import WebSocket

# The AI's name in the community; nobody else can take it.
AI_ALIAS = "HealAura"
RESERVED_ALIASES = {
    "healaura", "heal_aura", "admin", "admins", "moderator", "mod", "mods", "system",
    "everyone", "here", "channel", "ai", "bot", "support", "staff", "you",
}
ALIAS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,19}$")
MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{2,19})\b")


def alias_problem(alias: str) -> str | None:
    """Why an alias can't be used, or None if it's fine (availability checked separately)."""
    if not ALIAS_RE.match(alias):
        return "3–20 characters: letters, numbers or _, starting with a letter."
    if alias.lower() in RESERVED_ALIASES or alias.lower().startswith("healaura"):
        return "That name is reserved."
    return None


def mentions(text: str) -> list[str]:
    """Distinct @aliases in a message, in order."""
    seen: dict[str, str] = {}
    for m in MENTION_RE.finditer(text or ""):
        seen.setdefault(m.group(1).lower(), m.group(1))
    return list(seen.values())


class Hub:
    """Open sockets, each with its person's handle and the channel they're viewing."""

    def __init__(self) -> None:
        self._clients: dict[WebSocket, dict] = {}  # socket -> {"handle", "user", "channel"}
        self._lock = asyncio.Lock()

    def online(self) -> int:
        # The same person in two tabs counts once.
        return len({c["handle"] for c in self._clients.values()})

    def presence(self) -> dict:
        """Distinct people online overall, and per channel they're viewing."""
        per: dict[str, set[str]] = {}
        for c in self._clients.values():
            if c["channel"]:
                per.setdefault(c["channel"], set()).add(c["handle"])
        return {"online": self.online(), "channels": {k: len(v) for k, v in per.items()}}

    async def join(self, ws: WebSocket, handle: str, user_id: UUID) -> None:
        async with self._lock:
            self._clients[ws] = {"handle": handle, "user": user_id, "channel": None}

    def handle_of(self, ws: WebSocket) -> str | None:
        info = self._clients.get(ws)
        return info["handle"] if info else None

    async def rename(self, user_id: UUID, handle: str) -> None:
        """A person changed their alias: update their open sockets."""
        for info in self._clients.values():
            if info["user"] == user_id:
                info["handle"] = handle
        await self.broadcast_presence()

    async def send_to_users(self, user_ids: set[UUID], event: dict) -> None:
        """Deliver an event only to these people's open tabs (e.g. a mention)."""
        data = json.dumps(event, default=str)
        for ws, info in list(self._clients.items()):
            if info["user"] in user_ids:
                try:
                    await ws.send_text(data)
                except Exception:
                    pass
        await self.broadcast_presence()

    async def view(self, ws: WebSocket, channel_id: str) -> None:
        if ws in self._clients:
            self._clients[ws]["channel"] = channel_id
            await self.broadcast_presence()

    async def leave(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.pop(ws, None)
        await self.broadcast_presence()

    async def broadcast_presence(self) -> None:
        await self.broadcast({"type": "presence", **self.presence()})

    async def broadcast(
        self, event: dict, *, exclude: WebSocket | None = None, channel: str | None = None
    ) -> None:
        """Send to everyone, or only to sockets viewing `channel`."""
        data = json.dumps(event, default=str)
        dead = []
        for ws, info in list(self._clients.items()):
            if ws is exclude or (channel is not None and info["channel"] != channel):
                continue
            try:
                await ws.send_text(data)
            except Exception:  # closed mid-send; drop it
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.pop(ws, None)


hub = Hub()
