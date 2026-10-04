import asyncio
import logging

from datetime import date
from typing import Literal, Optional

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

import agent
import auth
import backchannel
import classify
import db
import safety
import sarvam_client
import trends
import voice
from models import (
    AudioEntryResponse,
    EntryCorrection,
    EntryRequest,
    EntryResponse,
    EntryOut,
    MessageOut,
    SpeechRequest,
    SuggestRequest,
    TrendsOut,
    UserOut,
)

# Roughly 10 minutes of Opus at speech bitrates; the endpoint is for a couple
# of minutes of talking, not for uploading media.
MAX_AUDIO_BYTES = 15 * 1024 * 1024

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entries", tags=["entries"])


@router.post("", response_model=EntryResponse)
async def create_entries(
    payload: EntryRequest, user: UserOut = Depends(auth.get_current_user)
) -> EntryResponse:
    """Store one entry and answer it: a short acknowledgement, or a real reply in "long" mode.

    Classification and the reply are independent, so they run concurrently —
    the user waits for one round trip, not two.
    """
    return await _record_entry(user, payload.raw_text, mode=payload.mode)


async def _reply(user: UserOut, raw_text: str, mode: str) -> tuple[str, bool, bool]:
    if mode == "long":
        # Earlier turns are read before this entry is stored, so they exclude it.
        history = await db.recent_conversation(user.id)
        return await backchannel.converse(raw_text, history, user.language, user.preferred_name)
    return await backchannel.respond(raw_text, user.language)


async def _record_entry(
    user: UserOut, text: str, *, language_code: Optional[str] = None, mode: str = "short"
) -> EntryResponse:
    """Shared path for typed and spoken entries."""
    raw_text = text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text cannot be empty")

    classified, answered = await asyncio.gather(
        classify.classify_with_confidence(raw_text),
        _reply(user, raw_text, mode),
        return_exceptions=True,
    )
    if isinstance(classified, BaseException):
        logger.warning("Sarvam classification failed for entry: %s", classified)
        raise HTTPException(status_code=502, detail=str(classified)) from classified
    if isinstance(answered, BaseException):
        # respond() handles its own failures; this is belt-and-braces so a
        # surprise never costs the user their entry.
        logger.warning("Backchannel raised unexpectedly: %s", answered)
        answered = ("hmm", False, False)
    reply_text, needs_support, model_crisis = answered
    # The phrase safety net also covers the back-channel's fallback paths,
    # which report no flags at all.
    crisis = safety.is_crisis(raw_text, model_crisis)
    needs_support = needs_support or crisis

    segments, used_fallback = classified
    user_msg = await db.insert_message(user.id, "user", raw_text, language_code=language_code)
    stored = await db.insert_segments(
        user.id, raw_text, segments, is_fallback=used_fallback, message_id=user_msg.id
    )
    if used_fallback:
        logger.warning("Stored fallback (unclassified) segments for: %r", raw_text)

    reply = await db.insert_message(
        user.id,
        "assistant",
        reply_text,
        needs_support=needs_support,
        crisis=crisis,
        language_code=language_code,
    )
    # The well-being agent decides, from recent context, whether to quietly
    # reach out to the user's close friends. It never raises.
    await agent.evaluate_and_alert(user, needs_support=needs_support, crisis=crisis)
    return EntryResponse(entries=stored, reply=reply)


@router.get("", response_model=list[EntryOut])
async def get_entries(
    day: Optional[date] = Query(default=None, alias="date"),
    user: UserOut = Depends(auth.get_current_user),
) -> list[EntryOut]:
    """Return entries created on the given date (default: today)."""
    target = day or date.today()
    return await db.fetch_entries_by_date(user.id, target)

@router.patch("/{entry_id}", response_model=EntryOut)
async def correct_entry(
    entry_id: UUID, payload: EntryCorrection, user: UserOut = Depends(auth.get_current_user)
) -> EntryOut:
    """Confirm an entry's classification, optionally correcting type/sentiment."""
    updated = await db.update_entry(
        user.id,
        entry_id,
        corrected_type=payload.corrected_type,
        corrected_sentiment=payload.corrected_sentiment,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return updated


@router.get("/trends", response_model=TrendsOut)
async def get_trends(
    days: int = Query(default=30, ge=7, le=180),
    user: UserOut = Depends(auth.get_current_user),
) -> TrendsOut:
    """Daily sentiment counts and a smoothed negativity score for the last `days` days."""
    return await trends.build(user.id, days)


@router.get("/messages", response_model=list[MessageOut])
async def get_messages(
    day: Optional[date] = Query(default=None, alias="date"),
    user: UserOut = Depends(auth.get_current_user),
) -> list[MessageOut]:
    """Return the conversation thread for the given date (default: today)."""
    return await db.fetch_messages_by_date(user.id, day or date.today())


@router.post("/suggest", response_model=MessageOut)
async def ask_for_suggestion(
    payload: SuggestRequest, user: UserOut = Depends(auth.get_current_user)
) -> MessageOut:
    """Answer an explicit request for advice. Only ever called on user action."""
    raw_text = payload.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text cannot be empty")
    try:
        advice = await backchannel.suggest(raw_text, user.language)
    except RuntimeError as exc:
        logger.warning("Sarvam suggestion failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not advice:
        raise HTTPException(status_code=502, detail="Empty suggestion from Sarvam")
    return await db.insert_message(user.id, "assistant", advice, kind="suggestion")


@router.post("/audio", response_model=AudioEntryResponse)
async def create_entry_from_audio(
    file: UploadFile = File(...),
    mode: Literal["short", "long"] = Form("short"),
    user: UserOut = Depends(auth.get_current_user),
) -> AudioEntryResponse:
    """Transcribe a spoken entry and run it through the normal entry path.

    Transcription is awaited rather than backgrounded: the reply is the whole
    point of the interaction, and polling for it would break the conversation.
    """
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio too large (limit 15 MB)")

    try:
        transcript, detected_language = await sarvam_client.transcribe(
            audio,
            filename=file.filename or "entry.webm",
            content_type=file.content_type or "audio/webm",
        )
    except RuntimeError as exc:
        logger.warning("Transcription failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not transcript:
        raise HTTPException(
            status_code=422, detail="Could not make out any speech in that recording"
        )

    recorded = await _record_entry(user, transcript, language_code=detected_language, mode=mode)
    return AudioEntryResponse(
        entries=recorded.entries, reply=recorded.reply, transcript=transcript
    )


@router.get("/voices")
async def list_voices(_user: UserOut = Depends(auth.get_current_user)) -> list[dict]:
    """Voices the user can pick for spoken replies, and which work right now."""
    return await voice.catalogue()


@router.post("/speech")
async def speak(
    payload: SpeechRequest, _user: UserOut = Depends(auth.get_current_user)
) -> Response:
    """Render text as speech. Returns raw audio for the browser to play."""
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text cannot be empty")
    try:
        audio = await voice.speak(
            text, language_code=payload.language_code, voice=payload.voice, tone=payload.tone
        )
    except RuntimeError as exc:
        logger.warning("Speech synthesis failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/wav")
