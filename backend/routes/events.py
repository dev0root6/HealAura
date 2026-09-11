from fastapi import APIRouter

import db
from models import EntryOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EntryOut])
async def get_events() -> list[EntryOut]:
    """Return upcoming dated events, soonest first, as reminder cards."""
    return await db.fetch_upcoming_events()
