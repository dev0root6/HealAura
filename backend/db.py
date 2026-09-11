import logging
import os
from datetime import date, time
from typing import Optional
from uuid import UUID

import asyncpg
from dotenv import load_dotenv

from models import EntryOut, MessageOut, Segment

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("NEON_DATABASE_URL")
_pool: Optional[asyncpg.Pool] = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_text TEXT NOT NULL,
    segment_text TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    event_date DATE,
    event_time TIME,
    person TEXT,
    ai_confidence REAL,
    user_confirmed SMALLINT DEFAULT 0,
    corrected_type TEXT,
    corrected_sentiment TEXT,
    alert_sent BOOLEAN DEFAULT FALSE,
    is_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'entry',
    needs_support BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_created_at_idx ON messages (created_at);

-- Added after the first tables were created, so apply them separately too.
ALTER TABLE entries ADD COLUMN IF NOT EXISTS is_fallback BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE entries ADD COLUMN IF NOT EXISTS message_id UUID REFERENCES messages (id) ON DELETE SET NULL;
"""


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it if necessary."""
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("NEON_DATABASE_URL is not set in .env")
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return _pool


async def init_db() -> None:
    """Create the connection pool and ensure the entries table exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("Database ready (entries table ensured)")


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def check_health() -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.fetchval("SELECT 1")
    return True


async def insert_segments(
    raw_text: str,
    segments: list[Segment],
    *,
    is_fallback: bool = False,
    message_id: Optional[UUID] = None,
) -> list[EntryOut]:
    """Persist all classified segments for one raw entry, returning stored rows."""
    pool = await get_pool()
    rows = []
    async with pool.acquire() as conn:
        async with conn.transaction():
            for seg in segments:
                row = await conn.fetchrow(
                    """
                    INSERT INTO entries (
                        raw_text, segment_text, entry_type, sentiment,
                        event_date, event_time, person, ai_confidence,
                        is_fallback, message_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    RETURNING *
                    """,
                    raw_text,
                    seg.segment_text,
                    seg.type,
                    seg.sentiment,
                    seg.event_date,
                    seg.event_time,
                    seg.person,
                    seg.ai_confidence,
                    is_fallback,
                    message_id,
                )
                rows.append(EntryOut.model_validate(dict(row)))
    return rows


async def fetch_entries_by_date(day: date) -> list[EntryOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            SELECT * FROM entries
            WHERE created_at::date = $1::date
            ORDER BY created_at ASC
            """,
            day,
        )
    return [EntryOut.model_validate(dict(r)) for r in result]


async def fetch_upcoming_events() -> list[EntryOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            SELECT * FROM entries
            WHERE COALESCE(corrected_type, entry_type) = 'event'
              AND event_date IS NOT NULL
              AND event_date >= CURRENT_DATE
            ORDER BY event_date ASC, event_time ASC NULLS LAST
            """
        )
    return [EntryOut.model_validate(dict(r)) for r in result]

async def update_entry(
    entry_id: UUID,
    *,
    corrected_type: Optional[str] = None,
    corrected_sentiment: Optional[str] = None,
) -> Optional[EntryOut]:
    """Record a user correction/confirmation for one entry.

    Passing no correction marks the entry confirmed as-is. Returns None if the
    entry does not exist.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE entries
            SET corrected_type = COALESCE($2, corrected_type),
                corrected_sentiment = COALESCE($3, corrected_sentiment),
                user_confirmed = 1
            WHERE id = $1
            RETURNING *
            """,
            entry_id,
            corrected_type,
            corrected_sentiment,
        )
    return EntryOut.model_validate(dict(row)) if row else None


async def insert_message(
    role: str,
    content: str,
    *,
    kind: str = "entry",
    needs_support: bool = False,
) -> MessageOut:
    """Append one turn to the conversation thread."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO messages (role, content, kind, needs_support)
            VALUES ($1, $2, $3, $4)
            RETURNING *
            """,
            role,
            content,
            kind,
            needs_support,
        )
    return MessageOut.model_validate(dict(row))


async def fetch_messages_by_date(day: date) -> list[MessageOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            SELECT * FROM messages
            WHERE created_at::date = $1::date
            ORDER BY created_at ASC
            """,
            day,
        )
    return [MessageOut.model_validate(dict(r)) for r in result]
