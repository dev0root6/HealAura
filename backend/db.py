import logging
import os
from datetime import date, time
from typing import Optional
from uuid import UUID

import asyncpg
from dotenv import load_dotenv

from models import ChannelOut, CommunityMessageOut, EntryOut, FriendOut, MessageOut, Segment, UserOut

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("NEON_DATABASE_URL")
# Community messages and images live this long, then they are deleted.
COMMUNITY_TTL_HOURS = 24
_pool: Optional[asyncpg.Pool] = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS friends (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS friends_user_idx ON friends (user_id);

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
    language_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_created_at_idx ON messages (created_at);

CREATE TABLE IF NOT EXISTS community_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    handle TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS community_created_at_idx ON community_messages (created_at);

-- Added after the first tables were created, so apply them separately too.
ALTER TABLE entries ADD COLUMN IF NOT EXISTS is_fallback BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE entries ADD COLUMN IF NOT EXISTS message_id UUID REFERENCES messages (id) ON DELETE SET NULL;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS language_code TEXT;

-- Per-user ownership, added after the app went multi-user.
ALTER TABLE entries ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users (id) ON DELETE CASCADE;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users (id) ON DELETE CASCADE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_alert_at TIMESTAMPTZ;
-- Explicit self-harm / suicide disclosure on an assistant turn (see safety.py).
ALTER TABLE messages ADD COLUMN IF NOT EXISTS crisis BOOLEAN NOT NULL DEFAULT FALSE;

-- Self-registration: every new account has a verified email.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_email_idx ON users (lower(email)) WHERE email IS NOT NULL;

-- One pending sign-up per email: the emailed code, then a short-lived token
-- that lets the verified address finish creating its account.
CREATE TABLE IF NOT EXISTS email_verifications (
    email TEXT PRIMARY KEY,
    code_hash TEXT NOT NULL,
    attempts SMALLINT NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    signup_token_hash TEXT,
    signup_token_expires_at TIMESTAMPTZ
);

-- Community companions: AI-written replies, shown with an AI label.
ALTER TABLE community_messages ADD COLUMN IF NOT EXISTS is_bot BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE community_messages ADD COLUMN IF NOT EXISTS reply_to UUID REFERENCES community_messages (id) ON DELETE SET NULL;

-- When the email reminder for an event went out (once per event).
ALTER TABLE entries ADD COLUMN IF NOT EXISTS reminder_sent_at TIMESTAMPTZ;

-- "Your daily day life": a diary page written from each day's entries.
CREATE TABLE IF NOT EXISTS day_summaries (
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    day DATE NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    mood TEXT,
    highlights TEXT[] NOT NULL DEFAULT '{}',
    looking_ahead TEXT[] NOT NULL DEFAULT '{}',
    entry_count INT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, day)
);

-- Well-being alerts that went out, so the user can see when and to whom.
CREATE TABLE IF NOT EXISTS well_being_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    reason TEXT NOT NULL,            -- 'crisis' | 'sustained' | 'test'
    friends_sent INT NOT NULL DEFAULT 0,
    friends_failed INT NOT NULL DEFAULT 0,
    self_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS well_being_alerts_user_idx ON well_being_alerts (user_id, created_at);

-- Channels (Discord-style). created_by is kept only for rate limits and is
-- never returned by the API, so channels don't de-anonymise anyone.
CREATE TABLE IF NOT EXISTS community_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    position INT NOT NULL DEFAULT 100,
    created_by UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO community_channels (slug, name, description, is_default, position) VALUES
    ('general', 'general', 'Say hi, share how today went.', TRUE, 0),
    ('exam-stress', 'exam-stress', 'Exams, deadlines, results: vent and study-buddy here.', TRUE, 1),
    ('placements', 'placements', 'Interviews, rejections, offers, and everything between.', TRUE, 2),
    ('late-night', 'late-night', 'Can''t sleep? Someone else is up too.', TRUE, 3),
    ('small-wins', 'small-wins', 'Got out of bed? Submitted it? Celebrate it here.', TRUE, 4),
    ('vent', 'vent', 'Let it out. No advice unless asked.', TRUE, 5)
