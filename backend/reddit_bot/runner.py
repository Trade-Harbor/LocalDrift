"""Reddit bot orchestrator.

Phase D (current) only implements `preview()` — pure dry-run, no Reddit
calls, no DB writes beyond what the fetcher reads. Used by the admin
preview UI to render markdown side-by-side for the community-vote post.

Phase F will add `monthly_rollover()` which submits + stickies via PRAW
and records to db.reddit_posts. Not in this file yet.
"""
from __future__ import annotations

import os

from .fetcher import fetch_month_events
from .formatter import STYLES, default_month_key, render, month_title


async def preview(
    db, style: str, month_key: str | None = None, site_url: str | None = None,
    *, include_tickets: bool = False,
) -> dict:
    """Render the markdown for one style + month combination.
    Returns metadata + the body so the admin UI can show counts and a
    copy-to-clipboard button.

    style ∈ {"weekly", "by_category", "chronological"}
    month_key defaults to the upcoming month.
    site_url defaults to PUBLIC_FRONTEND_URL or production root.
    include_tickets — toggle the optional external "[tickets](url)"
                      suffix on events that have an external_url. Off
                      by default (Option A — clean, no per-event links).
    """
    if style not in STYLES:
        raise ValueError(f"Unknown style {style!r}. Valid: {sorted(STYLES.keys())}")

    mk = month_key or default_month_key()
    base = site_url or os.environ.get("PUBLIC_FRONTEND_URL", "https://www.localdrift.app").rstrip("/")

    events = await fetch_month_events(db, mk)
    markdown = STYLES[style]["render"](events, mk, base, include_tickets=include_tickets)

    return {
        "style": style,
        "style_label": STYLES[style]["label"],
        "month_key": mk,
        "month_label": month_title(mk),
        "event_count": len(events),
        "include_tickets": include_tickets,
        "site_url": base,
        "title": f"What's happening in Wilmington — {month_title(mk)}",
        "markdown": markdown,
    }


async def preview_all(
    db, month_key: str | None = None, site_url: str | None = None,
    *, include_tickets: bool = False,
) -> dict:
    """Render all three styles for the same month in one call so the
    admin UI can show them side-by-side without round-tripping per style."""
    mk = month_key or default_month_key()
    base = site_url or os.environ.get("PUBLIC_FRONTEND_URL", "https://www.localdrift.app").rstrip("/")
    events = await fetch_month_events(db, mk)
    return {
        "month_key": mk,
        "month_label": month_title(mk),
        "event_count": len(events),
        "include_tickets": include_tickets,
        "site_url": base,
        "title": f"What's happening in Wilmington — {month_title(mk)}",
        "styles": {
            key: {
                "label": STYLES[key]["label"],
                "markdown": STYLES[key]["render"](events, mk, base, include_tickets=include_tickets),
            }
            for key in STYLES.keys()
        },
    }
