"""Accounts: sign-up with email verification, sign-in, sign-out.

Sign-up is three steps so that every account has an email that its owner
actually controls (well-being check-ins go to it):
  1. POST /auth/register/start     {email}            -> a 6-digit code is emailed
  2. POST /auth/register/verify    {email, code}      -> a short-lived signup token
  3. POST /auth/register/complete  {token, username, password} -> account + session
"""

import hashlib
import logging
import secrets
from datetime import datetime, timezone

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException

import auth
import db
import email_client
import emails
from models import (
    LANGUAGES,
    EmailStartRequest,
    ProfileIn,
    LoginRequest,
    LoginResponse,
    RegisterCompleteRequest,
    RegisterStartRequest,
    RegisterStartResponse,
    RegisterVerifyRequest,
    RegisterVerifyResponse,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

CODE_TTL_MINUTES = 10
RESEND_AFTER_SECONDS = 60
MAX_CODE_ATTEMPTS = 5
SIGNUP_TOKEN_TTL_MINUTES = 30


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _code_hash(email: str, code: str) -> str:
    return _hash(f"{email}:{code}")


async def _start_session(record: dict) -> LoginResponse:
    token = auth.new_token()
    await db.create_session(token, record["id"])
    return LoginResponse(token=token, user=UserOut.model_validate(record))


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    """Sign in with a username or the registered email, plus password."""
    record = await db.fetch_user_auth(payload.username.strip())
    if not record or not auth.verify_password(payload.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username/email or password")
    return await _start_session(record)


@router.post("/logout")
async def logout(authorization: str = Header(default="")) -> dict:
    if authorization.lower().startswith("bearer "):
        await db.delete_session(authorization.split(" ", 1)[1].strip())
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
async def me(user: UserOut = Depends(auth.get_current_user)) -> UserOut:
    return user


# --- sign-up ---

@router.post("/register/start", response_model=RegisterStartResponse)
async def register_start(payload: RegisterStartRequest) -> RegisterStartResponse:
    """Email a 6-digit code to the address being registered."""
    email = payload.email
    if await db.email_registered(email):
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")

    return await _send_code(email)


@router.post("/register/verify", response_model=RegisterVerifyResponse)
async def register_verify(payload: RegisterVerifyRequest) -> RegisterVerifyResponse:
    """Check the emailed code; on a match, hand back a token to finish sign-up."""
    email = payload.email
    await _check_code(email, payload.code)

    token = secrets.token_urlsafe(32)
    await db.mark_verified(email, _hash(token), SIGNUP_TOKEN_TTL_MINUTES)
    return RegisterVerifyResponse(signup_token=token)


@router.post("/register/complete", response_model=LoginResponse)
async def register_complete(payload: RegisterCompleteRequest) -> LoginResponse:
    """Create the account for a verified email and sign the user in."""
    record = await db.fetch_verification_by_token(_hash(payload.signup_token))
    if not record:
        raise HTTPException(status_code=400, detail="Your verification has expired. Please start again.")

    username = payload.username.strip()
    if await db.username_taken(username):
        raise HTTPException(status_code=409, detail="That username is taken. Try another.")
    try:
        user = await db.create_user(username, auth.hash_password(payload.password), record["email"])
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail="That username or email is already registered.") from exc
    await db.delete_verification(record["email"])

    token = auth.new_token()
    await db.create_session(token, user.id)
    logger.info("New account registered: %s", username)
    return LoginResponse(token=token, user=user)


# --- profile (also how existing accounts finish setting up) ---

@router.get("/languages")
async def languages() -> list[dict]:
    return [{"code": code, "label": label} for code, label in LANGUAGES.items()]


@router.put("/profile", response_model=UserOut)
async def update_profile(payload: ProfileIn, user: UserOut = Depends(auth.get_current_user)) -> UserOut:
    """Save what to call the person, the language they speak, and their interests."""
    name = (payload.preferred_name or "").strip() or None
    await db.update_profile(user.id, name, payload.language, payload.interests)
    record = await db.fetch_user_auth(user.username)
    return UserOut.model_validate(record)


async def _send_code(email: str) -> RegisterStartResponse:
    """Shared by sign-up and add-email: rate-limit, store and send a 6-digit code."""
    existing = await db.fetch_verification(email)
    if existing:
        wait = RESEND_AFTER_SECONDS - (datetime.now(timezone.utc) - existing["sent_at"]).total_seconds()
        if wait > 0:
            raise HTTPException(status_code=429, detail=f"Please wait {int(wait) + 1}s before asking for a new code.")
    code = f"{secrets.randbelow(1_000_000):06d}"
    await db.upsert_verification(email, _code_hash(email, code), CODE_TTL_MINUTES)
    if not email_client.configured():
        logger.warning("SMTP not configured. Verification code for %s: %s", email, code)
        return RegisterStartResponse(delivery="log", expires_in_minutes=CODE_TTL_MINUTES)
    subject, text, html = emails.verification_code(code, CODE_TTL_MINUTES)
    try:
        await email_client.send_email(email, subject, text, html)
    except RuntimeError as exc:
        await db.delete_verification(email)
        raise HTTPException(status_code=502, detail="We couldn't send the email. Check the address and try again.") from exc
    return RegisterStartResponse(delivery="email", expires_in_minutes=CODE_TTL_MINUTES)


async def _check_code(email: str, code: str) -> None:
    record = await db.fetch_verification(email)
    if not record or record["expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="That code has expired. Ask for a new one.")
    if record["attempts"] >= MAX_CODE_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many tries. Ask for a new code.")
    if not secrets.compare_digest(record["code_hash"], _code_hash(email, code.strip())):
        await db.record_failed_attempt(email)
        left = MAX_CODE_ATTEMPTS - record["attempts"] - 1
        raise HTTPException(status_code=400, detail=f"That code doesn't match. {left} tries left.")


@router.post("/email/start", response_model=RegisterStartResponse)
async def add_email_start(
    payload: EmailStartRequest, user: UserOut = Depends(auth.get_current_user)
) -> RegisterStartResponse:
    """Existing accounts without an email: send a code to the address they want to add."""
    if await db.email_registered(payload.email):
        raise HTTPException(status_code=409, detail="That email is already used by another account.")
    return await _send_code(payload.email)


@router.post("/email/verify", response_model=UserOut)
async def add_email_verify(
    payload: RegisterVerifyRequest, user: UserOut = Depends(auth.get_current_user)
) -> UserOut:
    await _check_code(payload.email, payload.code)
    try:
        await db.set_email(user.id, payload.email)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail="That email is already used by another account.") from exc
    await db.delete_verification(payload.email)
    return UserOut.model_validate(await db.fetch_user_auth(user.username))
