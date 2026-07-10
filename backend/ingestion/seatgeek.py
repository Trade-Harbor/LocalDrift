"""SeatGeek API ingester.

Docs: https://platform.seatgeek.com/
Free tier exists with no published hard cap. Get a client_id at
https://seatgeek.com/account/develop (instant signup).
Set env var: SEATGEEK_CLIENT_ID
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

API_BASE = "https://api.seatgeek.com/2/events"


async def fetch_events() -> List[Dict[str, Any]]:
    """Fetch upcoming SeatGeek events near the pilot region."""
    client_id = os.environ.get("SEATGEEK_CLIENT_ID")
    if not client_id:
        log.warning("SEATGEEK_CLIENT_ID not set; skipping SeatGeek ingestion")
        return []

    params = {
        "client_id": client_id,
        "lat": PILOT_LAT,
        "lon": PILOT_LON,
        "range": f"{int(PILOT_RADIUS_MILES)}mi",
        "per_page": 200,
        "sort": "datetime_local.asc",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(API_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as e:
        log.error(f"SeatGeek API error: {e}")
        return []

    raw_events = data.get("events", [])
    log.info(f"SeatGeek returned {len(raw_events)} raw events")

    normalized: List[Dict[str, Any]] = []
    for raw in raw_events:
        e = _normalize_event(raw)
        if e:
            normalized.append(e)

    log.info(f"SeatGeek normalized {len(normalized)} events")
    return normalized


def _normalize_event(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    title = raw.get("title")
    if not title:
        return None

    start_dt = parse_iso_safe(raw.get("datetime_utc")) or parse_iso_safe(raw.get("datetime_local"))
    if not start_dt:
        return None

    venue = raw.get("venue") or {}
    location = venue.get("location") or {}
    try:
        lat = float(location.get("lat")) if location.get("lat") else None
        lon = float(location.get("lon")) if location.get("lon") else None
    except (TypeError, ValueError):
        lat, lon = None, None
    if lat is None or lon is None:
        return None

    # Sanity check: reject events whose venue state doesn't match the
    # pilot region even if lat/lon fell inside the radius. Prevents
    # out-of-state events with bad geocoding (e.g. an NY venue mistakenly
    # returned with NC coordinates) from leaking into the local feed.
    state = venue.get("state") or ""
    if state and state.upper() != PILOT_STATE.upper():
        log.info(
            "SeatGeek: rejecting out-of-state event title=%r state=%s "
            "(lat/lon inside pilot radius but venue state mismatches PILOT_STATE=%s)",
            title, state, PILOT_STATE,
        )
        return None

    # Pricing — SeatGeek events are ticketed; mark is_paid=True even when the
    # lowest price isn't reported by the API (often happens for popular events).
    stats = raw.get("stats") or {}
    lowest = stats.get("lowest_price")
    is_paid = True
    ticket_price = float(lowest) if lowest is not None else None

    # Category from `type` field (e.g. "concert", "sports", "theater")
    seg = raw.get("type", "") + " " + " ".join(t.get("name", "") for t in raw.get("taxonomies", []))
    category = map_category_from_text(seg)

    # Image from first performer
    image_url = None
    for performer in raw.get("performers", []):
        if performer.get("image"):
            image_url = performer["image"]
            break

    return {
        "title": title,
        "description": raw.get("short_title") or title,
        "category": category,
        "start_date": to_iso(start_dt),
        "end_date": None,
        "location_name": venue.get("name") or "",
        "address": venue.get("address") or "",
        "city": venue.get("city") or "",
        "state": venue.get("state") or "",
        "zip_code": venue.get("postal_code") or "",
        "latitude": lat,
        "longitude": lon,
        "image_url": image_url,
        "is_paid": is_paid,
        "ticket_price": ticket_price,
        "discount_percentage": None,
        "total_tickets": None,
        "is_promoted": False,
        "tags": [],
        "mood_tags": [],
        "external_url": raw.get("url"),
        "_source": "seatgeek",
        "_source_id": str(raw.get("id")),
        "_source_url": raw.get("url"),
    }
