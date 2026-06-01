"""Fetch the week's events for the Instagram carousel.

Mirrors backend/reddit_bot/fetcher.py — same DB shape, different
date-window helper.
"""
from __future__ import annotations

from datetime import datetime

from .renderer import week_window


async def fetch_week_events(
    db,
    monday_utc: datetime | None = None,
    sunday_utc: datetime | None = None,
    max_events: int = 50,
) -> list[dict]:
    """Return events whose start falls inside the given Mon-Sun window.
    If the window isn't provided, fetches the upcoming week.

    Filters out auto-moderated events (is_hidden=True) and drops items
    without title or start_date so the renderer doesn't crash on them.
    """
    if monday_utc is None or sunday_utc is None:
        monday_utc, sunday_utc = week_window()

    query = {
        "start_date": {
            "$gte": monday_utc.isoformat(),
            "$lte": sunday_utc.isoformat(),
        },
        "is_hidden": {"$ne": True},
    }
    cursor = (
        db.events.find(query, {"_id": 0})
        .sort("start_date", 1)
        .limit(max_events)
    )
    raw = await cursor.to_list(max_events)
    return [ev for ev in raw if ev.get("title") and ev.get("start_date")]
