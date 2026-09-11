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
    created_at: datetime


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