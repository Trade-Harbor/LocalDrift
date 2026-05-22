"""Pure functions for turning a list of event dicts into Reddit-flavored markdown.

Three styles live here side by side; the community-vote post on r/Wilmington
shows all three and the winning one becomes the production template.

Design notes:
- Pure functions (no I/O, no DB, no PRAW) so they're trivially unit-testable
  and we can preview from the admin UI without touching the database
  beyond the fetcher pass.
- All dates rendered in Eastern Time explicitly ("ET") — events are stored
  UTC but Wilmington readers think in local time.
- Markdown-special characters in event titles are escaped so an event
  called "Wing*Fest" doesn't break Reddit's bold parser.
- Per-section soft cap to prevent walls of text; overflow shown as a
  link back to LocalDrift.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Iterable
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Reddit's markdown is a CommonMark dialect with a few extras. These are
# the characters we escape inside text we don't want interpreted.
_MD_ESCAPE = re.compile(r"([\\`*_{}\[\]()#+\-!>~|])")

# Per-section soft cap. More than this and the section gets a "see all on
# LocalDrift" trailer instead of a wall of text.
SECTION_CAP_DEFAULT = 12

# Category display labels. Keys MUST match backend EventCreate.category values.
CATEGORY_LABEL = {
    "concert": "Concerts & Live Music",
    "parade": "Parades",
    "marathon": "Races & Marathons",
    "market": "Markets",
    "happy_hour": "Happy Hours",
    "garage_sale": "Garage Sales",
    "food_festival": "Food Festivals",
    "community": "Community Events",
    "sports": "Sports",
    "other": "Other",
}
CATEGORY_ORDER = [
    "concert", "sports", "food_festival", "market", "community",
    "happy_hour", "parade", "marathon", "garage_sale", "other",
]


# ---------- Date / month helpers ----------

def month_window(month_key: str) -> tuple[datetime, datetime]:
    """Return UTC start/end-exclusive timestamps for a given YYYY-MM."""
    year, month = (int(x) for x in month_key.split("-"))
    start_local = datetime(year, month, 1, tzinfo=ET)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=ET)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=ET)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def default_month_key(now: datetime | None = None) -> str:
    """The "next month" key — what the bot would post about today if asked."""
    now = now or datetime.now(timezone.utc)
    nxt = (now.replace(day=28) + timedelta(days=10)).replace(day=1)
    return nxt.strftime("%Y-%m")


def month_title(month_key: str) -> str:
    year, month = (int(x) for x in month_key.split("-"))
    return datetime(year, month, 1).strftime("%B %Y")


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


def _local(dt: datetime) -> datetime:
    return dt.astimezone(ET)


# ---------- Markdown helpers ----------

def escape_md(text: str) -> str:
    """Escape characters Reddit's markdown parser interprets. Leaves
    apostrophes and quotes alone since they're benign."""
    if not text:
        return ""
    return _MD_ESCAPE.sub(r"\\\1", text)


def format_event_line(event: dict, site_url: str, style: str = "compact") -> str:
    """One event rendered as a single markdown line.

    style:
      compact      — "**Sat May 24 · 7:00 PM** — [Title](localdrift) at Venue"
      with_tickets — same plus an explicit "tickets" link if external_url exists
      bullet       — "* " prefixed compact line for use inside bulleted lists
    """
    dt = _parse_event_dt(event.get("start_date"))
    if dt is None:
        return ""
    local = _local(dt)
    # Cross-platform-safe formatting; %-I and %-d are POSIX-only.
    when = local.strftime("%a %b %d") + " · " + local.strftime("%I:%M %p").lstrip("0") + " ET"
    title = escape_md(event.get("title") or "Untitled event")
    venue = escape_md(event.get("location_name") or event.get("city") or "")
    event_id = event.get("event_id", "")
    link = f"{site_url}/events/{event_id}" if event_id else site_url

    base = f"**{when}** — [{title}]({link})"
    if venue:
        base += f" at {venue}"
    if style == "with_tickets" and event.get("external_url"):
        base += f" — [tickets]({event['external_url']})"
    if style == "bullet":
        return f"* {base}"
    return base


# ---------- Grouping helpers ----------

def group_by_week(events: list[dict]) -> list[tuple[str, list[dict]]]:
    """Return [(week_label, events), ...] in chronological order.
    Weeks are defined Monday-Sunday in ET (matches the Wilmington reader's mental model)."""
    buckets: dict[datetime, list[dict]] = {}
    for ev in events:
        dt = _parse_event_dt(ev.get("start_date"))
        if dt is None:
            continue
        local = _local(dt)
        # Monday of the event's week
        monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        buckets.setdefault(monday, []).append(ev)
    out = []
    for monday in sorted(buckets):
        sunday = monday + timedelta(days=6)
        label = f"Week of {monday.strftime('%b %d')} – {sunday.strftime('%b %d')}"
        bucket = sorted(buckets[monday], key=lambda e: _parse_event_dt(e.get("start_date")) or datetime.max.replace(tzinfo=timezone.utc))
        out.append((label, bucket))
    return out


