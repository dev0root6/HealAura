import asyncio
import logging

from datetime import date
from typing import Optional

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

import backchannel
import classify
import db
from models import (
    EntryCorrection,
    EntryRequest,
    EntryResponse,
    EntryOut,
    MessageOut,
    SuggestRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entries", tags=["entries"])


@router.post("", response_model=EntryResponse)
async def create_entries(payload: EntryRequest) -> EntryResponse:
    """Store one entry and answer it with a short acknowledgement.

    Classification and the backchannel reply are independent, so they run
    concurrently — the user waits for one round trip, not two.
    """
    raw_text = payload.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text cannot be empty")

    classified, answered = await asyncio.gather(
        classify.classify_entry(raw_text),
        backchannel.respond(raw_text),
        return_exceptions=True,
    )
    if isinstance(classified, BaseException):
        logger.warning("Sarvam classification failed for entry: %s", classified)
        raise HTTPException(status_code=502, detail=str(classified)) from classified
    if isinstance(answered, BaseException):
        # respond() handles its own failures; this is belt-and-braces so a
        # surprise never costs the user their entry.
        logger.warning("Backchannel raised unexpectedly: %s", answered)
        answered = ("hmm", False)
    reply_text, needs_support = answered

    segments, used_fallback = classified
    user_msg = await db.insert_message("user", raw_text)
    stored = await db.insert_segments(
        raw_text, segments, is_fallback=used_fallback, message_id=user_msg.id
    )
    if used_fallback:
        logger.warning("Stored fallback (unclassified) segments for: %r", raw_text)

    reply = await db.insert_message(
        "assistant", reply_text, needs_support=needs_support
    )
    return EntryResponse(entries=stored, reply=reply)


@router.get("", response_model=list[EntryOut])
async def get_entries(day: Optional[date] = Query(default=None, alias="date")) -> list[EntryOut]:
    """Return entries created on the given date (default: today)."""
    target = day or date.today()
    return await db.fetch_entries_by_date(target)

@router.patch("/{entry_id}", response_model=EntryOut)
async def correct_entry(entry_id: UUID, payload: EntryCorrection) -> EntryOut:
    """Confirm an entry's classification, optionally correcting type/sentiment."""
    updated = await db.update_entry(
        entry_id,
        corrected_type=payload.corrected_type,
        corrected_sentiment=payload.corrected_sentiment,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return updated


@router.get("/messages", response_model=list[MessageOut])
async def get_messages(day: Optional[date] = Query(default=None, alias="date")) -> list[MessageOut]:
    """Return the conversation thread for the given date (default: today)."""
    return await db.fetch_messages_by_date(day or date.today())


@router.post("/suggest", response_model=MessageOut)
async def ask_for_suggestion(payload: SuggestRequest) -> MessageOut:
    """Answer an explicit request for advice. Only ever called on user action."""
    raw_text = payload.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text cannot be empty")
    try:
        advice = await backchannel.suggest(raw_text)
    except RuntimeError as exc:
        logger.warning("Sarvam suggestion failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not advice:
        raise HTTPException(status_code=502, detail="Empty suggestion from Sarvam")
    return await db.insert_message("assistant", advice, kind="suggestion")
