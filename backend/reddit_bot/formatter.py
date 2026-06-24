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
#
# This used to be 12 (sized for a single week in the weekly view). For the
# monthly category view a single category can easily have 30-40 events
# (Wilmington has a busy concert scene), so 12 was clipping more than half
# of "Concerts." 50 gives breathing room while still trapping pathological
# cases (e.g., bad data flood) before they hit Reddit's post-length limit.
SECTION_CAP_DEFAULT = 50

# Category display labels. Keys MUST match backend EventCreate.category values.
CATEGORY_LABEL = {
    "concert": "Concerts & Live Music",
    "theater": "Theater & Stage",
    "comedy": "Comedy",
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
    "concert", "theater", "comedy", "sports", "food_festival", "market",
    "community", "happy_hour", "parade", "marathon", "garage_sale", "other",
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


def format_event_line(event: dict, *, bullet: bool = True, include_tickets: bool = False) -> str:
    """One event rendered as a single markdown line.

    Option A (default): plain text — no inline link to localdrift.app.
    Reads like community content rather than an ad, and keeps the post's
    total markdown-link count low so Reddit's spam filter doesn't flag.

    Synthetic recurring events (emitted by _collapse_recurring with the
    "_is_recurring" flag) are rendered differently — one line covering
    all the dates rather than N separate lines for N repeats.

    bullet           — prefix with "* " for use inside bulleted lists
    include_tickets  — append "— [tickets](external_url)" when the event has
                       one (Ticketmaster, SeatGeek, etc.). Off-platform link,
                       so genuinely helpful for ticketed events without being
                       self-promotional for LocalDrift. Off by default — flip
                       to True if the r/Wilmington mods/community decide they
                       want direct purchase links.
    """
    title = escape_md(event.get("title") or "Untitled event")
    venue = escape_md(event.get("location_name") or event.get("city") or "")

    if event.get("_is_recurring"):
        dates = event.get("_recurring_dates") or []
        if not dates:
            return ""
        first = dates[0]
        day_name = first.strftime("%A")
        time_str = first.strftime("%I:%M %p").lstrip("0") + " ET"
        date_list = ", ".join(d.strftime("%b %d").replace(" 0", " ") for d in dates)
        line = f"**Every {day_name} ({date_list}) · {time_str}** — {title}"
        if venue:
            line += f" at {venue}"
        if include_tickets and event.get("external_url"):
            line += f" — [tickets]({event['external_url']})"
        return f"* {line}" if bullet else line

    dt = _parse_event_dt(event.get("start_date"))
    if dt is None:
        return ""
    local = _local(dt)
    when = local.strftime("%a %b %d") + " · " + local.strftime("%I:%M %p").lstrip("0") + " ET"
    line = f"**{when}** — {title}"
    if venue:
        line += f" at {venue}"
    if include_tickets and event.get("external_url"):
        line += f" — [tickets]({event['external_url']})"
    return f"* {line}" if bullet else line


def _collapse_recurring(events: list[dict]) -> list[dict]:
    """Group identical-title-and-venue events that repeat on the same
    day-of-week + same time-of-day into a single synthetic "recurring"
    event. Solves the "5 Turtle Talks back to back" wall-of-text problem
    when listing a full month.

    Detection rules:
      - same title (after stripping whitespace)
      - same location_name
      - same weekday for every occurrence
      - same hour:minute for every occurrence (within +/- 1 minute slack)

    If those all hold, the group collapses to one synthetic event with
    a "_is_recurring=True" flag and "_recurring_dates=[datetime,...]"
    attached. The renderer in format_event_line handles the synthetic
    case. Otherwise the group is returned unchanged (events that share
    a title but happen on different days stay as separate lines).

    Sort order of the output preserves chronological order based on each
    group's earliest date — keeps weekly groupings + chronological view
    sensible after collapse.
    """
    from collections import defaultdict

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for ev in events:
        key = ((ev.get("title") or "").strip(), (ev.get("location_name") or "").strip())
        groups[key].append(ev)

    out: list[dict] = []
    for (title, venue), group in groups.items():
        if len(group) < 2:
            out.extend(group)
            continue

        # Pull local datetimes for every member of the group
        local_dts = []
        for ev in group:
            dt = _parse_event_dt(ev.get("start_date"))
            if dt is None:
                local_dts = None
                break
            local_dts.append(_local(dt))
        if local_dts is None or len(local_dts) < 2:
            out.extend(group)
            continue

        first = local_dts[0]
        same_pattern = all(
            d.weekday() == first.weekday()
            and d.hour == first.hour
            and abs(d.minute - first.minute) <= 1
            for d in local_dts
        )

        if not same_pattern:
            out.extend(group)
            continue

        # Build the synthetic event. Base on the first occurrence so all
        # the venue/category/tags survive untouched; just override the
        # recurring metadata.
        sorted_dts = sorted(local_dts)
        synthetic = dict(group[0])
        synthetic["_is_recurring"] = True
        synthetic["_recurring_dates"] = sorted_dts
        # Anchor start_date to the first occurrence so any downstream
        # sort / chronological grouping uses the right anchor.
        synthetic["start_date"] = sorted_dts[0].astimezone(timezone.utc).isoformat()
        out.append(synthetic)

    # Stable chronological re-sort so collapsed entries land in the right
    # spot (anchored to first occurrence).
    out.sort(
        key=lambda e: _parse_event_dt(e.get("start_date")) or datetime.max.replace(tzinfo=timezone.utc)
    )
    return out


# ---------- Grouping helpers ----------

def group_by_week(events: list[dict]) -> list[tuple[str, list[dict]]]:
    """Return [(week_label, events), ...] in chronological order.
    Weeks are defined Monday-Sunday in ET (matches the Wilmington reader's mental model).

    Note: recurring-collapse is NOT applied at the week level — a series
    that spans multiple weeks (e.g., Turtle Talks every Monday) should
    appear once per week, not collapsed across all weeks. The chronological
    + by-category views collapse at the top level instead."""
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
    """Return [(category_label, events), ...] in a stable display order.

    Applies _collapse_recurring within each category so a weekly Turtle
    Talks series shows as one line instead of five."""
    buckets: dict[str, list[dict]] = {}
    for ev in events:
        cat = (ev.get("category") or "other").lower()
        if cat not in CATEGORY_LABEL:
            cat = "other"
        buckets.setdefault(cat, []).append(ev)
    out = []
    for cat in CATEGORY_ORDER:
        if cat in buckets:
            collapsed = _collapse_recurring(buckets[cat])
            out.append((CATEGORY_LABEL[cat], collapsed))
    return out


# ---------- Top-level style renderers ----------

def _render_section(label: str, events: list[dict], cap: int, *, include_tickets: bool) -> str:
    """Render one section header + bullet list, with overflow trailer."""
    head = f"### {label}\n\n"
    shown = events[:cap]
    rest = len(events) - len(shown)
    body = "\n".join(
        line for line in (format_event_line(ev, include_tickets=include_tickets) for ev in shown) if line
    )
    out = head + body
    if rest > 0:
        # Plain text (no markdown link) — Reddit clients autolink bare URLs,
        # but the spam filter treats this less aggressively than [...]( ... ).
        out += f"\n\n*+ {rest} more — full list at localdrift.app*"
    return out


def _header(month_key: str, intro: str) -> str:
    """Top of the post: title, intro, one brand credit line."""
    return (
        f"# What's happening in Wilmington — {month_title(month_key)}\n\n"
        f"{intro}\n\n"
        f"---\n"
    )


def _footer(site_url: str) -> str:
    """Bottom of the post. The only LocalDrift markdown link in the body —
    everything above is plain text by design (Option A)."""
    return (
        f"\n\n---\n\n"
        f"*Compiled by the [LocalDrift]({site_url}) bot with thanks to the r/Wilmington mods for the space. "
        f"Find the full list (with maps, tickets, and details) at localdrift.app. "
        f"Spotted something we missed? Reply below or use the Send Feedback button on the site.*"
    )


def build_weekly(
    events: list[dict], month_key: str, site_url: str,
    cap: int = SECTION_CAP_DEFAULT, *, include_tickets: bool = False,
) -> str:
    """Style 1: events grouped by calendar week, chronological inside each week."""
    intro = (
        "A weekly breakdown of what's coming up in town this month — concerts, sports, "
        "markets, festivals, community gatherings, and more. Organized by week so you "
        "can plan around what works."
    )
    out = _header(month_key, intro)
    groups = group_by_week(events)
    if not groups:
        out += "\n_No events listed yet for this month. Submit one at localdrift.app and it'll show up here._\n"
    else:
        out += "\n" + "\n\n".join(
            _render_section(label, evs, cap, include_tickets=include_tickets)
            for label, evs in groups
        )
    out += _footer(site_url)
    return out


def build_by_category(
    events: list[dict], month_key: str, site_url: str,
    cap: int = SECTION_CAP_DEFAULT, *, include_tickets: bool = False,
) -> str:
    """Style 2: events grouped by category (concerts, sports, markets...). Each section chronological."""
    intro = (
        "Everything happening in town this month, sorted by what kind of event it is. "
        "Jump to the section that matches your mood — live music, sports, food, markets, "
        "community gatherings, or whatever else is on."
    )
    out = _header(month_key, intro)
    groups = group_by_category(events)
    if not groups:
        out += "\n_No events listed yet for this month. Submit one at localdrift.app and it'll show up here._\n"
    else:
        out += "\n" + "\n\n".join(
            _render_section(label, evs, cap, include_tickets=include_tickets)
            for label, evs in groups
        )
    out += _footer(site_url)
    return out


def build_chronological(
    events: list[dict], month_key: str, site_url: str,
    cap: int = 100, *, include_tickets: bool = False,
) -> str:
    """Style 3: one long chronological list of every event in the month. No sections."""
    intro = (
        "A single chronological list of everything happening in town this month. "
        "No filters, no grouping — just date order, top to bottom. Skim it like a calendar."
    )
    out = _header(month_key, intro)
    collapsed = _collapse_recurring(events)
    sorted_events = sorted(
        collapsed,
        key=lambda e: _parse_event_dt(e.get("start_date")) or datetime.max.replace(tzinfo=timezone.utc),
    )
    shown = sorted_events[:cap]
    rest = len(sorted_events) - len(shown)
    if not shown:
        out += "\n_No events listed yet for this month. Submit one at localdrift.app and it'll show up here._\n"
    else:
        out += "\n" + "\n".join(
            line for line in (format_event_line(ev, include_tickets=include_tickets) for ev in shown) if line
        )
        if rest > 0:
            out += f"\n\n*+ {rest} more — full list at localdrift.app*"
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
