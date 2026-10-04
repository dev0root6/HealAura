"""Email reminders for events people mention in their journal.

An "event" segment with a date (e.g. "placement interview tomorrow at 10") gets
one email:
  - events with a time: 1 hour before,
  - events with only a date: at 8:00 that morning.
If the entry was written after that moment but the event hasn't happened yet,
the reminder goes out right away. Past events are never emailed.

Times are interpreted in REMINDER_TIMEZONE (default Asia/Kolkata), since the
journal stores the date/time as the person said it. Runs in-process every minute.
"""

import asyncio
import logging
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import db
import email_client
import emails

logger = logging.getLogger(__name__)

TZ = ZoneInfo(os.getenv("REMINDER_TIMEZONE", "Asia/Kolkata"))
LEAD = timedelta(hours=1)
MORNING = time(8, 0)
TICK_SECONDS = 60


def send_window(event_date: date, event_time: time | None) -> tuple[datetime, datetime]:
    """(send from, too late after) for one event, in the reminder timezone."""
    if event_time is not None:
        at = datetime.combine(event_date, event_time, TZ)
        return at - LEAD, at
    return datetime.combine(event_date, MORNING, TZ), datetime.combine(event_date + timedelta(days=1), time(0), TZ)


def when_label(event_date: date, event_time: time | None, now: datetime) -> str:
    day = "Today" if event_date == now.date() else event_date.strftime("%A, %d %b")
    return f"{day} at {event_time.strftime('%I:%M %p').lstrip('0')}" if event_time else day


async def send_due_reminders(now: datetime | None = None) -> int:
    """Email every reminder that is due now. Returns how many went out."""
    if not email_client.configured():
        return 0
    now = now or datetime.now(TZ)
    sent = 0
    for ev in await db.events_due_for_reminder(now.date(), now.date() + timedelta(days=1)):
        start, end = send_window(ev["event_date"], ev["event_time"])
        if not (start <= now < end):
            continue
        name = ev["preferred_name"] or ev["username"]
        subject, text, html = emails.event_reminder(
            name, ev["segment_text"], when_label(ev["event_date"], ev["event_time"], now), ev["person"]
        )
        try:
            await email_client.send_email(ev["email"], subject, text, html)
            await db.mark_reminder_sent(ev["id"])
            sent += 1
            logger.info("Event reminder emailed to %s", ev["username"])
        except RuntimeError as exc:
            logger.warning("Could not email reminder to %s: %s", ev["username"], exc)
    return sent


async def run_forever() -> None:
    while True:
        try:
            await send_due_reminders()
        except Exception:
            logger.exception("Reminder run failed")
        await asyncio.sleep(TICK_SECONDS)
