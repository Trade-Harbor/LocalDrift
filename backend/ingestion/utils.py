"""Shared helpers for the ingestion pipeline.

The pilot region is Wilmington, NC. Override via env vars in production.
"""
import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Optional


# === Pilot region: Wilmington, NC ===
# Lat/Lon center plus a 30-mile radius covers Wilmington, Wrightsville Beach,
# Carolina Beach, Kure Beach, Leland, and Hampstead.
PILOT_LAT = float(os.environ.get("PILOT_LAT", "34.2257"))
PILOT_LON = float(os.environ.get("PILOT_LON", "-77.9447"))
PILOT_RADIUS_MILES = float(os.environ.get("PILOT_RADIUS_MILES", "30"))
PILOT_CITY = os.environ.get("PILOT_CITY", "Wilmington")
PILOT_STATE = os.environ.get("PILOT_STATE", "NC")


def event_dedup_key(title: str, start_date: str, location_name: str) -> str:
    """Stable hash for cross-source event dedup based on TITLE + hour.

    Catches concerts where the title differs slightly across sources:
      'Waylon Wyatt - Everywhere Under The Sun' (Ticketmaster)
      'Waylon Wyatt' (SeatGeek)
    Both reduce to 'waylon wyatt' (first 2 normalized tokens).

    But it MISSES sports events because home/away framing flips the title:
      'UNC Wilmington Seahawks vs High Point Panthers'  (TM)
      'High Point Panthers at UNC Wilmington Seahawks'  (SG)
    For those we use `event_location_dedup_key` below as a second pass.
    """
    title_tokens = _normalize(title).split()[:2]
    title_part = " ".join(title_tokens)
    date_part = (start_date or "")[:13]   # YYYY-MM-DDTHH (hour precision)
    normalized = f"{title_part}|{date_part}"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def event_title_set_dedup_key(title: str, start_date: str) -> str:
    """Tertiary dedup key based on a content-tokens SET + day.

    Catches sports games where titles are entirely different word orders:
      'UNC Wilmington Seahawks Baseball vs. High Point Panthers Baseball'
      'High Point Panthers at UNC Wilmington Seahawks Baseball'
    Token-set is identical: {baseball, high, panthers, point, seahawks,
    unc, wilmington} → same key regardless of word order.

    Day-precision (not hour) because the title-set already provides strong
    constraint, and TM/SG occasionally disagree about the exact start time
    by an hour for the same game.

    Stopwords (vs, at, the, etc.) are stripped so that 'A vs B' and 'B at A'
    produce the same set.
    """
    if not title:
        return ""
    tokens = set(_normalize(title).split())
    stopwords = {"vs", "v", "at", "the", "a", "and", "an", "of", "in",
                 "on", "to", "for", "with", "&"}
    tokens -= stopwords
    if not tokens:
        return ""
    # Sort for determinism so the same set always hashes the same
    title_part = "|".join(sorted(tokens))
    date_part = (start_date or "")[:10]   # YYYY-MM-DD (day precision)
    normalized = f"{title_part}|{date_part}"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def event_location_dedup_key(latitude: float, longitude: float, start_date: str) -> str:
    """Secondary dedup key based on geographic coordinates + start hour.

    Same venue at the same hour is overwhelmingly the same event regardless
    of how the title is worded. Catches sports games whose titles are flipped
    home/away across sources.

    Lat/lon rounded to 2 decimals (~1.1km precision). Originally tried 3
    decimals (~110m) but cross-source coordinates drift more than that —
    Ticketmaster's geocoder may put a venue at 34.2235 while SeatGeek's
    has it at 34.2244, which round to different values at 3 decimals
    (34.224 vs 34.224... wait those are the same — but values like 34.2244
    vs 34.2255 round to 34.224 vs 34.226 at 3 decimals → MISS).
    2 decimals is forgiving enough; venues a kilometer apart still distinct.

    Trade-off: events at two different venues within ~1km of each other
    happening at the same hour would falsely merge. Rare enough we accept it.
    """
    if latitude is None or longitude is None:
        return ""  # Can't dedupe by location if we don't have coords
    lat_part = f"{round(float(latitude), 2)}"
    lon_part = f"{round(float(longitude), 2)}"
    date_part = (start_date or "")[:13]
    normalized = f"{lat_part}|{lon_part}|{date_part}"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def business_dedup_key(name: str, address: str) -> str:
    """Stable hash for restaurant/business dedup."""
    normalized = f"{_normalize(name)}|{_normalize(address)}"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    # Lowercase, strip punctuation/extra whitespace, collapse spaces
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def to_iso(dt: datetime) -> str:
    """Mongo-friendly ISO string in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def parse_iso_safe(s: Optional[str]) -> Optional[datetime]:
    """Parse a variety of ISO datetime strings; return None on failure."""
    if not s:
        return None
    try:
        # Handle trailing Z (Zulu / UTC)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def map_category_from_text(text: str) -> str:
    """Best-effort mapping from external category strings to LocalDrift categories.

    Order matters: theater + comedy are checked BEFORE music/concert because
    Ticketmaster classifies a Broadway show as "Arts & Theatre Theatre Musical"
    — the substring "music" inside "musical" used to false-match into concert.
    Same for stand-up: TM ships it as "Arts & Theatre Comedy".
    """
    if not text:
        return "other"
    t = text.lower()

    # Comedy FIRST — TM ships stand-up as "Arts & Theatre Comedy", so we
    # have to catch "comedy" before "theatre" or every comedy show ends up
    # tagged as theater
    if any(k in t for k in [
        "comedy", "comedian", "stand-up", "standup",
        "dead crow",  # the Wilmington comedy venue
    ]):
        return "comedy"

    # Theater next — before music, because "music" matches "musical".
    # CAREFUL: "theater"/"theatre" appears in "amphitheater" too, which is a
    # concert venue, not a theater. Exclude that explicitly. Same kind of
    # false-positive shielding goes for any compound word containing the
    # token.
    is_amphitheater = "amphitheater" in t or "amphitheatre" in t
    theater_words = [
        "theatre", "theater", "musical", "broadway", "opera", "ballet",
        "playhouse", "stage show", "the play",
        "thalian hall",  # Wilmington's flagship theater venue
    ]
    if not is_amphitheater and any(k in t for k in theater_words):
        return "theater"

    # Sports (note: "race" intentionally removed here to avoid false matches)
    if any(k in t for k in [
        "sport", "football", "basketball", "baseball", "hockey", "soccer",
        "nba", "nfl", "mlb", "nhl", "wrestling", "boxing", "ufc",
        "tennis", "golf", "lacrosse", "volleyball", "rugby", "cycling",
    ]):
        if "marathon" in t or "5k" in t or "10k" in t:
            return "marathon"
        return "sports"

    # Marathons / road races
    if "marathon" in t or "5k" in t or "10k" in t or " race" in t or "road race" in t:
        return "marathon"

    # Music / concert
    if any(k in t for k in ["concert", "music", "band", "dj"]):
        if "food" in t:
            return "food_festival"
        return "concert"

    if "parade" in t:
        return "parade"
    if "festival" in t:
        if "food" in t or "wine" in t or "beer" in t:
            return "food_festival"
        return "concert"  # most non-food festivals are music-driven
    if "market" in t or " fair" in t or "bazaar" in t:
        return "market"
    if "happy hour" in t:
        return "happy_hour"
    if "garage" in t or "yard sale" in t:
        return "garage_sale"
    if "food" in t or "wine" in t or "beer" in t or "tasting" in t:
        return "food_festival"
    if "show" in t or "performance" in t:
        return "concert"  # generic fallback for live performance
    return "other"
