"""Orchestrator for the Instagram carousel generator.

Two public entry points:
  preview(db, week_start)
    Returns a dict with metadata + base64-encoded JPEG thumbnails of
    each slide. Used by the admin preview page so the operator can see
    the slides before downloading.

  zip_bytes(db, week_start)
    Renders all slides at full resolution and returns a ZIP file in
    memory containing one PNG per slide, named so they sort in carousel
    order when uploaded to IG.

Both functions accept an optional `week_start` (ISO date "YYYY-MM-DD").
If omitted, defaults to the upcoming Monday in Eastern Time.
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
from .renderer import build_carousel, week_label, week_window

logger = logging.getLogger(__name__)


def _resolve_week(week_start: Optional[str]) -> tuple[datetime, datetime]:
    """Convert an optional 'YYYY-MM-DD' Monday hint into the (monday_utc,
    sunday_utc) tuple the renderer + fetcher both want."""
    if week_start:
        try:
            anchor = datetime.fromisoformat(week_start).replace(tzinfo=timezone.utc)
        except ValueError:
            anchor = None
    else:
        anchor = None
    return week_window(anchor)


def _slide_to_jpeg_b64(img: Image.Image, max_dim: int = 540) -> str:
    """Downscaled preview as a base64 JPEG. 540x540 is half the slide
    resolution — plenty for visual review and cuts JSON payload from
    ~1.5MB per slide to ~80KB."""
    preview = img.copy()
    preview.thumbnail((max_dim, max_dim), Image.LANCZOS)
    buf = io.BytesIO()
    preview.convert("RGB").save(buf, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


async def preview(db, week_start: Optional[str] = None) -> dict:
    """Render every slide and return previews + metadata for the admin UI."""
    monday_utc, sunday_utc = _resolve_week(week_start)
    events = await fetch_week_events(db, monday_utc, sunday_utc)
    slides = build_carousel(events, monday_utc, sunday_utc)

    return {
        "week_label": week_label(monday_utc, sunday_utc),
        "monday_utc": monday_utc.isoformat(),
        "sunday_utc": sunday_utc.isoformat(),
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


async def zip_bytes(db, week_start: Optional[str] = None) -> tuple[bytes, str]:
    """Build the carousel + ZIP every slide as a PNG. Returns
    (zip_bytes, suggested_filename)."""
    monday_utc, sunday_utc = _resolve_week(week_start)
    events = await fetch_week_events(db, monday_utc, sunday_utc)
    slides = build_carousel(events, monday_utc, sunday_utc)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, img in enumerate(slides):
            png_buf = io.BytesIO()
            img.save(png_buf, format="PNG", optimize=True)
            zf.writestr(_slide_name(i, len(slides)) + ".png", png_buf.getvalue())

    filename = f"localdrift_carousel_{monday_utc.strftime('%Y-%m-%d')}.zip"
    return buf.getvalue(), filename


def _slide_name(index: int, total: int) -> str:
    """Filenames sort lexicographically into carousel order when
    uploaded to IG. Zero-padded so 1..N sorts before 10..."""
    pad = 2  # plenty for the IG 10-slide max
    return f"slide_{index:0{pad}d}"