ON CONFLICT (slug) DO NOTHING;
ALTER TABLE community_messages ADD COLUMN IF NOT EXISTS channel_id UUID REFERENCES community_channels (id) ON DELETE CASCADE;
UPDATE community_messages SET channel_id = (SELECT id FROM community_channels WHERE slug = 'general')
 WHERE channel_id IS NULL;
CREATE INDEX IF NOT EXISTS community_channel_created_idx ON community_messages (channel_id, created_at);

-- Profile set up after sign-up (or by existing users when prompted).
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_name TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS interests TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE users ADD COLUMN IF NOT EXISTS onboarded_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS setup_reminder_sent_at TIMESTAMPTZ;

-- Community aliases: a person's chosen public name in the community (unique,
-- case-insensitive). Separate from the login username.
ALTER TABLE users ADD COLUMN IF NOT EXISTS community_alias TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_community_alias_idx
    ON users (lower(community_alias)) WHERE community_alias IS NOT NULL;

-- Images shared in the community. Re-encoded on upload (no EXIF/location),
-- and deleted with their messages after 24 hours.
CREATE TABLE IF NOT EXISTS community_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data BYTEA NOT NULL,
    mime TEXT NOT NULL,
    width INT NOT NULL,
    height INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE community_messages ADD COLUMN IF NOT EXISTS image_id UUID REFERENCES community_images (id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS entries_user_idx ON entries (user_id);
CREATE INDEX IF NOT EXISTS messages_user_idx ON messages (user_id);
"""


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool, creating it if necessary."""
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("NEON_DATABASE_URL is not set in .env")
        # statement_cache_size=0: Neon's pooled endpoint shares server connections,
        # so cached prepared statements go stale after a schema change (e.g. a new
        # column) and fail with InvalidCachedStatementError.
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=10, statement_cache_size=0
        )
    return _pool


async def init_db() -> None:
    """Create the connection pool and ensure tables. Accounts come from sign-up."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("Database ready")


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
    user_id: UUID,
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
                        user_id, raw_text, segment_text, entry_type, sentiment,
                        event_date, event_time, person, ai_confidence,
                        is_fallback, message_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING *
                    """,
                    user_id,
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


async def fetch_entries_by_date(user_id: UUID, day: date) -> list[EntryOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            SELECT * FROM entries
            WHERE user_id = $1 AND created_at::date = $2::date
            ORDER BY created_at ASC
            """,
            user_id,
            day,
        )
    return [EntryOut.model_validate(dict(r)) for r in result]


async def fetch_upcoming_events(user_id: UUID) -> list[EntryOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            SELECT * FROM entries
            WHERE user_id = $1
              AND COALESCE(corrected_type, entry_type) = 'event'
              AND event_date IS NOT NULL
              AND event_date >= CURRENT_DATE
            ORDER BY event_date ASC, event_time ASC NULLS LAST
            """,
            user_id,
        )
    return [EntryOut.model_validate(dict(r)) for r in result]

async def sentiment_counts_by_day(user_id: UUID, start: date) -> list[dict]:
    """Per-day counts of segments by effective (user-corrected if any) sentiment."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT created_at::date AS day,
                   COALESCE(corrected_sentiment, sentiment) AS sentiment,
                   COUNT(*) AS n
            FROM entries
            WHERE user_id = $1 AND created_at::date >= $2::date
            GROUP BY 1, 2
            ORDER BY 1
            """,
            user_id,
            start,
        )
    return [dict(r) for r in rows]


