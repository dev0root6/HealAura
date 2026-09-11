import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

SARVAM_BASE_URL = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
DEFAULT_MODEL = "sarvam-105b"

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """Return a shared AsyncClient (created lazily)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=SARVAM_BASE_URL,
            timeout=httpx.Timeout(60.0),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> str:
    """Call Sarvam's /v1/chat/completions and return the assistant message content."""
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set in .env")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        # sarvam-105b is a reasoning model; reasoning tokens count toward
        # max_tokens and the default (medium) effort easily exhausts the budget
        # before any `content` is produced (finish_reason="length", content=null).
        # For structured JSON extraction we don't need chain-of-thought, so
        # disable it for fast, complete responses.
        "reasoning_effort": None,
    }
    headers = {"Authorization": f"Bearer {SARVAM_API_KEY}"}

    try:
        resp = await get_client().post("/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Sarvam API error {exc.response.status_code}: {exc.response.text[:500]}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Sarvam API request failed: {exc}") from exc

    data = resp.json()
    try:
        content = data["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected Sarvam response shape: {data}") from exc
    return content or ""