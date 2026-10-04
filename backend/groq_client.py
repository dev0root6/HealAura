"""Groq API client: chat completions (community companions) and Orpheus TTS.

Groq exposes an OpenAI-compatible surface. The key is read from GROQ_API_KEY,
or GROQ_API for the name already used in this project's .env.
"""

import logging
import os
import time
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API") or ""
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")
# Orpheus takes at most 200 characters per request.
TTS_MAX_CHARS = 200

_client: Optional[httpx.AsyncClient] = None
# When Orpheus refuses (e.g. its terms are not yet accepted on the Groq
# account), stop trying for a while instead of paying a failed round trip on
# every spoken reply.
_tts_disabled_until = 0.0
_TTS_BACKOFF_SECONDS = 600


def available() -> bool:
    return bool(GROQ_API_KEY)


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=GROQ_BASE_URL,
            timeout=httpx.Timeout(60.0),
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def chat(
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.9,
    max_tokens: int = 400,
) -> str:
    """One chat completion; returns the message content or raises RuntimeError."""
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in .env")
    payload = {
        "model": GROQ_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        # gpt-oss reasons before answering; keep that short for chat replies.
        "reasoning_effort": "low",
    }
    try:
        resp = await _get_client().post("/chat/completions", json=payload)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Groq API error {exc.response.status_code}: {exc.response.text[:300]}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Groq request failed: {exc}") from exc
    try:
        return (resp.json()["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("Unexpected Groq response shape") from exc


def tts_available() -> bool:
    return bool(GROQ_API_KEY) and time.monotonic() >= _tts_disabled_until


async def synthesize(text: str, *, voice: str, direction: Optional[str] = None) -> bytes:
    """Expressive English speech via Orpheus. Returns WAV bytes or raises RuntimeError."""
    global _tts_disabled_until
    spoken = f"[{direction}] {text}" if direction else text
    payload = {
        "model": GROQ_TTS_MODEL,
        "voice": voice,
        "input": spoken[:TTS_MAX_CHARS],
        "response_format": "wav",
    }
    try:
        resp = await _get_client().post("/audio/speech", json=payload)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (400, 401, 403):
            _tts_disabled_until = time.monotonic() + _TTS_BACKOFF_SECONDS
            logger.warning(
                "Orpheus TTS unavailable (%s); using Sarvam for %d min. %s",
                exc.response.status_code,
                _TTS_BACKOFF_SECONDS // 60,
                exc.response.text[:200],
            )
        raise RuntimeError(f"Groq TTS error {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Groq TTS request failed: {exc}") from exc
    return resp.content