async def update_entry(
    user_id: UUID,
    entry_id: UUID,
    *,
    corrected_type: Optional[str] = None,
    corrected_sentiment: Optional[str] = None,
) -> Optional[EntryOut]:
    """Record a user correction/confirmation for one of the user's entries.

    Passing no correction marks the entry confirmed as-is. Returns None if the
    entry does not exist or is not owned by this user.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE entries
            SET corrected_type = COALESCE($3, corrected_type),
                corrected_sentiment = COALESCE($4, corrected_sentiment),
                user_confirmed = 1
            WHERE id = $2 AND user_id = $1
            RETURNING *
            """,
            user_id,
            entry_id,
            corrected_type,
            corrected_sentiment,
        )
    return EntryOut.model_validate(dict(row)) if row else None


async def insert_message(
    user_id: UUID,
    role: str,
    content: str,
    *,
    kind: str = "entry",
    needs_support: bool = False,
    crisis: bool = False,
    language_code: Optional[str] = None,
) -> MessageOut:
    """Append one turn to a user's conversation thread."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO messages (user_id, role, content, kind, needs_support, crisis, language_code)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            user_id,
            role,
            content,
            kind,
            needs_support,
            crisis,
            language_code,
        )
    return MessageOut.model_validate(dict(row))


async def recent_conversation(user_id: UUID, limit: int = 12) -> list[tuple[str, str]]:
    """Today's latest (role, content) turns, oldest first, for conversation mode."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at FROM messages
                WHERE user_id = $1 AND created_at::date = CURRENT_DATE AND kind = 'entry'
                ORDER BY created_at DESC LIMIT $2
            ) recent ORDER BY created_at ASC
            """,
            user_id,
            limit,
        )
    return [(r["role"], r["content"]) for r in rows]


async def fetch_messages_by_date(user_id: UUID, day: date) -> list[MessageOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            SELECT * FROM messages
            WHERE user_id = $1 AND created_at::date = $2::date
            ORDER BY created_at ASC
            """,
            user_id,
            day,
        )
    return [MessageOut.model_validate(dict(r)) for r in result]


# --- users / auth ---

async def create_user(username: str, password_hash: str, email: str) -> UserOut:
    """Insert a new account. Raises asyncpg.UniqueViolationError on a taken username/email."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (username, password_hash, email)
            VALUES ($1, $2, $3)
            RETURNING id, username, email, is_admin, created_at, preferred_name, language, interests, onboarded_at
            """,
            username,
            password_hash,
            email,
        )
    return UserOut.model_validate(dict(row))


async def fetch_user_auth(login: str) -> Optional[dict]:
    """Look a user up by username, or by email when the login contains '@'."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if "@" in login:
            row = await conn.fetchrow("SELECT * FROM users WHERE lower(email) = lower($1)", login)
        else:
            row = await conn.fetchrow("SELECT * FROM users WHERE username = $1", login)
    return dict(row) if row else None


async def username_taken(username: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval("SELECT 1 FROM users WHERE lower(username) = lower($1)", username))


async def email_registered(email: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval("SELECT 1 FROM users WHERE lower(email) = lower($1)", email))


# --- email verification (sign-up) ---

async def fetch_verification(email: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM email_verifications WHERE email = $1", email)
    return dict(row) if row else None


async def upsert_verification(email: str, code_hash: str, ttl_minutes: int) -> None:
    """Store a fresh code for this email, replacing any earlier one."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO email_verifications (email, code_hash, expires_at)
            VALUES ($1, $2, now() + make_interval(mins => $3))
            ON CONFLICT (email) DO UPDATE
               SET code_hash = EXCLUDED.code_hash, attempts = 0,
                   expires_at = EXCLUDED.expires_at, sent_at = now(),
                   signup_token_hash = NULL, signup_token_expires_at = NULL
            """,
            email,
            code_hash,
            ttl_minutes,
        )


async def record_failed_attempt(email: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE email_verifications SET attempts = attempts + 1 WHERE email = $1", email
        )


async def mark_verified(email: str, token_hash: str, ttl_minutes: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE email_verifications
               SET signup_token_hash = $2,
                   signup_token_expires_at = now() + make_interval(mins => $3)
             WHERE email = $1
            """,
            email,
            token_hash,
            ttl_minutes,
        )


