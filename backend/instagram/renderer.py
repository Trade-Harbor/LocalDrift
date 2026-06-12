"""Pure PIL rendering for Instagram carousel slides.

No I/O beyond loading the bundled logo + font files. Takes a list of
event dicts, returns a list of 1080x1080 PIL Image objects ready to
save as PNG.

Design:
- Brand teal background (#1e6b6b) so each slide reads as LocalDrift
- Cover slide: big "WHAT'S HAPPENING" headline + week range
- One slide per event: day/time/title/venue/short description
- CTA slide: localdrift.app + handle

Slides are designed for IG's standard 1080x1080 square format.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# ---------- Constants ----------

SLIDE_SIZE = (1080, 1080)
BG_TEAL = (30, 107, 107)          # #1e6b6b — brand
BG_TEAL_DARK = (20, 78, 78)        # darker shade for accents
ACCENT_GOLD = (212, 165, 90)       # matches the L mark
TEXT_WHITE = (255, 255, 255)
TEXT_DIM = (220, 220, 220)
TEXT_FAINT = (180, 200, 200)

PAD = 80  # outer padding for all slide content

ET = ZoneInfo("America/New_York")

ASSETS_DIR = Path(__file__).parent / "assets"
FONTS_DIR = Path(__file__).parent / "fonts"

# Category labels for the per-event badge (mirrors reddit_bot/formatter.py)
CATEGORY_LABEL = {
    "concert": "CONCERT",
    "parade": "PARADE",
    "marathon": "RACE",
    "market": "MARKET",
    "happy_hour": "HAPPY HOUR",
    "garage_sale": "GARAGE SALE",
    "food_festival": "FOOD",
    "community": "COMMUNITY",
    "sports": "SPORTS",
    "other": "EVENT",
}

# Per-category accent colors for the badge — keeps each slide distinguishable
# in a carousel without losing the LocalDrift teal identity.
CATEGORY_COLOR = {
    "concert": (138, 99, 210),
    "parade": (216, 99, 138),
    "marathon": (216, 138, 99),
    "market": (99, 167, 138),
    "happy_hour": (210, 165, 99),
    "garage_sale": (210, 138, 99),
    "food_festival": (216, 99, 99),
    "community": (99, 138, 210),
    "sports": (210, 99, 138),
    "other": (138, 138, 138),
}


# ---------- Font loading with fallbacks ----------

# Candidate font paths in priority order. The first existing file wins.
_FONT_CANDIDATES = {
    "black": [
        FONTS_DIR / "Inter-Black.ttf",
        FONTS_DIR / "Inter-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),  # macOS dev
        Path("C:/Windows/Fonts/arialbd.ttf"),    # Windows dev
    ],
    "bold": [
        FONTS_DIR / "Inter-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ],
    "regular": [
        FONTS_DIR / "Inter-Regular.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ],
}

# Cache resolved font paths so we don't stat the filesystem on every call.
_resolved_font_paths: dict[str, str | None] = {}


def _font_path(weight: str) -> str | None:
    if weight in _resolved_font_paths:
        return _resolved_font_paths[weight]
    for cand in _FONT_CANDIDATES.get(weight, []):
        if cand.exists():
            _resolved_font_paths[weight] = str(cand)
            return str(cand)
    logger.warning("No font found for weight=%s — falling back to PIL default", weight)
    _resolved_font_paths[weight] = None
    return None


def _load_font(weight: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font at a given size. Falls back gracefully to PIL's default
    bitmap font if no TTF is available (which will look ugly but won't crash)."""
    path = _font_path(weight)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception as e:
            logger.warning("Failed to load %s at size %d: %s", path, size, e)
    return ImageFont.load_default()


# ---------- Logo loading ----------

_logo_cache: Image.Image | None = None


def _logo(size: int) -> Image.Image | None:
    global _logo_cache
    path = ASSETS_DIR / "logo-icon.png"
    if not path.exists():
        return None
    if _logo_cache is None:
        _logo_cache = Image.open(path).convert("RGBA")
    return _logo_cache.copy().resize((size, size), Image.LANCZOS)


# ---------- Text helpers ----------

