import logging

from datetime import date
from typing import Optional

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

import classify
import db
from models import EntryCorrection, EntryRequest, EntryOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entries", tags=["entries"])


@router.post("", response_model=list[EntryOut])
async def create_entries(payload: EntryRequest) -> list[EntryOut]:
    raw_text = payload.raw_text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text cannot be empty")

    try:
        segments, used_fallback = await classify.classify_entry(raw_text)
    except RuntimeError as exc:
        logger.warning("Sarvam classification failed for entry: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    stored = await db.insert_segments(raw_text, segments, is_fallback=used_fallback)
    if used_fallback:
        logger.warning("Stored fallback (unclassified) segments for: %r", raw_text)
    return stored


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