async def fetch_verification_by_token(token_hash: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM email_verifications
             WHERE signup_token_hash = $1 AND signup_token_expires_at > now()
            """,
            token_hash,
        )
    return dict(row) if row else None


async def delete_verification(email: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM email_verifications WHERE email = $1", email)


async def fetch_user_by_token(token: str) -> Optional[UserOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.username, u.email, u.is_admin, u.created_at,
                   u.preferred_name, u.language, u.interests, u.onboarded_at
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = $1
            """,
            token,
        )
    return UserOut.model_validate(dict(row)) if row else None


async def create_session(token: str, user_id: UUID) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sessions (token, user_id) VALUES ($1, $2)", token, user_id
        )


async def delete_session(token: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE token = $1", token)


async def add_friend(user_id: UUID, name: str, email: str) -> FriendOut:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO friends (user_id, name, email)
            VALUES ($1, $2, $3)
            RETURNING id, name, email, created_at
            """,
            user_id,
            name,
            email,
        )
    return FriendOut.model_validate(dict(row))


async def list_friends(user_id: UUID) -> list[FriendOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, email, created_at FROM friends WHERE user_id = $1 ORDER BY created_at ASC",
            user_id,
        )
    return [FriendOut.model_validate(dict(r)) for r in rows]


async def delete_friend(user_id: UUID, friend_id: UUID) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM friends WHERE id = $1 AND user_id = $2", friend_id, user_id
        )
    return result.endswith("1")


# --- auto-alert agent support ---

async def count_recent_negative(user_id: UUID, hours: int = 24) -> tuple[int, int]:
    """Return (negative_segment_count, total_segment_count) in the recent window."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE COALESCE(corrected_sentiment, sentiment) = 'negative'
                ) AS negatives,
                COUNT(*) AS total
            FROM entries
            WHERE user_id = $1 AND created_at >= now() - ($2 || ' hours')::interval
            """,
            user_id,
            str(hours),
        )
    return int(row["negatives"]), int(row["total"])


async def record_alert(
    user_id: UUID, reason: str, friends_sent: int, friends_failed: int, self_sent: bool
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO well_being_alerts (user_id, reason, friends_sent, friends_failed, self_sent)
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id, reason, friends_sent, friends_failed, self_sent,
        )


async def list_alerts(user_id: UUID, limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT reason, friends_sent, friends_failed, self_sent, created_at
            FROM well_being_alerts WHERE user_id = $1
            ORDER BY created_at DESC LIMIT $2
            """,
            user_id, limit,
        )
    return [dict(r) for r in rows]


async def last_alert_with_reason(user_id: UUID, reason: str):
    """When an alert of this kind ('crisis', 'sustained') last actually reached someone."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            SELECT MAX(created_at) FROM well_being_alerts
            WHERE user_id = $1 AND reason = $2 AND (friends_sent > 0 OR self_sent)
            """,
            user_id,
            reason,
        )


async def last_alert_at(user_id: UUID):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT last_alert_at FROM users WHERE id = $1", user_id)


async def mark_alert_sent(user_id: UUID) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_alert_at = now() WHERE id = $1", user_id
        )


async def alert_allowed(user_id: UUID, cooldown_hours: int = 12) -> bool:
    """True if no alert has been sent within the cooldown window."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        last = await conn.fetchval("SELECT last_alert_at FROM users WHERE id = $1", user_id)
    if last is None:
        return True
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) - last >= timedelta(hours=cooldown_hours)


async def insert_community_message(
    channel_id: UUID,
    handle: str,
    content: str,
    *,
    is_bot: bool = False,
    reply_to: Optional[UUID] = None,
    image_id: Optional[UUID] = None,
) -> CommunityMessageOut:
    """Post one message to a community channel under the author's alias."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO community_messages (channel_id, handle, content, is_bot, reply_to, image_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            channel_id,
            handle,
            content,
            is_bot,
            reply_to,
            image_id,
        )
    return CommunityMessageOut.model_validate(dict(row))


