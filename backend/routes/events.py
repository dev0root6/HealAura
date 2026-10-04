from fastapi import APIRouter, Depends

import auth
import db
from models import EntryOut, UserOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EntryOut])
async def get_events(user: UserOut = Depends(auth.get_current_user)) -> list[EntryOut]:
    """Return the user's upcoming dated events, soonest first, as reminder cards."""
    return await db.fetch_upcoming_events(user.id)
