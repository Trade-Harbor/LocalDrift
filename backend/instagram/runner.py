"""Orchestrator for the Instagram carousel generator.

Two public entry points:
  preview(db, start_date, mode)
    Returns a dict with metadata + base64-encoded JPEG thumbnails of
    each slide. Used by the admin preview page so the operator can see
    the slides before downloading.

  zip_bytes(db, start_date, mode)
    Renders all slides at full resolution and returns a ZIP file in
    memory containing one PNG per slide, named so they sort in carousel
    order when uploaded to IG.

Both functions accept:
  start_date — optional ISO date "YYYY-MM-DD". Interpreted as the
               Monday (mode=week) or Friday (mode=weekend) of the
               target span. Defaults to the next upcoming Mon / Fri.
  mode       — "week" (Mon-Sun) or "weekend" (Fri-Sun).
"""
from __future__ import annotations

import base64
import io
import logging
import zipfile
from datetime import datetime, timezone
from typing import Optional

from PIL import Image

from .fetcher import fetch_week_events
from .renderer import (
    build_carousel,
    range_label,
    week_window,
    weekday_window,
    weekend_window,
)

logger = logging.getLogger(__name__)


def _resolve_window(
    start_date: Optional[str], mode: str
) -> tuple[datetime, datetime, str]:
    """Pick the right (start_utc, end_utc) tuple based on mode, plus the
    human-readable sub-headline ("this week" / "this weekend") to bake
    into the cover slide. Bad mode string falls back to "week".
    """
    if start_date:
        try:
            anchor = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        except ValueError:
            anchor = None
    else:
        anchor = None

    if mode == "weekend":
        start, end = weekend_window(anchor)
        period_label = "this weekend"
    elif mode == "weekday":
        start, end = weekday_window(anchor)
        period_label = "this week · weekdays"
    else:
        start, end = week_window(anchor)
        period_label = "this week"
    return start, end, period_label


def _slide_to_jpeg_b64(img: Image.Image, max_dim: int = 540) -> str:
    """Downscaled preview as a base64 JPEG. 540x540 is half the slide
    resolution — plenty for visual review and cuts JSON payload from
    ~1.5MB per slide to ~80KB."""
    preview = img.copy()
    preview.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    preview.convert("RGB").save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


async def preview(
    db, week_start: Optional[str] = None, mode: str = "week"
) -> dict:
    """Render every slide and return previews + metadata for the admin UI."""
    start_utc, end_utc, period_label = _resolve_window(week_start, mode)
    events = await fetch_week_events(db, start_utc, end_utc)
    slides = build_carousel(events, start_utc, end_utc, period_label=period_label)

    return {
        "mode": mode if mode in {"week", "weekend", "weekday"} else "week",
        "period_label": period_label,
        "week_label": range_label(start_utc, end_utc),
        "monday_utc": start_utc.isoformat(),  # legacy key kept for backwards-compat
        "sunday_utc": end_utc.isoformat(),
        "start_utc": start_utc.isoformat(),
        "end_utc": end_utc.isoformat(),
        "event_count": len(events),
        "slide_count": len(slides),
        "slides": [
            {
                "index": i,
                "name": _slide_name(i, len(slides)),
                "preview": _slide_to_jpeg_b64(img),
            }
            for i, img in enumerate(slides)
        ],
    }


async def zip_bytes(
    db, week_start: Optional[str] = None, mode: str = "week"
) -> tuple[bytes, str]:
    """Build the carousel + ZIP every slide as a PNG. Returns
    (zip_bytes, suggested_filename). Filename includes the mode so
    successive downloads (week + weekend for the same calendar week)
    don't overwrite each other."""
    start_utc, end_utc, period_label = _resolve_window(week_start, mode)
    events = await fetch_week_events(db, start_utc, end_utc)
    slides = build_carousel(events, start_utc, end_utc, period_label=period_label)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, img in enumerate(slides):
            png_buf = io.BytesIO()
            img.save(png_buf, format="PNG", optimize=True)
            zf.writestr(_slide_name(i, len(slides)) + ".png", png_buf.getvalue())

    mode_tag = mode if mode in {"weekend", "weekday"} else "week"
    filename = f"localdrift_carousel_{mode_tag}_{start_utc.strftime('%Y-%m-%d')}.zip"
    return buf.getvalue(), filename


def _slide_name(index: int, total: int) -> str:
    """Filenames sort lexicographically into carousel order when
    uploaded to IG. Zero-padded so 1..N sorts before 10..."""
    pad = 2  # plenty for the IG 10-slide max
    return f"slide_{index:0{pad}d}"
