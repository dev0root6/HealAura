import base64
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

SARVAM_BASE_URL = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
DEFAULT_MODEL = "sarvam-105b"

# Speech lives outside the OpenAI-compatible /v1 surface and authenticates with
# a different header, so it gets its own base URL rather than reusing the chat
# client's.
SARVAM_SPEECH_BASE_URL = os.getenv("SARVAM_SPEECH_BASE_URL", "https://api.sarvam.ai")
STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
# "codemix" keeps Tanglish/Hinglish as the user actually said it, which is the
# form classify.py's prompt and few-shot examples are written against.
STT_MODE = os.getenv("SARVAM_STT_MODE", "codemix")
TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "ishita")
TTS_LANGUAGES = {
    "bn-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN", "ml-IN",
    "mr-IN", "od-IN", "pa-IN", "ta-IN", "te-IN",
}
DEFAULT_TTS_LANGUAGE = os.getenv("SARVAM_TTS_LANGUAGE", "en-IN")
_TTS_MAX_CHARS = 2500

_client: Optional[httpx.AsyncClient] = None
_speech_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """Return a shared AsyncClient (created lazily)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=SARVAM_BASE_URL,
            timeout=httpx.Timeout(60.0),
        )
    return _client


def get_speech_client() -> httpx.AsyncClient:
    """Return a shared AsyncClient for the speech endpoints (created lazily)."""
    global _speech_client
    if _speech_client is None:
        _speech_client = httpx.AsyncClient(
            base_url=SARVAM_SPEECH_BASE_URL,
            timeout=httpx.Timeout(120.0),
        )
    return _speech_client


async def close_client() -> None:
    global _client, _speech_client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _speech_client is not None:
        await _speech_client.aclose()
        _speech_client = None


def _speech_headers() -> dict[str, str]:
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY is not set in .env")
    return {"api-subscription-key": SARVAM_API_KEY}


def _raise_for_speech_error(exc: httpx.HTTPError, what: str) -> RuntimeError:
    if isinstance(exc, httpx.HTTPStatusError):
        return RuntimeError(
            f"Sarvam {what} error {exc.response.status_code}: {exc.response.text[:500]}"
        )
    return RuntimeError(f"Sarvam {what} request failed: {exc}")


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

async def transcribe(
    audio: bytes,
    *,
    filename: str = "entry.webm",
    content_type: str = "audio/webm",
    language_code: str = "unknown",
) -> tuple[str, Optional[str]]:
    """Transcribe recorded audio. Returns (transcript, detected_language_code)."""
    # Sarvam matches the full Content-Type against an allow-list, so a browser
    # value like "audio/webm;codecs=opus" is rejected even though "audio/webm"
    # is allowed. Drop any parameters and keep just the media type.
    content_type = content_type.split(";", 1)[0].strip() or "audio/webm"
    data = {"model": STT_MODEL, "language_code": language_code}
    if STT_MODEL.startswith("saaras:v3"):
        # `mode` is only accepted by v3; v4 rejects it.
        data["mode"] = STT_MODE

    try:
        resp = await get_speech_client().post(
            "/speech-to-text",
            files={"file": (filename, audio, content_type)},
            data=data,
            headers=_speech_headers(),
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise _raise_for_speech_error(exc, "speech-to-text") from exc

    payload = resp.json()
    transcript = payload.get("transcript")
    if not isinstance(transcript, str):
        raise RuntimeError(f"Unexpected speech-to-text response shape: {payload}")
    detected = payload.get("language_code")
    return transcript.strip(), detected if isinstance(detected, str) else None


async def synthesize(
    text: str,
    *,
    language_code: Optional[str] = None,
    speaker: Optional[str] = None,
    pace: Optional[float] = None,
) -> bytes:
    """Render text as speech, returning raw audio bytes (WAV)."""
    language = language_code if language_code in TTS_LANGUAGES else DEFAULT_TTS_LANGUAGE
    payload = {
        "text": text[:_TTS_MAX_CHARS],
        "language_code": language,
        "model": TTS_MODEL,
        "speaker": speaker or TTS_SPEAKER,
    }
    if pace is not None:
        payload["pace"] = pace

    try:
        resp = await get_speech_client().post(
            "/text-to-speech", json=payload, headers=_speech_headers()
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise _raise_for_speech_error(exc, "text-to-speech") from exc

    data = resp.json()
    audios = data.get("audios")
    if not isinstance(audios, list) or not audios:
        raise RuntimeError(f"Unexpected text-to-speech response shape: {data}")
    return base64.b64decode(audios[0])
