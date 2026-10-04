"""Mood trends: per-day sentiment counts and a smoothed negativity score.

Counts use the effective label (the user's correction if there is one), the
same rule the well-being agent uses. The smoothed score is an exponentially
weighted moving average of each day's negative share; days without entries
carry the previous value forward rather than pulling it towards zero, since
"didn't write" is not "felt fine".
"""

from datetime import date, timedelta
from uuid import UUID

import db
from models import VALID_SENTIMENTS, DayTrend, TrendsOut

# Weight of the newest day in the moving average (~a one-week memory).
SMOOTHING_ALPHA = 0.3


def summarise(rows: list[dict], start: date, end: date) -> TrendsOut:
    """Turn (day, sentiment, n) rows into a gap-free series from start to end."""
    by_day: dict[date, dict[str, int]] = {}
    for r in rows:
        if r["sentiment"] in VALID_SENTIMENTS:
            by_day.setdefault(r["day"], {})[r["sentiment"]] = int(r["n"])

    days: list[DayTrend] = []
    totals = {s: 0 for s in VALID_SENTIMENTS}
    smoothed = None
    d = start
    while d <= end:
        counts = by_day.get(d, {})
        total = sum(counts.values())
        share = counts.get("negative", 0) / total if total else None
        if share is not None:
            smoothed = share if smoothed is None else SMOOTHING_ALPHA * share + (1 - SMOOTHING_ALPHA) * smoothed
        for s, n in counts.items():
            totals[s] += n
        days.append(DayTrend(
            day=d,
            total=total,
            negative_share=round(share, 3) if share is not None else None,
            smoothed_negative=round(smoothed, 3) if smoothed is not None else None,
            **counts,
        ))
        d += timedelta(days=1)
    return TrendsOut(days=days, totals=totals)


async def build(user_id: UUID, days: int) -> TrendsOut:
    end = date.today()
    start = end - timedelta(days=days - 1)
    rows = await db.sentiment_counts_by_day(user_id, start)
    return summarise(rows, start, end)