def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    """Pillow's text size API changed across versions; this normalizes to width."""
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    return draw.textsize(text, font=font)[0]


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    if hasattr(draw, "textbbox"):
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    return draw.textsize(text, font=font)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Greedy word-wrap so long event titles flow to a second/third line."""
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_text_centered(draw, text, font, y, fill=TEXT_WHITE, slide_width=SLIDE_SIZE[0]):
    w, _ = _text_size(draw, text, font)
    draw.text(((slide_width - w) // 2, y), text, font=font, fill=fill)


def _draw_text_wrapped_centered(
    draw, text, font, y, max_width, line_height=None, fill=TEXT_WHITE,
    slide_width=SLIDE_SIZE[0],
) -> int:
    """Wraps text and draws each line centered. Returns the y position
    after the last line so the caller can stack content below."""
    lines = _wrap(draw, text, font, max_width)
    if not lines:
        return y
    if line_height is None:
        _, h = _text_size(draw, "Mg", font)
        line_height = int(h * 1.15)
    for line in lines:
        _draw_text_centered(draw, line, font, y, fill=fill, slide_width=slide_width)
        y += line_height
    return y


# ---------- Date helpers (mirrors reddit_bot/formatter style) ----------

def _parse_event_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def week_window(start_date: datetime | None = None) -> tuple[datetime, datetime]:
    """Return Monday-Sunday window in ET, returned as UTC datetimes.
    If start_date is None, returns the upcoming Mon-Sun (whatever week starts
    next Monday in Eastern Time)."""
    now = (start_date or datetime.now(timezone.utc)).astimezone(ET)
    # Roll to next Monday — if today IS Monday, use today
    days_to_monday = (7 - now.weekday()) % 7 if now.weekday() != 0 else 0
    monday_local = (now + timedelta(days=days_to_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    sunday_local = monday_local + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday_local.astimezone(timezone.utc), sunday_local.astimezone(timezone.utc)


def weekend_window(start_date: datetime | None = None) -> tuple[datetime, datetime]:
    """Return Friday 00:00 ET through Sunday 23:59 ET, as UTC datetimes.
    If start_date is None, returns the upcoming Fri-Sun. If today IS Friday,
    uses today (so a Friday-morning post still covers tonight)."""
    now = (start_date or datetime.now(timezone.utc)).astimezone(ET)
    # Weekday: Mon=0, Fri=4. Days until Friday.
    days_to_friday = (4 - now.weekday()) % 7
    friday_local = (now + timedelta(days=days_to_friday)).replace(hour=0, minute=0, second=0, microsecond=0)
    sunday_local = friday_local + timedelta(days=2, hours=23, minutes=59, seconds=59)
    return friday_local.astimezone(timezone.utc), sunday_local.astimezone(timezone.utc)


def range_label(start_utc: datetime, end_utc: datetime) -> str:
    """Format a date range as "Jun 8 – 14" (same month) or "Jun 30 – Jul 6"
    (cross-month). Works for both Mon-Sun weeks and Fri-Sun weekends."""
    s = start_utc.astimezone(ET)
    e = end_utc.astimezone(ET)
    if s.month == e.month:
        return f"{s.strftime('%b %d').replace(' 0', ' ')} – {e.strftime('%d')}"
    return f"{s.strftime('%b %d').replace(' 0', ' ')} – {e.strftime('%b %d').replace(' 0', ' ')}"


# Backward-compat alias — older callers (Reddit bot, tests) may import week_label.
# Same implementation, just renamed for clarity now that weekends share it.
week_label = range_label


# ---------- Slide builders ----------

def build_cover(
    start_utc: datetime, end_utc: datetime, *, period_label: str = "this week"
) -> Image.Image:
    """First slide: brand + headline + range label + swipe prompt.

    period_label drives the sub-headline ("this week" or "this weekend").
    The range below it shows the actual date span from start_utc to end_utc."""
    img = Image.new("RGB", SLIDE_SIZE, BG_TEAL)
    draw = ImageDraw.Draw(img)

    # Logo at the top center
    logo = _logo(220)
    if logo is not None:
        img.paste(logo, ((SLIDE_SIZE[0] - 220) // 2, 100), logo)

    headline_font = _load_font("black", 96)
    week_font = _load_font("bold", 68)
    sub_font = _load_font("regular", 44)
    swipe_font = _load_font("regular", 36)

    # "WHAT'S HAPPENING" — split into two lines
    y = 380
    _draw_text_centered(draw, "WHAT'S HAPPENING", headline_font, y)
    y += 110
    _draw_text_centered(draw, "IN WILMINGTON", headline_font, y)
    y += 130
    _draw_text_centered(draw, period_label, sub_font, y, fill=TEXT_DIM)
    y += 80
    label = range_label(start_utc, end_utc).upper()
    _draw_text_centered(draw, label, week_font, y, fill=ACCENT_GOLD)

    # Swipe prompt
    _draw_text_centered(draw, "swipe →", swipe_font, SLIDE_SIZE[1] - 120, fill=TEXT_FAINT)

    return img


def build_event(event: dict, slide_index: int, total: int) -> Image.Image:
    """One slide per event. Shows the day+date prominently, then time,
    then title (wrapped), venue, and a short description."""
    img = Image.new("RGB", SLIDE_SIZE, BG_TEAL)
    draw = ImageDraw.Draw(img)

    # Tiny logo + handle at top-left so every reshared slide carries identity
    logo = _logo(56)
    if logo is not None:
        img.paste(logo, (PAD, PAD), logo)
    handle_font = _load_font("bold", 28)
    draw.text((PAD + 70, PAD + 14), "@localdrift.app", font=handle_font, fill=TEXT_DIM)

    # Counter top-right (e.g. "2 / 7")
    counter_font = _load_font("regular", 28)
    counter = f"{slide_index} / {total}"
    cw, _ = _text_size(draw, counter, counter_font)
    draw.text((SLIDE_SIZE[0] - PAD - cw, PAD + 14), counter, font=counter_font, fill=TEXT_DIM)

    # Category badge top-center
    category = (event.get("category") or "other").lower()
    cat_label = CATEGORY_LABEL.get(category, "EVENT")
    cat_color = CATEGORY_COLOR.get(category, CATEGORY_COLOR["other"])
    badge_font = _load_font("bold", 30)
    bw, bh = _text_size(draw, cat_label, badge_font)
    badge_pad_x, badge_pad_y = 28, 14
    badge_w, badge_h = bw + badge_pad_x * 2, bh + badge_pad_y * 2
    badge_x = (SLIDE_SIZE[0] - badge_w) // 2
    badge_y = PAD + 60
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=badge_h // 2,
        fill=cat_color,
    )
    draw.text((badge_x + badge_pad_x, badge_y + badge_pad_y - 4), cat_label, font=badge_font, fill=TEXT_WHITE)

    # Compute local datetime
    dt = _parse_event_dt(event.get("start_date"))
    local = dt.astimezone(ET) if dt else None

    # Big date — "SAT JUN 7"
    date_font = _load_font("black", 132)
    time_font = _load_font("bold", 64)
    if local:
        date_str = local.strftime("%a %b %d").replace(" 0", " ").upper()
        time_str = local.strftime("%I:%M %p ET").lstrip("0")
    else:
        date_str = "TBD"
        time_str = ""

    y = 280
    _draw_text_centered(draw, date_str, date_font, y, fill=TEXT_WHITE)
    y += 160
    if time_str:
        _draw_text_centered(draw, time_str, time_font, y, fill=ACCENT_GOLD)
        y += 100
    else:
        y += 40

    # Event title — wrapped, can take 2-3 lines
    title_font = _load_font("bold", 56)
    title = event.get("title") or "Untitled event"
    y = _draw_text_wrapped_centered(
        draw, title, title_font, y,
        max_width=SLIDE_SIZE[0] - 2 * PAD,
        line_height=70,
        fill=TEXT_WHITE,
    )
    y += 16

    # Venue
    venue_font = _load_font("regular", 36)
    venue = event.get("location_name") or event.get("city") or ""
    if venue:
        y = _draw_text_wrapped_centered(
            draw, venue, venue_font, y,
            max_width=SLIDE_SIZE[0] - 2 * PAD,
            line_height=46,
            fill=TEXT_FAINT,
        )

    # Short description in a separated zone near the bottom
    desc = (event.get("description") or "").strip()
    if desc:
        desc_font = _load_font("regular", 30)
        # Truncate to roughly 2 lines worth of characters
        max_chars = 130
        snippet = desc[:max_chars]
        if len(desc) > max_chars:
            snippet = snippet.rstrip() + "…"
        _draw_text_wrapped_centered(
            draw, snippet, desc_font, SLIDE_SIZE[1] - 230,
            max_width=SLIDE_SIZE[0] - 2 * PAD,
            line_height=40,
            fill=TEXT_DIM,
        )

    return img


def build_cta() -> Image.Image:
    """Final slide: where to find more. Brand-heavy."""
    img = Image.new("RGB", SLIDE_SIZE, BG_TEAL)
    draw = ImageDraw.Draw(img)

    # Big logo center
    logo = _logo(280)
    if logo is not None:
        img.paste(logo, ((SLIDE_SIZE[0] - 280) // 2, 160), logo)

    sub_font = _load_font("regular", 44)
    huge_font = _load_font("black", 100)
    handle_font = _load_font("bold", 48)
    line_font = _load_font("regular", 32)

    y = 500
    _draw_text_centered(draw, "FIND THESE & MORE AT", sub_font, y, fill=TEXT_DIM)
    y += 80
    _draw_text_centered(draw, "localdrift.app", huge_font, y, fill=ACCENT_GOLD)
    y += 160
    _draw_text_centered(draw, "@localdrift.app", handle_font, y, fill=TEXT_WHITE)
    y += 80
    _draw_text_centered(draw, "Free local discovery for Wilmington, NC", line_font, y, fill=TEXT_FAINT)

    return img


def build_carousel(
    events: list[dict],
    start_utc: datetime,
    end_utc: datetime,
    *,
    period_label: str = "this week",
) -> list[Image.Image]:
    """Build the full carousel: cover + up to N event slides + CTA.

    IG carousels cap at 10 slides. We use cover + CTA + up to 8 events
    to leave headroom. If there are more events than the cap, we
    sort by start time and pick the earliest.

    period_label is passed through to the cover slide ("this week" /
    "this weekend") so the same builder works for both modes."""
    sorted_events = sorted(
        events,
        key=lambda e: _parse_event_dt(e.get("start_date")) or datetime.max.replace(tzinfo=timezone.utc),
    )
    capped = sorted_events[:8]

    slides: list[Image.Image] = []
    total_events = len(capped)
    slides.append(build_cover(start_utc, end_utc, period_label=period_label))
    for idx, ev in enumerate(capped, start=1):
        slides.append(build_event(ev, idx, total_events))
    slides.append(build_cta())
    return slides
