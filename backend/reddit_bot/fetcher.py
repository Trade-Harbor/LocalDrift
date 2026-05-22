"""Pull the month's events from the database for Reddit-bot rendering.

Kept minimal — just the month-window filter + a few hygiene filters
(hide auto-moderated content, drop events with missing critical fields).
Sorting and grouping are the formatter's job.
"""
from __future__ import annotations

from datetime import datetime, timezone
from .formatter import month_window


async def fetch_month_events(db, month_key: str, max_events: int = 200) -> list[dict]:
    """Return all events scheduled to start within the given YYYY-MM
    that should be visible publicly. Sorted by start_date ascending."""
    start_utc, end_utc = month_window(month_key)

    # start_date is stored as ISO strings (set by ingestion + user-create flow
    # via .isoformat()), so string comparison works for the range filter.
    query = {
        "start_date": {
            "$gte": start_utc.isoformat(),
            "$lt": end_utc.isoformat(),
        },
        "is_hidden": {"$ne": True},
    }

    cursor = (
        db.events.find(query, {"_id": 0})
        .sort("start_date", 1)
        .limit(max_events)
    )
    raw = await cursor.to_list(max_events)

    # Drop events missing critical render fields.
    out = []
    for ev in raw:
        if not ev.get("title") or not ev.get("start_date"):
            continue
        out.append(ev)
    return out
