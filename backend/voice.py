"""Voices for spoken replies, and how each reply is rendered.

Two families, chosen by the user in the app:
  - Indian voices (Sarvam Bulbul v3): speak every language the app supports,
    including Tamil, Hindi, Tanglish and Hinglish.
  - International voices (Groq Orpheus): expressive English with a vocal
    direction ("[warm]", "[softly]"). Orpheus only speaks English, so a
    non-English reply in an international voice is spoken by a Sarvam voice of
    the same gender instead.
If Orpheus is unavailable (e.g. its terms aren't accepted on the Groq account
yet) or fails, the reply falls back to Sarvam rather than going silent.
"""

import io
import logging
import re
import time
import wave
from typing import Optional

import groq_client
import sarvam_client

logger = logging.getLogger(__name__)

# id -> engine, gender, display label, family. Ids are the providers' speaker ids.
VOICES: dict[str, dict] = {
    # Indian · Sarvam Bulbul v3
    "ishita": {"engine": "sarvam", "gender": "f", "label": "Ishita", "family": "Indian"},
    "kavya": {"engine": "sarvam", "gender": "f", "label": "Kavya", "family": "Indian"},
    "priya": {"engine": "sarvam", "gender": "f", "label": "Priya", "family": "Indian"},
    "simran": {"engine": "sarvam", "gender": "f", "label": "Simran", "family": "Indian"},
    "shubh": {"engine": "sarvam", "gender": "m", "label": "Shubh", "family": "Indian"},
    "rohan": {"engine": "sarvam", "gender": "m", "label": "Rohan", "family": "Indian"},
    "kabir": {"engine": "sarvam", "gender": "m", "label": "Kabir", "family": "Indian"},
    # International · Groq Orpheus (English)
    "hannah": {"engine": "orpheus", "gender": "f", "label": "Hannah", "family": "International"},
    "diana": {"engine": "orpheus", "gender": "f", "label": "Diana", "family": "International"},
    "autumn": {"engine": "orpheus", "gender": "f", "label": "Autumn", "family": "International"},
    "daniel": {"engine": "orpheus", "gender": "m", "label": "Daniel", "family": "International"},
    "austin": {"engine": "orpheus", "gender": "m", "label": "Austin", "family": "International"},
    "troy": {"engine": "orpheus", "gender": "m", "label": "Troy", "family": "International"},
}
DEFAULT_VOICE = "ishita"
_SARVAM_FOR_GENDER = {"f": "ishita", "m": "shubh"}

# Slower than the 1.0 default reads as calmer; slower still for heavy moments.
_PACE = {"warm": 0.92, "gentle": 0.85}
_DIRECTION = {"warm": "warm", "gentle": "softly"}

# A handful of very common English words. Romanised Tamil/Hindi shares the
# Latin script, so "is it ASCII" is not enough to call a reply English.
_ENGLISH_WORDS = set(
    """i you he she it we they me my your the a an is are was were be been am do does did
    not no yes and or but so that this what how why when where okay ok hmm here there
    sounds feel feels felt really that's i'm you're it's go on keep talking sorry glad
    hard tough day good bad then happened with for to of in on at about just can could
    would will try maybe one thing small help talk someone if""".split()
)
_WORD_RE = re.compile(r"[a-zA-Z']+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def looks_english(text: str) -> bool:
    if not text.isascii():
        return False
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return False
    return sum(w in _ENGLISH_WORDS for w in words) / len(words) >= 0.5


# --- is Orpheus usable right now? (probed once, cached) ---

_PROBE_TTL = 600
_probe = {"ok": None, "at": 0.0}


async def orpheus_available() -> bool:
    if not groq_client.tts_available():
        return False
    if _probe["ok"] is not None and time.monotonic() - _probe["at"] < _PROBE_TTL:
        return _probe["ok"]
    try:
        await groq_client.synthesize("hi", voice="hannah")
        ok = True
    except RuntimeError:
        ok = False
    _probe.update(ok=ok, at=time.monotonic())
    return ok


async def catalogue() -> list[dict]:
    """Voices for the picker, with whether each can be used right now."""
    orpheus = await orpheus_available()
    return [
        {
            "id": vid,
            "label": v["label"],
            "family": v["family"],
            "gender": v["gender"],
            "available": v["engine"] == "sarvam" or orpheus,
        }
        for vid, v in VOICES.items()
    ]


# --- rendering ---

def _chunks(text: str, limit: int) -> list[str]:
    """Split on sentence ends so each piece fits Orpheus's character limit, in order."""
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_RE.split(text.strip()):
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = ""
        while len(sentence) > limit:  # a very long sentence: cut on a space
            cut = sentence.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _join_wavs(parts: list[bytes]) -> bytes:
    if len(parts) == 1:
        return parts[0]
    out = io.BytesIO()
    with wave.open(io.BytesIO(parts[0])) as first:
        params = first.getparams()
    with wave.open(out, "wb") as w:
        w.setparams(params)
        for part in parts:
            with wave.open(io.BytesIO(part)) as r:
                w.writeframes(r.readframes(r.getnframes()))
    return out.getvalue()


async def _orpheus(text: str, voice_id: str, tone: str) -> bytes:
    # Leave room for the "[direction] " prefix inside Orpheus's limit.
    limit = groq_client.TTS_MAX_CHARS - 12
    parts = [
        await groq_client.synthesize(piece, voice=voice_id, direction=_DIRECTION[tone])
        for piece in _chunks(text, limit)
    ]
    return _join_wavs(parts)


async def speak(
    text: str,
    *,
    language_code: Optional[str] = None,
    voice: Optional[str] = None,
    tone: Optional[str] = None,
) -> bytes:
    """Render one reply as WAV bytes. Raises RuntimeError only if every engine fails."""
    voice = voice if voice in VOICES else DEFAULT_VOICE
    tone = tone if tone in _PACE else "warm"
    spec = VOICES[voice]

    if spec["engine"] == "orpheus":
        english = language_code in (None, "en-IN") and looks_english(text)
        if english and groq_client.tts_available():
            try:
                return await _orpheus(text, voice, tone)
            except RuntimeError as exc:
                logger.info("Orpheus failed, falling back to Sarvam: %s", exc)
        speaker = _SARVAM_FOR_GENDER[spec["gender"]]
    else:
        speaker = voice

    return await sarvam_client.synthesize(
        text, language_code=language_code, speaker=speaker, pace=_PACE[tone]
    )