def group_by_category(events: list[dict]) -> list[tuple[str, list[dict]]]:
    """Return [(category_label, events), ...] in a stable display order."""
    buckets: dict[str, list[dict]] = {}
    for ev in events:
        cat = (ev.get("category") or "other").lower()
        if cat not in CATEGORY_LABEL:
            cat = "other"
        buckets.setdefault(cat, []).append(ev)
    out = []
    for cat in CATEGORY_ORDER:
        if cat in buckets:
            bucket = sorted(buckets[cat], key=lambda e: _parse_event_dt(e.get("start_date")) or datetime.max.replace(tzinfo=timezone.utc))
            out.append((CATEGORY_LABEL[cat], bucket))
    return out


# ---------- Top-level style renderers ----------

def _render_section(label: str, events: list[dict], site_url: str, cap: int) -> str:
    """Render one section header + bullet list, with overflow trailer."""
    head = f"### {label}\n\n"
    shown = events[:cap]
    rest = len(events) - len(shown)
    body = "\n".join(format_event_line(ev, site_url, style="bullet") for ev in shown if format_event_line(ev, site_url, style="bullet"))
    out = head + body
    if rest > 0:
        out += f"\n\n*[+ {rest} more on LocalDrift]({site_url}/events)*"
    return out


def _header(month_key: str, site_url: str, intro: str) -> str:
    """Common top-of-post block: title, intro, link line."""
    return (
        f"# What's happening in Wilmington — {month_title(month_key)}\n\n"
        f"{intro}\n\n"
        f"All listings pulled from [LocalDrift]({site_url}) — a free local-discovery site built by a Wilmington local. Hit the link on any event for details, tickets, or directions.\n\n"
        f"---\n"
    )


def _footer(site_url: str) -> str:
    return (
        f"\n\n---\n\n"
        f"*Compiled and posted by the [LocalDrift]({site_url}) bot, with thanks to the r/Wilmington mods for the space. "
        f"Spotted an event we missed? Reply below or use the Send Feedback button on the site.*"
    )


def build_weekly(events: list[dict], month_key: str, site_url: str, cap: int = SECTION_CAP_DEFAULT) -> str:
    """Style 1: events grouped by calendar week, chronological inside each week."""
    intro = (
        "A weekly breakdown of what's coming up in town this month — concerts, sports, "
        "markets, festivals, community gatherings, and more. Organized by week so you "
        "can plan around what works."
    )
    out = _header(month_key, site_url, intro)
    groups = group_by_week(events)
    if not groups:
        out += "\n_No events listed yet for this month. Submit one through LocalDrift and it'll show up here._\n"
    else:
        out += "\n" + "\n\n".join(_render_section(label, evs, site_url, cap) for label, evs in groups)
    out += _footer(site_url)
    return out


def build_by_category(events: list[dict], month_key: str, site_url: str, cap: int = SECTION_CAP_DEFAULT) -> str:
    """Style 2: events grouped by category (concerts, sports, markets...). Each section chronological."""
    intro = (
        "Everything happening in town this month, sorted by what kind of event it is. "
        "Jump to the section that matches your mood — live music, sports, food, markets, "
        "community gatherings, or whatever else is on."
    )
    out = _header(month_key, site_url, intro)
    groups = group_by_category(events)
    if not groups:
        out += "\n_No events listed yet for this month. Submit one through LocalDrift and it'll show up here._\n"
    else:
        out += "\n" + "\n\n".join(_render_section(label, evs, site_url, cap) for label, evs in groups)
    out += _footer(site_url)
    return out


def build_chronological(events: list[dict], month_key: str, site_url: str, cap: int = 60) -> str:
    """Style 3: one long chronological list of every event in the month. No sections."""
    intro = (
        "A single chronological list of everything happening in town this month. "
        "No filters, no grouping — just date order, top to bottom. Skim it like a calendar."
    )
    out = _header(month_key, site_url, intro)
    sorted_events = sorted(
        events,
        key=lambda e: _parse_event_dt(e.get("start_date")) or datetime.max.replace(tzinfo=timezone.utc),
    )
    shown = sorted_events[:cap]
    rest = len(sorted_events) - len(shown)
    if not shown:
        out += "\n_No events listed yet for this month. Submit one through LocalDrift and it'll show up here._\n"
    else:
        out += "\n" + "\n".join(format_event_line(ev, site_url, style="bullet") for ev in shown if format_event_line(ev, site_url, style="bullet"))
        if rest > 0:
            out += f"\n\n*[+ {rest} more on LocalDrift]({site_url}/events)*"
    out += _footer(site_url)
    return out


# Map of style key -> renderer + display name (used by the admin UI).
STYLES = {
    "weekly":        {"label": "Style 1 — Weekly breakdown",   "render": build_weekly},
    "by_category":   {"label": "Style 2 — Grouped by category", "render": build_by_category},
    "chronological": {"label": "Style 3 — Single chronological list", "render": build_chronological},
}


def render(style: str, events: list[dict], month_key: str, site_url: str) -> str:
    """Dispatch to the chosen style. Raises ValueError on unknown style."""
    if style not in STYLES:
        raise ValueError(f"Unknown style {style!r}. Valid: {sorted(STYLES.keys())}")
    return STYLES[style]["render"](events, month_key, site_url)
