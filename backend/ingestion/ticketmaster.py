"""Ticketmaster Discovery API ingester.

Docs: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
Free tier: 5,000 calls/day. Get a key at https://developer.ticketmaster.com (instant signup).
Set env var: TICKETMASTER_API_KEY
"""
import logging
import os
from typing import List, Dict, Any, Optional

import httpx

from .utils import (
    PILOT_LAT,
    PILOT_LON,
    PILOT_RADIUS_MILES,
    PILOT_STATE,
    parse_iso_safe,
    to_iso,
    map_category_from_text,
)

log = logging.getLogger(__name__)

API_BASE = "https://app.ticketmaster.com/discovery/v2/events.json"


async def fetch_events() -> List[Dict[str, Any]]:
    """Fetch upcoming events near the pilot region. Returns list of LocalDrift-shape event docs.

    Empty list (with a warning log) if the API key is missing — keeps ingestion runs resilient.
    """
    api_key = os.environ.get("TICKETMASTER_API_KEY")
    if not api_key:
        log.warning("TICKETMASTER_API_KEY not set; skipping Ticketmaster ingestion")
        return []

    params = {
        "apikey": api_key,
        "latlong": f"{PILOT_LAT},{PILOT_LON}",
        "radius": int(PILOT_RADIUS_MILES),
        "unit": "miles",
        "size": 200,
        "sort": "date,asc",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error(f"Ticketmaster API error: {e}")
        return []

    events_raw = (data.get("_embedded") or {}).get("events", [])
    log.info(f"Ticketmaster returned {len(events_raw)} raw events")

    normalized: List[Dict[str, Any]] = []
    for raw in events_raw:
        normalized_event = _normalize_event(raw)
        if normalized_event:
            normalized.append(normalized_event)

    log.info(f"Ticketmaster normalized {len(normalized)} events")
    return normalized


def _normalize_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert one Ticketmaster event to LocalDrift's event document shape."""
    title = raw.get("name")
    if not title:
        return None

    # Date
    dates = raw.get("dates") or {}
    start_obj = (dates.get("start") or {})
    start_dt = parse_iso_safe(start_obj.get("dateTime")) or parse_iso_safe(start_obj.get("localDate"))
    if not start_dt:
        return None

    # Venue
    venues = (raw.get("_embedded") or {}).get("venues") or []
    if not venues:
        return None
    venue = venues[0]
    location = venue.get("location") or {}
    address = (venue.get("address") or {}).get("line1") or ""
    city = (venue.get("city") or {}).get("name") or ""
    state = (venue.get("state") or {}).get("stateCode") or ""
    zip_code = venue.get("postalCode") or ""

    try:
        lat = float(location.get("latitude")) if location.get("latitude") else None
        lon = float(location.get("longitude")) if location.get("longitude") else None
    except (TypeError, ValueError):
        lat, lon = None, None
    if lat is None or lon is None:
        return None

    # Sanity check against TM's internally-inconsistent geocoding.
    # Real-world case: TM listed an "Outdoors on Chippewa" event with
    # city=Buffalo/state=NY/zip=14202 but lat+lon pointing at Wilmington NC.
    # The geo radius search returned it, and the event showed up as local.
    # Reject anything whose state field disagrees with the pilot region.
    # Empty state = don't reject (some venues genuinely omit it and are
    # already inside the radius, we trust the lat/lon).
    if state and state.upper() != PILOT_STATE.upper():
        log.info(
            "Ticketmaster: rejecting out-of-state event title=%r state=%s "
            "(lat/lon inside pilot radius but venue state mismatches PILOT_STATE=%s)",
            title, state, PILOT_STATE,
        )
        return None

    # Image: pick the largest 16:9 image if available, else first
    images = raw.get("images") or []
    image_url = None
    if images:
        ratio_16_9 = [im for im in images if im.get("ratio") == "16_9"]
        candidates = ratio_16_9 or images
        candidates.sort(key=lambda im: im.get("width", 0), reverse=True)
        image_url = candidates[0].get("url")

    # Pricing — Ticketmaster events are ALWAYS ticketed (they're a ticketing
    # platform). priceRanges may not be returned in the public API even when
    # tickets are paid, so we mark is_paid=True unconditionally and surface
    # the price only when the API gave us one.
    price_ranges = raw.get("priceRanges") or []
    is_paid = True
    ticket_price = float(price_ranges[0]["min"]) if price_ranges and price_ranges[0].get("min") is not None else None

    # Category from classifications
    classifications = raw.get("classifications") or []
    seg_name = ""
    if classifications:
        c = classifications[0]
        seg_name = (
            (c.get("segment") or {}).get("name", "") + " "
            + (c.get("genre") or {}).get("name", "") + " "
            + (c.get("subGenre") or {}).get("name", "")
        )
    category = map_category_from_text(seg_name)

    return {
        "title": title,
        "description": raw.get("info") or raw.get("pleaseNote") or title,
        "category": category,
        "start_date": to_iso(start_dt),
        "end_date": None,
        "location_name": venue.get("name") or "",
        "address": address,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "latitude": lat,
        "longitude": lon,
        "image_url": image_url,
        "is_paid": is_paid,
        "ticket_price": ticket_price,
        "discount_percentage": None,
        "total_tickets": None,
        "is_promoted": False,
        "tags": [t.lower() for t in (raw.get("info", "").split()[:5] if raw.get("info") else [])],
        "mood_tags": [],
        # Source tracking — `external_url` is also exposed at the top level
        # so the frontend can link out to the original ticketing page instead
        # of trying to run an internal Stripe checkout for an event we don't
        # actually sell tickets for.
        "external_url": raw.get("url"),
        "_source": "ticketmaster",
        "_source_id": raw.get("id"),
        "_source_url": raw.get("url"),
    }