async def fetch_community_messages(channel_id: UUID, limit: int = 100) -> list[CommunityMessageOut]:
    """Return a channel's most recent messages, oldest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            SELECT * FROM (
                SELECT * FROM community_messages
                WHERE channel_id = $1 AND created_at > now() - make_interval(hours => $3)
                ORDER BY created_at DESC
                LIMIT $2
            ) recent
            ORDER BY created_at ASC
            """,
            channel_id,
            limit,
            COMMUNITY_TTL_HOURS,
        )
    return [CommunityMessageOut.model_validate(dict(r)) for r in result]


# --- community channels ---

async def list_channels() -> list[ChannelOut]:
    """All channels: defaults first (in their set order), then newest activity first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.slug, c.name, c.description, c.is_default, c.created_at,
                   MAX(m.created_at) AS last_message_at,
                   COUNT(m.id) AS message_count
            FROM community_channels c
            LEFT JOIN community_messages m
                   ON m.channel_id = c.id AND m.created_at > now() - make_interval(hours => $1)
            GROUP BY c.id
            ORDER BY c.is_default DESC, c.position ASC,
                     MAX(m.created_at) DESC NULLS LAST, c.created_at DESC
            """,
            COMMUNITY_TTL_HOURS,
        )
    return [ChannelOut.model_validate(dict(r)) for r in rows]


async def get_channel(channel_id: UUID) -> Optional[ChannelOut]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, slug, name, description, is_default, created_at,
                   NULL::timestamptz AS last_message_at, 0 AS message_count
            FROM community_channels WHERE id = $1
            """,
            channel_id,
        )
    return ChannelOut.model_validate(dict(row)) if row else None


async def create_channel(slug: str, description: str, created_by: UUID) -> ChannelOut:
    """Raises asyncpg.UniqueViolationError if the slug exists."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO community_channels (slug, name, description, created_by)
            VALUES ($1, $1, $2, $3)
            RETURNING id, slug, name, description, is_default, created_at,
                      NULL::timestamptz AS last_message_at, 0 AS message_count
            """,
            slug,
            description,
            created_by,
        )
    return ChannelOut.model_validate(dict(row))


async def channels_created_since(user_id: UUID, hours: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return int(
            await conn.fetchval(
                """
                SELECT COUNT(*) FROM community_channels
                WHERE created_by = $1 AND created_at >= now() - make_interval(hours => $2)
                """,
                user_id,
                hours,
            )
        )


async def recent_human_handles(channel_id: UUID, minutes: int) -> set[str]:
    """Handles of people (not companions) who posted in a channel recently."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT handle FROM community_messages
            WHERE channel_id = $1 AND NOT is_bot
              AND created_at >= now() - make_interval(mins => $2)
            """,
            channel_id,
            minutes,
        )
    return {r["handle"] for r in rows}


# --- community aliases, mentions, images, expiry ---

async def get_alias(user_id: UUID) -> Optional[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT community_alias FROM users WHERE id = $1", user_id)


async def alias_owner(alias: str) -> Optional[UUID]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT id FROM users WHERE lower(community_alias) = lower($1)", alias
        )


async def set_alias(user_id: UUID, alias: str) -> None:
    """Raises asyncpg.UniqueViolationError if another person has it."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET community_alias = $2 WHERE id = $1", user_id, alias)


async def users_for_aliases(aliases: list[str]) -> dict[str, UUID]:
    """Map lower-cased aliases to user ids, for the ones that exist."""
    if not aliases:
        return {}
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, lower(community_alias) AS alias FROM users WHERE lower(community_alias) = ANY($1::text[])",
            [a.lower() for a in aliases],
        )
    return {r["alias"]: r["id"] for r in rows}


