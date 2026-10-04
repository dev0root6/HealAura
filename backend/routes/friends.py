from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

import auth
import db
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
