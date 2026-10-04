from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

import agent
import auth
import db
import email_client
from models import FriendIn, FriendOut, UserOut

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("", response_model=list[FriendOut])
async def list_friends(user: UserOut = Depends(auth.get_current_user)) -> list[FriendOut]:
    """The user's close-friends list — who the well-being agent may reach out to."""
    return await db.list_friends(user.id)


@router.post("", response_model=FriendOut)
async def add_friend(
    payload: FriendIn, user: UserOut = Depends(auth.get_current_user)
) -> FriendOut:
    return await db.add_friend(user.id, payload.name.strip(), payload.email)


@router.delete("/{friend_id}")
async def remove_friend(
    friend_id: UUID, user: UserOut = Depends(auth.get_current_user)
) -> dict:
    if not await db.delete_friend(user.id, friend_id):
        raise HTTPException(status_code=404, detail="Friend not found")
    return {"status": "deleted"}


@router.get("/alerts")
async def alert_history(user: UserOut = Depends(auth.get_current_user)) -> dict:
    """Recent check-ins HealAura sent for this user, and when the next one can go out."""
    last = await db.last_alert_at(user.id)
    return {
        "email_configured": email_client.configured(),
        "cooldown_hours": agent.COOLDOWN_HOURS,
        "next_allowed_at": (last + timedelta(hours=agent.COOLDOWN_HOURS)) if last else None,
        "alerts": await db.list_alerts(user.id),
    }


@router.post("/test-alert")
async def test_alert(user: UserOut = Depends(auth.get_current_user)) -> dict:
    """Send a clearly labelled test email to the user's close friends."""
    if not email_client.configured():
        raise HTTPException(status_code=503, detail="Email isn't set up on the server yet.")
    if not await db.list_friends(user.id):
        raise HTTPException(status_code=400, detail="Add a close friend first.")
    if not await agent.send_alert(user, reason="test"):
        raise HTTPException(status_code=502, detail="The test email couldn't be sent. Check the friend's address.")
    return {"status": "sent"}
