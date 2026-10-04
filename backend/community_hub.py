"""Real-time fan-out for the community channel.

Every open Community tab holds one WebSocket here. New messages (from people
and from companions), who-is-typing hints and the online count are pushed to
all of them, so the channel works as a live chat room.

State is in-process: run the API as a single worker (the default for
`uvicorn main:app`). Several workers would each have their own room.
"""

import asyncio
import hashlib
import json
import os
from datetime import date
from uuid import UUID

from fastapi import WebSocket


_ADJECTIVES = [
    "Calm", "Quiet", "Gentle", "Warm", "Kind", "Brave", "Still", "Bright",
    "Soft", "Hopeful", "Steady", "Open",
]
_ANIMALS = [
    "Sparrow", "Otter", "Fox", "Heron", "Deer", "Koala", "Finch", "Panda",
    "Lark", "Seal", "Wren", "Owl",
]
_SALT = os.getenv("COMMUNITY_HANDLE_SALT", "healaura-community")


def handle_for(user_id: UUID, day: date | None = None) -> str:
    """A person's anonymous handle for the day.

    Stable within a day so a conversation is easy to follow, different the next
    day so it never becomes a long-lived identity. Not reversible to the user.
    """
    day = day or date.today()
    digest = hashlib.sha256(f"{_SALT}:{user_id}:{day.isoformat()}".encode()).digest()
    return f"{_ADJECTIVES[digest[0] % len(_ADJECTIVES)]}{_ANIMALS[digest[1] % len(_ANIMALS)]}"


class Hub:
    """Open sockets, each with its person's handle and the channel they're viewing."""

    def __init__(self) -> None:
        self._clients: dict[WebSocket, dict] = {}  # socket -> {"handle", "channel"}
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

    async def join(self, ws: WebSocket, handle: str) -> None:
        async with self._lock:
            self._clients[ws] = {"handle": handle, "channel": None}
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
