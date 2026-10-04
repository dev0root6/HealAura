"""Minimal token auth for the prototype.

Passwords are salted PBKDF2 (stdlib, no extra deps). A login mints a random
bearer token stored in the `sessions` table; requests carry it as
`Authorization: Bearer <token>`. Good enough for a demo, not a hardened system.
"""

import hashlib
import secrets
from typing import Optional

from fastapi import Header, HTTPException

import db
from models import UserOut

_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return secrets.compare_digest(dk.hex(), expected)


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> UserOut:
    """FastAPI dependency: resolve the bearer token to a user, or 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    user = await db.fetch_user_by_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user