async def search_aliases(prefix: str, limit: int = 8) -> list[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT community_alias FROM users
            WHERE community_alias IS NOT NULL AND lower(community_alias) LIKE lower($1) || '%'
            ORDER BY lower(community_alias) LIMIT $2
            """,
            prefix,
            limit,
        )
    return [r["community_alias"] for r in rows]


async def insert_image(data: bytes, mime: str, width: int, height: int) -> UUID:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO community_images (data, mime, width, height) VALUES ($1, $2, $3, $4) RETURNING id",
            data, mime, width, height,
        )


async def get_image(image_id: UUID) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT data, mime FROM community_images
            WHERE id = $1 AND created_at > now() - make_interval(hours => $2)
            """,
            image_id,
            COMMUNITY_TTL_HOURS,
        )
    return dict(row) if row else None


async def purge_expired_community() -> tuple[int, int]:
    """Delete community messages and images older than the TTL. Returns (messages, images)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            m = await conn.execute(
                "DELETE FROM community_messages WHERE created_at <= now() - make_interval(hours => $1)",
                COMMUNITY_TTL_HOURS,
            )
            i = await conn.execute(
                "DELETE FROM community_images WHERE created_at <= now() - make_interval(hours => $1)",
                COMMUNITY_TTL_HOURS,
            )
    return int(m.split()[-1]), int(i.split()[-1])


# --- profile ---

async def update_profile(
    user_id: UUID, preferred_name: Optional[str], language: str, interests: list[str]
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE users
               SET preferred_name = $2, language = $3, interests = $4,
                   onboarded_at = COALESCE(onboarded_at, now())
             WHERE id = $1
            """,
            user_id, preferred_name, language, interests,
        )


async def set_email(user_id: UUID, email: str) -> None:
    """Raises asyncpg.UniqueViolationError if another account has it."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET email = $2 WHERE id = $1", user_id, email)


async def users_needing_setup_reminder() -> list[dict]:
    """Accounts with an email that haven't finished their profile and weren't reminded yet."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, username, email FROM users
            WHERE email IS NOT NULL AND onboarded_at IS NULL AND setup_reminder_sent_at IS NULL
            """
        )
    return [dict(r) for r in rows]


async def mark_setup_reminder_sent(user_id: UUID) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET setup_reminder_sent_at = now() WHERE id = $1", user_id)


# --- event reminders ---

async def events_due_for_reminder(start: date, end: date) -> list[dict]:
    """Un-reminded events dated between start and end (inclusive) for people with an email."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id, e.segment_text, e.event_date, e.event_time, e.person,
                   u.id AS user_id, u.username, u.preferred_name, u.email
            FROM entries e JOIN users u ON u.id = e.user_id
            WHERE COALESCE(e.corrected_type, e.entry_type) = 'event'
              AND e.event_date BETWEEN $1 AND $2
              AND e.reminder_sent_at IS NULL
              AND NOT e.is_fallback
              AND u.email IS NOT NULL
            """,
            start,
            end,
        )
    return [dict(r) for r in rows]


async def mark_reminder_sent(entry_id: UUID) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE entries SET reminder_sent_at = now() WHERE id = $1", entry_id)


# --- daily summaries ---

async def get_day_summary(user_id: UUID, day: date) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM day_summaries WHERE user_id = $1 AND day = $2", user_id, day
        )
    return dict(row) if row else None


async def save_day_summary(user_id: UUID, day: date, data: dict, entry_count: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO day_summaries (user_id, day, title, body, mood, highlights, looking_ahead, entry_count)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (user_id, day) DO UPDATE
               SET title = EXCLUDED.title, body = EXCLUDED.body, mood = EXCLUDED.mood,
                   highlights = EXCLUDED.highlights, looking_ahead = EXCLUDED.looking_ahead,
                   entry_count = EXCLUDED.entry_count, updated_at = now()
            RETURNING *
            """,
            user_id, day, data["title"], data["body"], data.get("mood"),
            data.get("highlights", []), data.get("looking_ahead", []), entry_count,
        )
    return dict(row)


async def days_with_entries(user_id: UUID, limit: int = 60) -> list[date]:
    """Most recent days the person wrote anything, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT created_at::date AS day FROM messages
            WHERE user_id = $1 AND role = 'user'
            ORDER BY day DESC LIMIT $2
            """,
            user_id, limit,
        )
    return [r["day"] for r in rows]
