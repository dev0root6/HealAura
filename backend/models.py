from datetime import date, datetime, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_TYPES = {"memory", "event", "task"}
VALID_SENTIMENTS = {"positive", "negative", "neutral", "mixed"}


def _check_member(value: Optional[str], allowed: set[str], label: str) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise ValueError(f"invalid {label}: {value!r} (expected one of {sorted(allowed)})")
    return normalized


class Segment(BaseModel):
    """A single classified segment returned by Sarvam."""

    segment_text: str
    type: str
    sentiment: str
    event_date: Optional[date] = None
    event_time: Optional[time] = None
    person: Optional[str] = None
    ai_confidence: Optional[float] = None


class EntryRequest(BaseModel):
    raw_text: str = Field(min_length=1)


class EntryOut(BaseModel):
    """Stored entries row, as returned to the frontend."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    raw_text: str
    segment_text: str
    entry_type: str
    sentiment: str
    event_date: Optional[date] = None
    event_time: Optional[time] = None
    person: Optional[str] = None
    ai_confidence: Optional[float] = None
    user_confirmed: int = 0
    corrected_type: Optional[str] = None
    corrected_sentiment: Optional[str] = None
    alert_sent: bool = False
    is_fallback: bool = False
    message_id: Optional[UUID] = None
    created_at: datetime


class MessageOut(BaseModel):
    """One turn of the journaling conversation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    kind: str
    needs_support: bool
    crisis: bool = False
    language_code: Optional[str] = None
    created_at: datetime


class EntryResponse(BaseModel):
    """What POST /entries returns: the structured segments plus the reply."""

    entries: list["EntryOut"]
    reply: MessageOut


class SuggestRequest(BaseModel):
    raw_text: str = Field(min_length=1)


class AudioEntryResponse(EntryResponse):
    """An entry created from speech, with the transcript that produced it."""

    transcript: str


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1)
    language_code: Optional[str] = None
    # A voice id from voice.VOICES; unknown ids fall back to the default.
    voice: Optional[str] = None
    # "warm" for ordinary replies, "gentle" for heavy moments.
    tone: Optional[str] = None


def _valid_email(v: str) -> str:
    v = v.strip()
    if "@" not in v or "." not in v.split("@")[-1]:
        raise ValueError("that does not look like an email address")
    return v


class LoginRequest(BaseModel):
    # A username, or the email the account was registered with.
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class RegisterStartRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _valid_email(v).lower()


class RegisterStartResponse(BaseModel):
    # "email" when the code was mailed; "log" when SMTP is not configured yet
    # and the code went to the server log instead (development only).
    delivery: str
    expires_in_minutes: int


class RegisterVerifyRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=12)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class RegisterVerifyResponse(BaseModel):
    signup_token: str


class RegisterCompleteRequest(BaseModel):
    signup_token: str = Field(min_length=10, max_length=200)
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    email: Optional[str] = None
    is_admin: bool = False
    created_at: datetime


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class FriendIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _valid_email(v)


class FriendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str
    created_at: datetime


class Counsellor(BaseModel):
    """A (demo) counsellor a user can reach out to."""

    name: str
    title: str
    languages: list[str]
    phone: str
    email: str
    available: str


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    description: str
    is_default: bool
    created_at: datetime
    last_message_at: Optional[datetime] = None
    message_count: int = 0


class ChannelIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    description: str = Field(default="", max_length=140)


class CommunityMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=1000)


class CommunityMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    handle: str
    content: str
    channel_id: Optional[UUID] = None
    is_bot: bool = False
    reply_to: Optional[UUID] = None
    created_at: datetime


class DayTrend(BaseModel):
    """Segment sentiment counts for one day of the trends view."""

    day: date
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    mixed: int = 0
    total: int = 0
    # Share of the day's segments that were negative; None on days with no entries.
    negative_share: Optional[float] = None
    # Exponentially weighted negative share, carried over days with no entries.
    smoothed_negative: Optional[float] = None


class TrendsOut(BaseModel):
    days: list[DayTrend]
    totals: dict[str, int]


class EntryCorrection(BaseModel):
    """User confirmation / correction of one classified entry.

    Both fields optional: an empty body confirms the AI classification as-is.
    """

    corrected_type: Optional[str] = None
    corrected_sentiment: Optional[str] = None

    @field_validator("corrected_type")
    @classmethod
    def _check_type(cls, v: Optional[str]) -> Optional[str]:
        return _check_member(v, VALID_TYPES, "type")

    @field_validator("corrected_sentiment")
    @classmethod
    def _check_sentiment(cls, v: Optional[str]) -> Optional[str]:
        return _check_member(v, VALID_SENTIMENTS, "sentiment")