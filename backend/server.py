from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
import asyncio
import email_helper as _email_helper
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import bcrypt
import jwt
import httpx
from math import radians, sin, cos, sqrt, atan2

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'default_secret')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 168  # 7 days

# Commission rate for ticket sales
COMMISSION_RATE = float(os.environ.get('COMMISSION_RATE', '0.05'))

# Beta-mode toggle. While True, all payment-related endpoints return 503
# with a clear "beta" message so accidental traffic can't create real
# Stripe charges or subscriptions. Flip to "false" in Render when ready
# to accept payments.
BETA_PAYMENTS_DISABLED = os.environ.get("BETA_PAYMENTS_DISABLED", "true").lower() == "true"
BETA_DISABLED_MESSAGE = (
    "Payments are disabled during the LocalDrift beta. We're collecting "
    "feedback first — monetization features will return after beta. "
    "Email hello@localdrift.app if you'd like to participate in a "
    "monetization preview as a business partner."
)


def _enforce_beta_block():
    """Raise 503 if payments are beta-disabled. Use as a guard at the top of
    any endpoint that would otherwise initiate a Stripe checkout."""
    if BETA_PAYMENTS_DISABLED:
        raise HTTPException(status_code=503, detail=BETA_DISABLED_MESSAGE)

# Create the main app
app = FastAPI(title="LocalDrift API")

# Create routers
api_router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/api/auth")
events_router = APIRouter(prefix="/api/events")
foodtrucks_router = APIRouter(prefix="/api/foodtrucks")
payments_router = APIRouter(prefix="/api/payments")
ai_router = APIRouter(prefix="/api/ai")
flash_deals_router = APIRouter(prefix="/api/flash-deals")

security = HTTPBearer(auto_error=False)

# ============= MODELS =============

class UserBase(BaseModel):
    email: EmailStr
    name: str
    
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str
    account_type: str = "personal"  # personal or business
    business_name: Optional[str] = None
    phone: Optional[str] = None
    zip_code: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    account_type: str
    business_name: Optional[str] = None
    zip_code: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class EventCategory(BaseModel):
    name: str
    icon: str

class EventCreate(BaseModel):
    title: str
    description: str
    category: str  # concert, parade, marathon, market, happy_hour, garage_sale, food_festival, other
    start_date: datetime
    end_date: Optional[datetime] = None
    location_name: str
    address: str
    city: str
    state: str
    zip_code: str
    latitude: float
    longitude: float
    image_url: Optional[str] = None
    is_paid: bool = False
    ticket_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    total_tickets: Optional[int] = None
    is_promoted: bool = False
    tags: List[str] = []
    mood_tags: List[str] = []  # family_friendly, dog_friendly, outdoor, indoor, free_parking, accessible

class EventResponse(BaseModel):
    event_id: str
    title: str
    description: str
    category: str
    start_date: datetime
    end_date: Optional[datetime] = None
    location_name: str
    address: str
    city: str
    state: str
    zip_code: str
    latitude: float
    longitude: float
    image_url: Optional[str] = None
    is_paid: bool = False
    ticket_price: Optional[float] = None
    discount_percentage: Optional[float] = None
    discounted_price: Optional[float] = None
    total_tickets: Optional[int] = None
    tickets_sold: int = 0
    is_promoted: bool = False
    promotion_expires: Optional[datetime] = None
    tags: List[str] = []
    mood_tags: List[str] = []
    organizer_id: str
    organizer_name: str
    organizer_type: str
    created_at: datetime
    distance: Optional[float] = None
    # External ticketing URL (set when the event was ingested from Ticketmaster,
    # SeatGeek, etc.) — the frontend uses this to link out for ticket purchase
    # instead of running its own Stripe checkout for an event we don't control.
    external_url: Optional[str] = None
    source: Optional[str] = None  # "ticketmaster", "seatgeek", or None for user-submitted

class FoodTruckCreate(BaseModel):
    name: str
    description: str
    cuisine_type: str
    latitude: float
    longitude: float
    address: str
    city: str
    state: str
    zip_code: str
    operating_hours: str
    image_url: Optional[str] = None
    menu_highlights: List[str] = []

class FoodTruckResponse(BaseModel):
    truck_id: str
    name: str
    description: str
    cuisine_type: str
    latitude: float
    longitude: float
    address: str
    city: str
    state: str
    zip_code: str
    operating_hours: str
    image_url: Optional[str] = None
    menu_highlights: List[str] = []
    owner_id: str
    owner_name: str
    rating: float = 0.0
    review_count: int = 0
    is_active_today: bool = True
    last_updated: datetime
    distance: Optional[float] = None

class CommentCreate(BaseModel):
    content: str
    rating: Optional[int] = None  # 1-5 stars

class CommentResponse(BaseModel):
    comment_id: str
    content: str
    rating: Optional[int] = None
    user_id: str
    user_name: str
    user_picture: Optional[str] = None
    target_type: str  # event or foodtruck
    target_id: str
    created_at: datetime

class TicketPurchase(BaseModel):
    event_id: str
    quantity: int = 1
    payment_method: str = "stripe"  # stripe or paypal

class TicketResponse(BaseModel):
    ticket_id: str
    event_id: str
    event_title: str
    user_id: str
    quantity: int
    unit_price: float
    total_price: float
    commission: float
    payment_status: str
    payment_method: str
    created_at: datetime

class PromotionCreate(BaseModel):
    event_id: str
    duration_days: int = 7  # promotion duration
    
class PromotionPackage(BaseModel):
    package_id: str
    name: str
    duration_days: int
    price: float
    description: str

class FlashDealCreate(BaseModel):
    event_id: str
    discount_percentage: float  # 0-100
    deal_price: float
    spots_total: Optional[int] = None  # None = unlimited
    end_time: datetime
    description: Optional[str] = None

class FlashDealResponse(BaseModel):
    deal_id: str
    event_id: str
    event_title: str
    event_image: Optional[str] = None
    event_date: datetime
    location_name: str
    city: str
    description: Optional[str] = None
    discount_percentage: float
    deal_price: float
    original_price: float
    business_name: str
    spots_total: Optional[int] = None
    spots_claimed: int = 0
    spots_left: Optional[int] = None
    end_time: datetime
    time_left_seconds: int
    created_at: datetime

# ============= HELPER FUNCTIONS =============

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(request: Request, credentials = Depends(security)):
    # Check cookie first
    session_token = request.cookies.get("session_token")
    if session_token:
        session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
        if session:
            expires_at = session.get("expires_at")
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > datetime.now(timezone.utc):
                user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0})
                if user:
                    return user
    
    # Check Bearer token
    if credentials:
        token = credentials.credentials
        payload = decode_token(token)
        user = await db.users.find_one({"user_id": payload["user_id"]}, {"_id": 0})
        if user:
            return user
    
    raise HTTPException(status_code=401, detail="Not authenticated")

async def get_optional_user(request: Request, credentials = Depends(security)):
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in miles between two coordinates using Haversine formula"""
    R = 3959  # Earth's radius in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

# ============= AUTH ROUTES =============

@auth_router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    # Check if user exists
    existing = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    hashed_pw = hash_password(user_data.password)
    
    user_doc = {
        "user_id": user_id,
        "email": user_data.email,
        "password": hashed_pw,
        "name": user_data.name,
        "account_type": user_data.account_type,
        "business_name": user_data.business_name,
        "phone": user_data.phone,
        "zip_code": user_data.zip_code,
        "profile_picture": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.insert_one(user_doc)
    
    token = create_token(user_id, user_data.email)
    
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            user_id=user_id,
            email=user_data.email,
            name=user_data.name,
            account_type=user_data.account_type,
            business_name=user_data.business_name,
            zip_code=user_data.zip_code,
            profile_picture=None,
            created_at=datetime.now(timezone.utc)
        )
    )

@auth_router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["user_id"], user["email"])
    
    created_at = user.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            user_id=user["user_id"],
            email=user["email"],
            name=user["name"],
            account_type=user.get("account_type", "personal"),
            business_name=user.get("business_name"),
            zip_code=user.get("zip_code"),
            profile_picture=user.get("profile_picture"),
            created_at=created_at
        )
    )

# Emergent OAuth session endpoint removed. To re-add Google login, integrate
# Google Identity Services directly with `google-auth` library here.

@auth_router.get("/me", response_model=UserResponse)
async def get_me(user = Depends(get_current_user)):
    created_at = user.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    
    return UserResponse(
        user_id=user["user_id"],
        email=user["email"],
        name=user["name"],
        account_type=user.get("account_type", "personal"),
        business_name=user.get("business_name"),
        zip_code=user.get("zip_code"),
        profile_picture=user.get("profile_picture"),
        created_at=created_at
    )

@auth_router.post("/logout")
async def logout(request: Request, response_obj = None):
    session_token = request.cookies.get("session_token")
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    return {"message": "Logged out"}


# ============= PASSWORD RESET =============
# Standard email-based recovery. Flow:
#   1. POST /api/auth/forgot-password { email } -> always returns success
#      (don't leak which emails are registered). If the email exists, an
#      email with a reset link is sent.
#   2. User clicks the link, which lands on /reset-password?token=...
#      The token is opaque (UUID), single-use, expires after 1 hour.
#   3. POST /api/auth/reset-password { token, new_password } -> updates
#      the user's password hash and consumes the token.

_RESET_TTL_HOURS = 1


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@auth_router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordRequest, request: Request):
    """Initiate password reset. Always returns 200 with a generic
    message regardless of whether the email is registered — avoids
    leaking the user list."""
    email = (data.email or "").strip().lower()
    response_payload = {
        "status": "ok",
        "message": "If an account exists for that email, you'll receive a reset link shortly.",
    }
    if not email:
        return response_payload

    user = await db.users.find_one({"email": email}, {"_id": 0, "user_id": 1, "name": 1, "email": 1})
    if not user:
        return response_payload

    # Generate single-use reset token. We store the raw token; hashing it
    # would be more defensive but the trade-off isn't worth it at this
    # scale (tokens are single-use + short-lived).
    reset_token = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=_RESET_TTL_HOURS)

    # Invalidate any pending tokens for this user so old links from a
    # previous request stop working as soon as a new one is issued.
    await db.password_resets.delete_many({"user_id": user["user_id"], "used_at": None})

    await db.password_resets.insert_one({
        "reset_id": f"rst_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "email": email,
        "token": reset_token,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "used_at": None,
        "ip": request.client.host if request.client else None,
    })

    site_url = os.environ.get("PUBLIC_FRONTEND_URL", "https://www.localdrift.app").rstrip("/")
    reset_link = f"{site_url}/reset-password?token={reset_token}"
    name = user.get("name") or "there"

    html = f"""<!doctype html>
<html><body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f3f4f6;padding:24px;">
  <div style="max-width:520px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;">
    <div style="background:#1e6b6b;padding:24px;color:#fff;">
      <div style="font-size:22px;font-weight:700;">Reset your password</div>
    </div>
    <div style="padding:24px;color:#111827;line-height:1.55;">
      <p>Hi {escape_html(name)},</p>
      <p>We got a request to reset your LocalDrift password. Click the button below to choose a new one. This link expires in {_RESET_TTL_HOURS} hour.</p>
      <p style="text-align:center;margin:24px 0;">
        <a href="{reset_link}" style="background:#1e6b6b;color:#fff;text-decoration:none;padding:12px 24px;border-radius:9999px;font-weight:600;display:inline-block;">Reset password</a>
      </p>
      <p style="font-size:13px;color:#6b7280;">If the button doesn't work, copy this link into your browser:<br>
        <span style="word-break:break-all;">{reset_link}</span>
      </p>
      <p style="font-size:13px;color:#6b7280;margin-top:24px;">
        If you didn't request a password reset, you can safely ignore this email.
      </p>
    </div>
  </div>
</body></html>"""

    text = f"Reset your LocalDrift password by visiting: {reset_link}\n\nThis link expires in {_RESET_TTL_HOURS} hour. If you didn't request a reset, ignore this email."

    import email_helper as _eh
    _eh.send_email(email, "Reset your LocalDrift password", html, text_fallback=text)

    return response_payload


@auth_router.post("/reset-password")
async def reset_password(data: ResetPasswordRequest):
    """Consume a reset token and set the new password. Tokens are
    single-use and time-limited."""
    if not data.token or not data.new_password:
        raise HTTPException(status_code=400, detail="Token and new password required")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    reset_doc = await db.password_resets.find_one({"token": data.token, "used_at": None}, {"_id": 0})
    if not reset_doc:
        raise HTTPException(status_code=400, detail="Invalid or already-used reset link")

    expires_at = reset_doc.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")

    new_hash = hash_password(data.new_password)
    await db.users.update_one(
        {"user_id": reset_doc["user_id"]},
        {"$set": {"password": new_hash, "password_updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    await db.password_resets.update_one(
        {"token": data.token},
        {"$set": {"used_at": datetime.now(timezone.utc).isoformat()}},
    )
    # Invalidate any other active sessions for this user — forces a
    # re-login on all devices, which is what users expect after a reset.
    await db.user_sessions.delete_many({"user_id": reset_doc["user_id"]})

    return {"status": "ok", "message": "Password reset successfully. You can sign in now."}


def escape_html(s: str) -> str:
    """Minimal HTML-escape for values embedded in the reset email."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ============= EVENT ROUTES =============

EVENT_CATEGORIES = [
    {"name": "concert", "label": "Concerts", "icon": "Music"},
    {"name": "parade", "label": "Parades", "icon": "Flag"},
    {"name": "marathon", "label": "Marathons", "icon": "Timer"},
    {"name": "market", "label": "Markets", "icon": "ShoppingBag"},
    {"name": "happy_hour", "label": "Happy Hours", "icon": "Wine"},
    {"name": "garage_sale", "label": "Garage Sales", "icon": "Tag"},
    {"name": "food_festival", "label": "Food Festivals", "icon": "UtensilsCrossed"},
    {"name": "community", "label": "Community Events", "icon": "Users"},
    {"name": "sports", "label": "Sports", "icon": "Trophy"},
    {"name": "other", "label": "Other", "icon": "Calendar"},
]

@events_router.get("/categories")
async def get_categories():
    return EVENT_CATEGORIES

@events_router.post("", response_model=EventResponse)
async def create_event(event_data: EventCreate, user = Depends(get_current_user)):
    event_id = f"event_{uuid.uuid4().hex[:12]}"
    
    discounted_price = None
    if event_data.is_paid and event_data.ticket_price and event_data.discount_percentage:
        discounted_price = round(event_data.ticket_price * (1 - event_data.discount_percentage / 100), 2)
    
    event_doc = {
        "event_id": event_id,
        "title": event_data.title,
        "description": event_data.description,
        "category": event_data.category,
        "start_date": event_data.start_date.isoformat(),
        "end_date": event_data.end_date.isoformat() if event_data.end_date else None,
        "location_name": event_data.location_name,
        "address": event_data.address,
        "city": event_data.city,
        "state": event_data.state,
        "zip_code": event_data.zip_code,
        "latitude": event_data.latitude,
        "longitude": event_data.longitude,
        "image_url": event_data.image_url,
        "is_paid": event_data.is_paid,
        "ticket_price": event_data.ticket_price,
        "discount_percentage": event_data.discount_percentage,
        "discounted_price": discounted_price,
        "total_tickets": event_data.total_tickets,
        "tickets_sold": 0,
        "is_promoted": event_data.is_promoted,
        "promotion_expires": None,
        "tags": event_data.tags,
        "mood_tags": event_data.mood_tags,
        "organizer_id": user["user_id"],
        "organizer_name": user.get("business_name") or user["name"],
        "organizer_type": user.get("account_type", "personal"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.events.insert_one(event_doc)
    
    return EventResponse(**{
        **event_doc,
        "start_date": event_data.start_date,
        "end_date": event_data.end_date,
        "created_at": datetime.now(timezone.utc)
    })

@events_router.get("", response_model=List[EventResponse])
async def get_events(
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    radius: float = Query(25, description="Radius in miles"),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    is_free: Optional[bool] = Query(None),
    mood: Optional[str] = Query(None),  # family_friendly, dog_friendly, outdoor, etc.
    promoted_only: bool = Query(False),
    limit: int = Query(50),
    offset: int = Query(0)
):
    query = {}
    
    # Filter by category
    if category:
        query["category"] = category
    
    # Filter by mood tags
    if mood:
        query["mood_tags"] = {"$in": [mood]}
    
    # Filter by search term
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"tags": {"$in": [search.lower()]}}
        ]
    
    # Filter by date range
    if start_date:
        query["start_date"] = {"$gte": start_date}
    if end_date:
        if "start_date" in query:
            query["start_date"]["$lte"] = end_date
        else:
            query["start_date"] = {"$lte": end_date}
    
    # Filter by price
    if is_free is not None:
        query["is_paid"] = not is_free
    
    # Filter promoted events
    if promoted_only:
        query["is_promoted"] = True
        query["$or"] = query.get("$or", []) + [
            {"promotion_expires": {"$gt": datetime.now(timezone.utc).isoformat()}},
            {"promotion_expires": None, "is_promoted": True}
        ]
    
    # Only show upcoming or ongoing events
    query["start_date"] = {"$gte": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()}

    # Hide auto-moderated events (flagged by N distinct users until admin review)
    query["is_hidden"] = {"$ne": True}

    cursor = db.events.find(query, {"_id": 0})
    events = await cursor.to_list(1000)
    
    # Calculate distance and filter by radius if coordinates provided
    results = []
    for event in events:
        event_copy = dict(event)
        
        # Parse dates
        if isinstance(event_copy["start_date"], str):
            event_copy["start_date"] = datetime.fromisoformat(event_copy["start_date"])
        if event_copy.get("end_date") and isinstance(event_copy["end_date"], str):
            event_copy["end_date"] = datetime.fromisoformat(event_copy["end_date"])
        if isinstance(event_copy["created_at"], str):
            event_copy["created_at"] = datetime.fromisoformat(event_copy["created_at"])
        if event_copy.get("promotion_expires") and isinstance(event_copy["promotion_expires"], str):
            event_copy["promotion_expires"] = datetime.fromisoformat(event_copy["promotion_expires"])
        
        if latitude and longitude:
            distance = calculate_distance(
                latitude, longitude,
                event["latitude"], event["longitude"]
            )
            if distance <= radius:
                event_copy["distance"] = round(distance, 1)
                results.append(event_copy)
        else:
            results.append(event_copy)
    
    # Sort: promoted first, then by start date
    results.sort(key=lambda x: (not x.get("is_promoted", False), x["start_date"]))
    
    # Apply pagination
    paginated = results[offset:offset + limit]
    
    return [EventResponse(**e) for e in paginated]

@events_router.get("/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: str,
    request: Request,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
):
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # Hide auto-moderated events from everyone except the organizer.
    # Closes the "direct URL still works on hidden events" gap.
    if event.get("is_hidden"):
        viewer = await _resolve_user_from_request(request)
        is_organizer = viewer and event.get("organizer_id") == viewer.get("user_id")
        if not is_organizer:
            raise HTTPException(status_code=404, detail="Event not found")

    # Parse dates
    if isinstance(event["start_date"], str):
        event["start_date"] = datetime.fromisoformat(event["start_date"])
    if event.get("end_date") and isinstance(event["end_date"], str):
        event["end_date"] = datetime.fromisoformat(event["end_date"])
    if isinstance(event["created_at"], str):
        event["created_at"] = datetime.fromisoformat(event["created_at"])
    if event.get("promotion_expires") and isinstance(event["promotion_expires"], str):
        event["promotion_expires"] = datetime.fromisoformat(event["promotion_expires"])
    
    # Calculate distance if coordinates provided
    if latitude and longitude:
        event["distance"] = round(calculate_distance(
            latitude, longitude,
            event["latitude"], event["longitude"]
        ), 1)
    
    return EventResponse(**event)

@events_router.put("/{event_id}", response_model=EventResponse)
async def update_event(event_id: str, event_data: EventCreate, user = Depends(get_current_user)):
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event["organizer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    discounted_price = None
    if event_data.is_paid and event_data.ticket_price and event_data.discount_percentage:
        discounted_price = round(event_data.ticket_price * (1 - event_data.discount_percentage / 100), 2)
    
    update_data = {
        "title": event_data.title,
        "description": event_data.description,
        "category": event_data.category,
        "start_date": event_data.start_date.isoformat(),
        "end_date": event_data.end_date.isoformat() if event_data.end_date else None,
        "location_name": event_data.location_name,
        "address": event_data.address,
        "city": event_data.city,
        "state": event_data.state,
        "zip_code": event_data.zip_code,
        "latitude": event_data.latitude,
        "longitude": event_data.longitude,
        "image_url": event_data.image_url,
        "is_paid": event_data.is_paid,
        "ticket_price": event_data.ticket_price,
        "discount_percentage": event_data.discount_percentage,
        "discounted_price": discounted_price,
        "total_tickets": event_data.total_tickets,
        "tags": event_data.tags
    }
    
    await db.events.update_one({"event_id": event_id}, {"$set": update_data})
    
    updated_event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    
    # Parse dates
    if isinstance(updated_event["start_date"], str):
        updated_event["start_date"] = datetime.fromisoformat(updated_event["start_date"])
    if updated_event.get("end_date") and isinstance(updated_event["end_date"], str):
        updated_event["end_date"] = datetime.fromisoformat(updated_event["end_date"])
    if isinstance(updated_event["created_at"], str):
        updated_event["created_at"] = datetime.fromisoformat(updated_event["created_at"])
    
    return EventResponse(**updated_event)

@events_router.delete("/{event_id}")
async def delete_event(event_id: str, user = Depends(get_current_user)):
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event["organizer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.events.delete_one({"event_id": event_id})
    return {"message": "Event deleted"}

@events_router.get("/user/my-events", response_model=List[EventResponse])
async def get_my_events(user = Depends(get_current_user)):
    events = await db.events.find({"organizer_id": user["user_id"]}, {"_id": 0}).to_list(100)
    
    results = []
    for event in events:
        if isinstance(event["start_date"], str):
            event["start_date"] = datetime.fromisoformat(event["start_date"])
        if event.get("end_date") and isinstance(event["end_date"], str):
            event["end_date"] = datetime.fromisoformat(event["end_date"])
        if isinstance(event["created_at"], str):
            event["created_at"] = datetime.fromisoformat(event["created_at"])
        results.append(EventResponse(**event))
    
    return results

# ============= FOOD TRUCK ROUTES =============

@foodtrucks_router.post("", response_model=FoodTruckResponse)
async def create_food_truck(truck_data: FoodTruckCreate, user = Depends(get_current_user)):
    truck_id = f"truck_{uuid.uuid4().hex[:12]}"
    
    truck_doc = {
        "truck_id": truck_id,
        "name": truck_data.name,
        "description": truck_data.description,
        "cuisine_type": truck_data.cuisine_type,
        "latitude": truck_data.latitude,
        "longitude": truck_data.longitude,
        "address": truck_data.address,
        "city": truck_data.city,
        "state": truck_data.state,
        "zip_code": truck_data.zip_code,
        "operating_hours": truck_data.operating_hours,
        "image_url": truck_data.image_url,
        "menu_highlights": truck_data.menu_highlights,
        "owner_id": user["user_id"],
        "owner_name": user.get("business_name") or user["name"],
        "rating": 0.0,
        "review_count": 0,
        "is_active_today": True,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    
    await db.food_trucks.insert_one(truck_doc)
    
    return FoodTruckResponse(**{
        **truck_doc,
        "last_updated": datetime.now(timezone.utc)
    })

@foodtrucks_router.get("", response_model=List[FoodTruckResponse])
async def get_food_trucks(
    latitude: Optional[float] = Query(None),
    longitude: Optional[float] = Query(None),
    radius: float = Query(25),
    cuisine: Optional[str] = Query(None),
    active_only: bool = Query(True)
):
    query = {}
    
    if cuisine:
        query["cuisine_type"] = {"$regex": cuisine, "$options": "i"}
    
    if active_only:
        query["is_active_today"] = True
    
    trucks = await db.food_trucks.find(query, {"_id": 0}).to_list(500)
    
    results = []
    for truck in trucks:
        truck_copy = dict(truck)
        
        if isinstance(truck_copy["last_updated"], str):
            truck_copy["last_updated"] = datetime.fromisoformat(truck_copy["last_updated"])
        
        if latitude and longitude:
            distance = calculate_distance(
                latitude, longitude,
                truck["latitude"], truck["longitude"]
            )
            if distance <= radius:
                truck_copy["distance"] = round(distance, 1)
                results.append(truck_copy)
        else:
            results.append(truck_copy)
    
    # Sort by distance if coordinates provided
    if latitude and longitude:
        results.sort(key=lambda x: x.get("distance", 999))
    
    return [FoodTruckResponse(**t) for t in results]

@foodtrucks_router.get("/{truck_id}", response_model=FoodTruckResponse)
async def get_food_truck(truck_id: str):
    truck = await db.food_trucks.find_one({"truck_id": truck_id}, {"_id": 0})
    if not truck:
        raise HTTPException(status_code=404, detail="Food truck not found")
    
    if isinstance(truck["last_updated"], str):
        truck["last_updated"] = datetime.fromisoformat(truck["last_updated"])
    
    return FoodTruckResponse(**truck)

@foodtrucks_router.put("/{truck_id}/location")
async def update_food_truck_location(
    truck_id: str,
    latitude: float,
    longitude: float,
    address: str,
    user = Depends(get_current_user)
):
    truck = await db.food_trucks.find_one({"truck_id": truck_id}, {"_id": 0})
    if not truck:
        raise HTTPException(status_code=404, detail="Food truck not found")
    
    if truck["owner_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.food_trucks.update_one(
        {"truck_id": truck_id},
        {"$set": {
            "latitude": latitude,
            "longitude": longitude,
            "address": address,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Location updated"}

@foodtrucks_router.put("/{truck_id}/status")
async def toggle_food_truck_status(truck_id: str, is_active: bool, user = Depends(get_current_user)):
    truck = await db.food_trucks.find_one({"truck_id": truck_id}, {"_id": 0})
    if not truck:
        raise HTTPException(status_code=404, detail="Food truck not found")
    
    if truck["owner_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    await db.food_trucks.update_one(
        {"truck_id": truck_id},
        {"$set": {"is_active_today": is_active, "last_updated": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {"message": f"Status updated to {'active' if is_active else 'inactive'}"}

# ============= COMMENTS & REVIEWS =============

@api_router.post("/comments", response_model=CommentResponse)
async def create_comment(
    target_type: str,  # event or foodtruck
    target_id: str,
    comment_data: CommentCreate,
    user = Depends(get_current_user)
):
    # Verify target exists
    if target_type == "event":
        target = await db.events.find_one({"event_id": target_id}, {"_id": 0})
    elif target_type == "foodtruck":
        target = await db.food_trucks.find_one({"truck_id": target_id}, {"_id": 0})
    else:
        raise HTTPException(status_code=400, detail="Invalid target type")
    
    if not target:
        raise HTTPException(status_code=404, detail=f"{target_type.capitalize()} not found")
    
    comment_id = f"comment_{uuid.uuid4().hex[:12]}"
    
    comment_doc = {
        "comment_id": comment_id,
        "content": comment_data.content,
        "rating": comment_data.rating,
        "user_id": user["user_id"],
        "user_name": user["name"],
        "user_picture": user.get("profile_picture"),
        "target_type": target_type,
        "target_id": target_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.comments.insert_one(comment_doc)
    
    # Update average rating for food trucks
    if target_type == "foodtruck" and comment_data.rating:
        comments = await db.comments.find(
            {"target_type": "foodtruck", "target_id": target_id, "rating": {"$ne": None}},
            {"_id": 0, "rating": 1}
        ).to_list(1000)
        
        if comments:
            avg_rating = sum(c["rating"] for c in comments) / len(comments)
            await db.food_trucks.update_one(
                {"truck_id": target_id},
                {"$set": {"rating": round(avg_rating, 1), "review_count": len(comments)}}
            )
    
    return CommentResponse(**{
        **comment_doc,
        "created_at": datetime.now(timezone.utc)
    })

@api_router.get("/comments/{target_type}/{target_id}", response_model=List[CommentResponse])
async def get_comments(target_type: str, target_id: str):
    comments = await db.comments.find(
        {"target_type": target_type, "target_id": target_id, "is_hidden": {"$ne": True}},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    results = []
    for comment in comments:
        if isinstance(comment["created_at"], str):
            comment["created_at"] = datetime.fromisoformat(comment["created_at"])
        results.append(CommentResponse(**comment))
    
    return results

# ============= PAYMENTS & TICKETS =============

PROMOTION_PACKAGES = [
    {"package_id": "promo_basic", "name": "Basic Boost", "duration_days": 3, "price": 9.99, "description": "3 days of featured placement"},
    {"package_id": "promo_standard", "name": "Standard Boost", "duration_days": 7, "price": 19.99, "description": "7 days of featured placement"},
    {"package_id": "promo_premium", "name": "Premium Boost", "duration_days": 14, "price": 34.99, "description": "14 days of premium featured placement"},
]

@payments_router.get("/promotion-packages")
async def get_promotion_packages():
    return PROMOTION_PACKAGES

@payments_router.post("/checkout/ticket")
async def create_ticket_checkout(purchase: TicketPurchase, request: Request, user = Depends(get_current_user)):
    _enforce_beta_block()
    event = await db.events.find_one({"event_id": purchase.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if not event.get("is_paid"):
        raise HTTPException(status_code=400, detail="This is a free event")
    
    # Check ticket availability
    tickets_available = (event.get("total_tickets") or 0) - (event.get("tickets_sold") or 0)
    if tickets_available < purchase.quantity:
        raise HTTPException(status_code=400, detail="Not enough tickets available")
    
    # Calculate price
    unit_price = event.get("discounted_price") or event.get("ticket_price")
    total_price = round(unit_price * purchase.quantity, 2)
    commission = round(total_price * COMMISSION_RATE, 2)
    
    # Get origin URL from frontend
    origin_url = request.headers.get("Origin") or request.headers.get("Referer", "").rstrip("/")
    if not origin_url:
        origin_url = str(request.base_url).rstrip("/")
    
    # Create payment transaction
    transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
    ticket_id = f"ticket_{uuid.uuid4().hex[:12]}"
    
    transaction_doc = {
        "transaction_id": transaction_id,
        "ticket_id": ticket_id,
        "event_id": purchase.event_id,
        "event_title": event["title"],
        "user_id": user["user_id"],
        "quantity": purchase.quantity,
        "unit_price": unit_price,
        "total_price": total_price,
        "commission": commission,
        "payment_method": purchase.payment_method,
        "payment_status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.payment_transactions.insert_one(transaction_doc)
    
    if purchase.payment_method == "stripe":
        import stripe_helper

        success_url = f"{origin_url}/tickets/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin_url}/events/{purchase.event_id}"

        session = stripe_helper.create_checkout_session(
            amount=float(total_price),
            currency="usd",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "transaction_id": transaction_id,
                "ticket_id": ticket_id,
                "event_id": purchase.event_id,
                "user_id": user["user_id"],
                "type": "ticket",
            },
            product_name=f"Ticket: {event['title']}",
        )

        await db.payment_transactions.update_one(
            {"transaction_id": transaction_id},
            {"$set": {"session_id": session.session_id}}
        )

        return {"checkout_url": session.url, "session_id": session.session_id}
    
    else:  # PayPal
        return {
            "transaction_id": transaction_id,
            "total_price": total_price,
            "payment_method": "paypal"
        }

@payments_router.post("/checkout/promotion")
async def create_promotion_checkout(
    event_id: str,
    package_id: str,
    request: Request,
    user = Depends(get_current_user)
):
    _enforce_beta_block()
    event = await db.events.find_one({"event_id": event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event["organizer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Find package
    package = next((p for p in PROMOTION_PACKAGES if p["package_id"] == package_id), None)
    if not package:
        raise HTTPException(status_code=400, detail="Invalid package")
    
    origin_url = request.headers.get("Origin") or request.headers.get("Referer", "").rstrip("/")
    if not origin_url:
        origin_url = str(request.base_url).rstrip("/")
    
    transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
    
    transaction_doc = {
        "transaction_id": transaction_id,
        "event_id": event_id,
        "user_id": user["user_id"],
        "package_id": package_id,
        "amount": package["price"],
        "duration_days": package["duration_days"],
        "payment_status": "pending",
        "type": "promotion",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.payment_transactions.insert_one(transaction_doc)

    import stripe_helper

    success_url = f"{origin_url}/dashboard?promotion=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin_url}/dashboard"

    session = stripe_helper.create_checkout_session(
        amount=float(package["price"]),
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "transaction_id": transaction_id,
            "event_id": event_id,
            "user_id": user["user_id"],
            "package_id": package_id,
            "duration_days": str(package["duration_days"]),
            "type": "promotion",
        },
        product_name=f"Promotion: {package['name']}",
    )

    await db.payment_transactions.update_one(
        {"transaction_id": transaction_id},
        {"$set": {"session_id": session.session_id}}
    )

    return {"checkout_url": session.url, "session_id": session.session_id}

@payments_router.get("/checkout/status/{session_id}")
async def get_checkout_status(session_id: str):
    import stripe_helper

    status = stripe_helper.get_checkout_status(session_id)
    
    # Update transaction if paid
    if status.payment_status == "paid":
        transaction = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        
        if transaction and transaction.get("payment_status") != "paid":
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"payment_status": "paid"}}
            )
            
            # Handle ticket purchase
            if transaction.get("type") != "promotion" and transaction.get("ticket_id"):
                # Create ticket record
                ticket_doc = {
                    "ticket_id": transaction["ticket_id"],
                    "event_id": transaction["event_id"],
                    "event_title": transaction["event_title"],
                    "user_id": transaction["user_id"],
                    "quantity": transaction["quantity"],
                    "unit_price": transaction["unit_price"],
                    "total_price": transaction["total_price"],
                    "commission": transaction["commission"],
                    "payment_status": "paid",
                    "payment_method": transaction["payment_method"],
                    "created_at": transaction["created_at"]
                }
                await db.tickets.insert_one(ticket_doc)
                
                # Update tickets sold
                await db.events.update_one(
                    {"event_id": transaction["event_id"]},
                    {"$inc": {"tickets_sold": transaction["quantity"]}}
                )
            
            # Handle promotion purchase
            elif transaction.get("type") == "promotion":
                duration_days = int(transaction.get("duration_days", 7))
                promotion_expires = datetime.now(timezone.utc) + timedelta(days=duration_days)
                
                await db.events.update_one(
                    {"event_id": transaction["event_id"]},
                    {"$set": {
                        "is_promoted": True,
                        "promotion_expires": promotion_expires.isoformat()
                    }}
                )
    
    return {
        "status": status.status,
        "payment_status": status.payment_status,
        "amount_total": status.amount_total,
        "currency": status.currency
    }

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    import stripe_helper

    body = await request.body()

    try:
        webhook_response = stripe_helper.handle_webhook(
            body, request.headers.get("Stripe-Signature")
        )

        if webhook_response.payment_status == "paid":
            await db.payment_transactions.update_one(
                {"session_id": webhook_response.session_id},
                {"$set": {"payment_status": "paid"}}
            )

        return {"status": "processed"}
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return {"status": "error"}

@payments_router.get("/my-tickets", response_model=List[TicketResponse])
async def get_my_tickets(user = Depends(get_current_user)):
    tickets = await db.tickets.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(100)
    
    results = []
    for ticket in tickets:
        if isinstance(ticket["created_at"], str):
            ticket["created_at"] = datetime.fromisoformat(ticket["created_at"])
        results.append(TicketResponse(**ticket))
    
    return results

# ============= AI RECOMMENDATIONS =============

@ai_router.post("/recommend")
async def get_recommendations(
    latitude: float,
    longitude: float,
    preferences: Optional[List[str]] = None,
    user = Depends(get_optional_user)
):
    """Recommend nearby events. AI summary disabled in v1 — distance-sorted only.
    To re-enable, integrate Google Gemini directly via `google-genai` here."""
    events = await db.events.find({}, {"_id": 0}).to_list(50)

    nearby_events = []
    for event in events:
        distance = calculate_distance(latitude, longitude, event["latitude"], event["longitude"])
        if distance <= 50:
            event["distance"] = round(distance, 1)
            nearby_events.append(event)

    nearby_events.sort(key=lambda x: x["distance"])
    nearby_events = nearby_events[:5]

    if not nearby_events:
        return {"recommendations": [], "message": "No events found nearby"}

    return {
        "recommendations": [e["event_id"] for e in nearby_events],
        "events": nearby_events,
    }

@ai_router.post("/search")
async def ai_search(query: str, latitude: Optional[float] = None, longitude: Optional[float] = None):
    """Keyword search across events. AI query parsing disabled in v1.
    To re-enable, integrate Google Gemini directly via `google-genai` here."""
    keywords = [k for k in query.split() if k]

    db_query = {}
    if keywords:
        regex = "|".join(keywords)
        db_query["$or"] = [
            {"title": {"$regex": regex, "$options": "i"}},
            {"description": {"$regex": regex, "$options": "i"}},
            {"tags": {"$in": [k.lower() for k in keywords]}},
        ]

    events = await db.events.find(db_query, {"_id": 0}).to_list(20)

    results = []
    for event in events:
        if isinstance(event.get("start_date"), str):
            event["start_date"] = datetime.fromisoformat(event["start_date"])
        if event.get("end_date") and isinstance(event["end_date"], str):
            event["end_date"] = datetime.fromisoformat(event["end_date"])
        if isinstance(event.get("created_at"), str):
            event["created_at"] = datetime.fromisoformat(event["created_at"])

        if latitude is not None and longitude is not None:
            event["distance"] = round(calculate_distance(
                latitude, longitude, event["latitude"], event["longitude"]
            ), 1)

        results.append(event)

    return {"events": results, "search_params": {"keywords": keywords}}

# ============= FLASH DEALS =============

def _to_flash_deal_response(deal: dict) -> dict:
    """Compute derived fields (time_left_seconds, spots_left) on a deal doc."""
    end_time = deal.get("end_time")
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    time_left = int((end_time - datetime.now(timezone.utc)).total_seconds())

    spots_total = deal.get("spots_total")
    spots_claimed = deal.get("spots_claimed", 0)
    spots_left = (spots_total - spots_claimed) if spots_total is not None else None

    event_date = deal.get("event_date")
    if isinstance(event_date, str):
        event_date = datetime.fromisoformat(event_date)

    created_at = deal.get("created_at")
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)

    return {
        "deal_id": deal["deal_id"],
        "event_id": deal["event_id"],
        "event_title": deal.get("event_title", ""),
        "event_image": deal.get("event_image"),
        "event_date": event_date,
        "location_name": deal.get("location_name", ""),
        "city": deal.get("city", ""),
        "description": deal.get("description"),
        "discount_percentage": deal.get("discount_percentage", 0.0),
        "deal_price": deal.get("deal_price", 0.0),
        "original_price": deal.get("original_price", 0.0),
        "business_name": deal.get("business_name", ""),
        "spots_total": spots_total,
        "spots_claimed": spots_claimed,
        "spots_left": spots_left,
        "end_time": end_time,
        "time_left_seconds": max(0, time_left),
        "created_at": created_at,
    }


@flash_deals_router.get("", response_model=List[FlashDealResponse])
async def list_flash_deals(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius: float = 50.0,
    active_only: bool = True,
    limit: int = 50,
):
    """List flash deals, optionally filtered by location and active status."""
    query: Dict[str, Any] = {}
    if active_only:
        query["end_time"] = {"$gt": datetime.now(timezone.utc).isoformat()}

    deals = await db.flash_deals.find(query, {"_id": 0}).to_list(500)

    results = []
    for deal in deals:
        # Skip sold-out deals when active_only
        if active_only and deal.get("spots_total") is not None:
            if deal.get("spots_claimed", 0) >= deal["spots_total"]:
                continue

        # Optional radius filter using stored lat/lon
        if latitude is not None and longitude is not None:
            d_lat = deal.get("latitude")
            d_lon = deal.get("longitude")
            if d_lat is not None and d_lon is not None:
                distance = calculate_distance(latitude, longitude, d_lat, d_lon)
                if distance > radius:
                    continue

        results.append(_to_flash_deal_response(deal))

    # Sort by ending soonest first
    results.sort(key=lambda d: d["time_left_seconds"])
    return results[:limit]


@flash_deals_router.post("", response_model=FlashDealResponse)
async def create_flash_deal(data: FlashDealCreate, user = Depends(get_current_user)):
    """Create a flash deal for an event you organize. Business accounts only."""
    event = await db.events.find_one({"event_id": data.event_id}, {"_id": 0})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event["organizer_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="You don't organize this event")

    if not event.get("is_paid") or not event.get("ticket_price"):
        raise HTTPException(status_code=400, detail="Flash deals require a paid event with a ticket price")

    if not (0 < data.discount_percentage <= 100):
        raise HTTPException(status_code=400, detail="discount_percentage must be between 0 and 100")

    end_time = data.end_time
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    if end_time <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="end_time must be in the future")

    deal_id = f"deal_{uuid.uuid4().hex[:12]}"
    business_name = user.get("business_name") or user.get("name", "Business")

    deal_doc = {
        "deal_id": deal_id,
        "event_id": data.event_id,
        "event_title": event["title"],
        "event_image": event.get("image_url"),
        "event_date": event["start_date"],
        "location_name": event["location_name"],
        "city": event["city"],
        "latitude": event["latitude"],
        "longitude": event["longitude"],
        "description": data.description,
        "discount_percentage": data.discount_percentage,
        "deal_price": data.deal_price,
        "original_price": event["ticket_price"],
        "business_name": business_name,
        "business_id": user["user_id"],
        "spots_total": data.spots_total,
        "spots_claimed": 0,
        "end_time": end_time.isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    await db.flash_deals.insert_one(deal_doc)
    return _to_flash_deal_response(deal_doc)


@flash_deals_router.post("/{deal_id}/claim")
async def claim_flash_deal(deal_id: str, user = Depends(get_current_user)):
    """Reserve a flash deal for the current user. Valid for 24 hours."""
    deal = await db.flash_deals.find_one({"deal_id": deal_id}, {"_id": 0})
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Check expiry
    end_time = deal["end_time"]
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)
    if end_time <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This deal has expired")

    # Check capacity
    if deal.get("spots_total") is not None:
        if deal.get("spots_claimed", 0) >= deal["spots_total"]:
            raise HTTPException(status_code=400, detail="This deal is sold out")

    # Check duplicate claim
    existing = await db.flash_deal_claims.find_one(
        {"deal_id": deal_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if existing:
        raise HTTPException(status_code=400, detail="You have already claimed this deal")

    claim_id = f"claim_{uuid.uuid4().hex[:12]}"
    claim_expires = datetime.now(timezone.utc) + timedelta(hours=24)

    await db.flash_deal_claims.insert_one({
        "claim_id": claim_id,
        "deal_id": deal_id,
        "user_id": user["user_id"],
        "event_id": deal["event_id"],
        "deal_price": deal["deal_price"],
        "claimed_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": claim_expires.isoformat(),
        "redeemed": False,
    })

    await db.flash_deals.update_one(
        {"deal_id": deal_id},
        {"$inc": {"spots_claimed": 1}}
    )

    return {
        "claim_id": claim_id,
        "deal_id": deal_id,
        "expires_at": claim_expires.isoformat(),
        "message": "Deal claimed. Use it within 24 hours when purchasing tickets.",
    }


@flash_deals_router.get("/my-claims")
async def get_my_flash_deal_claims(user = Depends(get_current_user)):
    """Get the current user's active (un-redeemed, un-expired) flash deal claims."""
    claims = await db.flash_deal_claims.find(
        {"user_id": user["user_id"], "redeemed": False},
        {"_id": 0}
    ).to_list(100)

    now = datetime.now(timezone.utc)
    active = []
    for claim in claims:
        expires_at = claim.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > now:
            active.append(claim)

    return active


# ============= SEED DATA =============

@api_router.post("/seed")
async def seed_data():
    """Seed database with sample data.

    Disabled in production: the original seed contains NYC demo
    restaurants/events/forum-posts left over from the Emergent scaffold,
    which polluted the Wilmington data with Manhattan/Brooklyn entries
    when accidentally invoked. We rely on real ingestion (ticketmaster,
    seatgeek, yelp, osm, churches) for live data instead.

    To re-enable for local dev, set ALLOW_SEED=true in env."""
    if os.environ.get("ALLOW_SEED", "").lower() != "true":
        raise HTTPException(
            status_code=403,
            detail="Seed endpoint disabled. Set ALLOW_SEED=true to enable for dev.",
        )
    # Check if already seeded
    existing_events = await db.events.count_documents({})
    if existing_events > 0:
        return {"message": "Data already seeded"}
    
    # Sample events
    sample_events = [
        {
            "event_id": "event_demo_001",
            "title": "Summer Jazz Festival",
            "description": "Experience the best of jazz with live performances from top artists. Food vendors, craft beer, and amazing music await!",
            "category": "concert",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=3, hours=6)).isoformat(),
            "location_name": "Central Park Amphitheater",
            "address": "123 Park Ave",
            "city": "New York",
            "state": "NY",
            "zip_code": "10001",
            "latitude": 40.7829,
            "longitude": -73.9654,
            "image_url": "https://images.unsplash.com/photo-1765278797923-10a027f5c69d?w=800",
            "is_paid": True,
            "ticket_price": 45.00,
            "discount_percentage": 15,
            "discounted_price": 38.25,
            "total_tickets": 500,
            "tickets_sold": 234,
            "is_promoted": True,
            "promotion_expires": (datetime.now(timezone.utc) + timedelta(days=10)).isoformat(),
            "tags": ["jazz", "music", "festival", "outdoor"],
            "organizer_id": "system",
            "organizer_name": "NYC Events Co",
            "organizer_type": "business",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "event_id": "event_demo_002",
            "title": "Downtown Farmers Market",
            "description": "Fresh local produce, artisan goods, and homemade treats. Support local farmers every Saturday!",
            "category": "market",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=2, hours=4)).isoformat(),
            "location_name": "City Square",
            "address": "456 Main St",
            "city": "Brooklyn",
            "state": "NY",
            "zip_code": "11201",
            "latitude": 40.6892,
            "longitude": -73.9857,
            "image_url": "https://images.unsplash.com/photo-1666480141485-d1a86796ca85?w=800",
            "is_paid": False,
            "ticket_price": None,
            "discount_percentage": None,
            "discounted_price": None,
            "total_tickets": None,
            "tickets_sold": 0,
            "is_promoted": False,
            "promotion_expires": None,
            "tags": ["farmers market", "organic", "local", "food"],
            "organizer_id": "system",
            "organizer_name": "Brooklyn Markets",
            "organizer_type": "business",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "event_id": "event_demo_003",
            "title": "5K Charity Run",
            "description": "Join us for a fun 5K run to support local children's hospital. All fitness levels welcome!",
            "category": "marathon",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=7, hours=3)).isoformat(),
            "location_name": "Riverside Park",
            "address": "789 River Road",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10024",
            "latitude": 40.7903,
            "longitude": -73.9745,
            "image_url": "https://images.unsplash.com/photo-1571008887538-b36bb32f4571?w=800",
            "is_paid": True,
            "ticket_price": 25.00,
            "discount_percentage": None,
            "discounted_price": None,
            "total_tickets": 300,
            "tickets_sold": 156,
            "is_promoted": True,
            "promotion_expires": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "tags": ["running", "charity", "fitness", "5k"],
            "organizer_id": "system",
            "organizer_name": "Run for Good",
            "organizer_type": "business",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "event_id": "event_demo_004",
            "title": "Multi-Family Garage Sale",
            "description": "Huge neighborhood garage sale! Furniture, clothes, electronics, toys, and more at amazing prices.",
            "category": "garage_sale",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=1, hours=6)).isoformat(),
            "location_name": "Oak Street Community",
            "address": "321 Oak St",
            "city": "Queens",
            "state": "NY",
            "zip_code": "11375",
            "latitude": 40.7282,
            "longitude": -73.8317,
            "image_url": "https://images.unsplash.com/photo-1768321611388-51d2ad51ceed?w=800",
            "is_paid": False,
            "ticket_price": None,
            "discount_percentage": None,
            "discounted_price": None,
            "total_tickets": None,
            "tickets_sold": 0,
            "is_promoted": False,
            "promotion_expires": None,
            "tags": ["garage sale", "bargains", "second hand", "community"],
            "organizer_id": "system",
            "organizer_name": "Sarah Miller",
            "organizer_type": "personal",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "event_id": "event_demo_005",
            "title": "Happy Hour at The Blue Note",
            "description": "2-for-1 cocktails and live acoustic music. Perfect way to end your work week!",
            "category": "happy_hour",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=1, hours=3)).isoformat(),
            "location_name": "The Blue Note Bar",
            "address": "555 Jazz Alley",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10012",
            "latitude": 40.7308,
            "longitude": -73.9973,
            "image_url": "https://images.unsplash.com/photo-1514362545857-3bc16c4c7d1b?w=800",
            "is_paid": False,
            "ticket_price": None,
            "discount_percentage": None,
            "discounted_price": None,
            "total_tickets": None,
            "tickets_sold": 0,
            "is_promoted": True,
            "promotion_expires": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            "tags": ["happy hour", "cocktails", "music", "bar"],
            "organizer_id": "system",
            "organizer_name": "The Blue Note",
            "organizer_type": "business",
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "event_id": "event_demo_006",
            "title": "Street Food Festival",
            "description": "Over 30 food trucks and vendors serving cuisines from around the world. Live music and family fun!",
            "category": "food_festival",
            "start_date": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
            "end_date": (datetime.now(timezone.utc) + timedelta(days=5, hours=8)).isoformat(),
            "location_name": "Pier 17",
            "address": "89 South Street",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10038",
            "latitude": 40.7063,
            "longitude": -74.0034,
            "image_url": "https://images.unsplash.com/photo-1620589125156-fd5028c5e05b?w=800",
            "is_paid": True,
            "ticket_price": 15.00,
            "discount_percentage": 20,
            "discounted_price": 12.00,
            "total_tickets": 1000,
            "tickets_sold": 420,
            "is_promoted": True,
            "promotion_expires": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
            "tags": ["food", "festival", "international", "family"],
            "organizer_id": "system",
            "organizer_name": "NYC Food Events",
            "organizer_type": "business",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    # Sample food trucks
    sample_trucks = [
        {
            "truck_id": "truck_demo_001",
            "name": "Taco Loco",
            "description": "Authentic Mexican street tacos and burritos. Family recipes passed down for generations.",
            "cuisine_type": "Mexican",
            "latitude": 40.7580,
            "longitude": -73.9855,
            "address": "Times Square Area",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10036",
            "operating_hours": "11AM - 9PM",
            "image_url": "https://images.unsplash.com/photo-1620589125156-fd5028c5e05b?w=800",
            "menu_highlights": ["Carne Asada Tacos", "Al Pastor Burrito", "Churros"],
            "owner_id": "system",
            "owner_name": "Maria's Kitchen",
            "rating": 4.7,
            "review_count": 89,
            "is_active_today": True,
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "truck_id": "truck_demo_002",
            "name": "Seoul Food",
            "description": "Korean BBQ and fusion dishes. Try our famous Korean fried chicken!",
            "cuisine_type": "Korean",
            "latitude": 40.7484,
            "longitude": -73.9857,
            "address": "Herald Square",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10001",
            "operating_hours": "11AM - 8PM",
            "image_url": "https://images.unsplash.com/photo-1567129937968-cdad8f07e2f8?w=800",
            "menu_highlights": ["Korean Fried Chicken", "Bulgogi Bowl", "Kimchi Fries"],
            "owner_id": "system",
            "owner_name": "Seoul Food Inc",
            "rating": 4.5,
            "review_count": 67,
            "is_active_today": True,
            "last_updated": datetime.now(timezone.utc).isoformat()
        },
        {
            "truck_id": "truck_demo_003",
            "name": "Pizza Wheels",
            "description": "Wood-fired Neapolitan pizza made fresh on the spot. Authentic Italian flavors!",
            "cuisine_type": "Italian",
            "latitude": 40.7614,
            "longitude": -73.9776,
            "address": "Columbus Circle",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10019",
            "operating_hours": "12PM - 10PM",
            "image_url": "https://images.unsplash.com/photo-1513104890138-7c749659a591?w=800",
            "menu_highlights": ["Margherita Pizza", "Quattro Formaggi", "Tiramisu"],
            "owner_id": "system",
            "owner_name": "Pizza Wheels LLC",
            "rating": 4.8,
            "review_count": 124,
            "is_active_today": True,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    await db.events.insert_many(sample_events)
    await db.food_trucks.insert_many(sample_trucks)
    
    # Sample Restaurants
    sample_restaurants = [
        {
            "restaurant_id": "rest_demo_001",
            "name": "The Italian Corner",
            "description": "Authentic Italian cuisine with fresh pasta made daily. Family-owned since 1985.",
            "cuisine_type": "Italian",
            "price_level": 3,
            "address": "234 Little Italy Lane",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10013",
            "latitude": 40.7195,
            "longitude": -73.9973,
            "phone": "(212) 555-0123",
            "website": "https://italiancorner.com",
            "image_url": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=800",
            "hours": {
                "monday": {"open": "11:30", "close": "22:00"},
                "tuesday": {"open": "11:30", "close": "22:00"},
                "wednesday": {"open": "11:30", "close": "22:00"},
                "thursday": {"open": "11:30", "close": "23:00"},
                "friday": {"open": "11:30", "close": "23:00"},
                "saturday": {"open": "12:00", "close": "23:00"},
                "sunday": {"open": "12:00", "close": "21:00"}
            },
            "features": ["outdoor_seating", "reservations", "takeout", "wine_bar"],
            "mood_tags": ["romantic", "date_night", "special_occasion"],
            "rating": 4.6,
            "review_count": 234,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "restaurant_id": "rest_demo_002",
            "name": "Sakura Sushi House",
            "description": "Premium omakase and fresh sushi. Traditional Japanese dining experience.",
            "cuisine_type": "Japanese",
            "price_level": 4,
            "address": "567 East Village Ave",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10003",
            "latitude": 40.7264,
            "longitude": -73.9878,
            "phone": "(212) 555-0456",
            "image_url": "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=800",
            "hours": {
                "monday": {"closed": True},
                "tuesday": {"open": "17:00", "close": "22:00"},
                "wednesday": {"open": "17:00", "close": "22:00"},
                "thursday": {"open": "17:00", "close": "22:00"},
                "friday": {"open": "17:00", "close": "23:00"},
                "saturday": {"open": "12:00", "close": "23:00"},
                "sunday": {"open": "12:00", "close": "21:00"}
            },
            "features": ["reservations", "bar", "private_dining"],
            "mood_tags": ["upscale", "date_night", "business_dinner"],
            "rating": 4.8,
            "review_count": 156,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "restaurant_id": "rest_demo_003",
            "name": "BBQ Pit Masters",
            "description": "Texas-style BBQ with slow-smoked brisket, ribs, and all the fixings. Family-friendly with outdoor patio.",
            "cuisine_type": "BBQ",
            "price_level": 2,
            "address": "890 Smokehouse Road",
            "city": "Brooklyn",
            "state": "NY",
            "zip_code": "11215",
            "latitude": 40.6681,
            "longitude": -73.9806,
            "phone": "(718) 555-0789",
            "image_url": "https://images.unsplash.com/photo-1529193591184-b1d58069ecdd?w=800",
            "hours": {
                "monday": {"open": "11:00", "close": "21:00"},
                "tuesday": {"open": "11:00", "close": "21:00"},
                "wednesday": {"open": "11:00", "close": "21:00"},
                "thursday": {"open": "11:00", "close": "21:00"},
                "friday": {"open": "11:00", "close": "22:00"},
                "saturday": {"open": "11:00", "close": "22:00"},
                "sunday": {"open": "11:00", "close": "20:00"}
            },
            "features": ["outdoor_seating", "takeout", "catering", "kid_friendly"],
            "mood_tags": ["family_friendly", "casual", "groups"],
            "rating": 4.5,
            "review_count": 312,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "restaurant_id": "rest_demo_004",
            "name": "Vegan Paradise",
            "description": "Plant-based cuisine that even meat-lovers will enjoy. Organic, locally-sourced ingredients.",
            "cuisine_type": "Vegan",
            "price_level": 2,
            "address": "123 Green Street",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10014",
            "latitude": 40.7352,
            "longitude": -74.0056,
            "phone": "(212) 555-0999",
            "image_url": "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800",
            "hours": {
                "monday": {"open": "09:00", "close": "21:00"},
                "tuesday": {"open": "09:00", "close": "21:00"},
                "wednesday": {"open": "09:00", "close": "21:00"},
                "thursday": {"open": "09:00", "close": "21:00"},
                "friday": {"open": "09:00", "close": "22:00"},
                "saturday": {"open": "10:00", "close": "22:00"},
                "sunday": {"open": "10:00", "close": "20:00"}
            },
            "features": ["outdoor_seating", "delivery", "takeout", "brunch"],
            "mood_tags": ["healthy", "vegetarian", "dog_friendly"],
            "rating": 4.4,
            "review_count": 189,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "restaurant_id": "rest_demo_005",
            "name": "El Mariachi Cantina",
            "description": "Authentic Mexican with handmade tortillas, fresh guacamole, and 50+ tequilas.",
            "cuisine_type": "Mexican",
            "price_level": 2,
            "address": "456 Cinco de Mayo Blvd",
            "city": "Queens",
            "state": "NY",
            "zip_code": "11372",
            "latitude": 40.7515,
            "longitude": -73.8836,
            "phone": "(718) 555-1234",
            "image_url": "https://images.unsplash.com/photo-1615870216519-2f9fa575fa5c?w=800",
            "hours": {
                "monday": {"open": "11:00", "close": "22:00"},
                "tuesday": {"open": "11:00", "close": "22:00"},
                "wednesday": {"open": "11:00", "close": "22:00"},
                "thursday": {"open": "11:00", "close": "23:00"},
                "friday": {"open": "11:00", "close": "24:00"},
                "saturday": {"open": "10:00", "close": "24:00"},
                "sunday": {"open": "10:00", "close": "22:00"}
            },
            "features": ["outdoor_seating", "bar", "live_music", "happy_hour"],
            "mood_tags": ["family_friendly", "groups", "lively"],
            "rating": 4.3,
            "review_count": 267,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    # Sample Attractions (Parks, Trails, Sites)
    sample_attractions = [
        {
            "attraction_id": "attr_demo_001",
            "name": "Central Park",
            "description": "843-acre urban oasis with walking paths, lakes, gardens, and iconic landmarks. Perfect for picnics, jogging, or simply enjoying nature in the city.",
            "attraction_type": "park",
            "address": "Central Park",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10024",
            "latitude": 40.7829,
            "longitude": -73.9654,
            "image_url": "https://images.unsplash.com/photo-1568515387631-8b650bbcdb90?w=800",
            "hours": {"monday": {"open": "06:00", "close": "01:00"}, "tuesday": {"open": "06:00", "close": "01:00"}, "wednesday": {"open": "06:00", "close": "01:00"}, "thursday": {"open": "06:00", "close": "01:00"}, "friday": {"open": "06:00", "close": "01:00"}, "saturday": {"open": "06:00", "close": "01:00"}, "sunday": {"open": "06:00", "close": "01:00"}},
            "admission_fee": None,
            "is_free": True,
            "amenities": ["restrooms", "parking", "picnic_area", "water_fountain", "playground", "bike_rental"],
            "mood_tags": ["family_friendly", "dog_friendly", "wheelchair_accessible", "scenic", "romantic"],
            "best_time_to_visit": "Early morning or late afternoon for fewer crowds",
            "tips": "Visit Bethesda Fountain and row a boat on The Lake. Great for sunset views from Belvedere Castle.",
            "rating": 4.9,
            "review_count": 5420,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "attraction_id": "attr_demo_002",
            "name": "Hudson River Greenway Trail",
            "description": "11-mile paved trail along the Hudson River with stunning views of the water and New Jersey skyline. Great for biking, jogging, and rollerblading.",
            "attraction_type": "hiking_trail",
            "address": "Hudson River Park",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10014",
            "latitude": 40.7371,
            "longitude": -74.0105,
            "image_url": "https://images.unsplash.com/photo-1601024445121-e5b82f020549?w=800",
            "hours": None,
            "admission_fee": None,
            "is_free": True,
            "difficulty_level": "easy",
            "trail_length": 11.0,
            "estimated_duration": "2-4 hours",
            "amenities": ["restrooms", "water_fountain", "bike_rental", "benches"],
            "mood_tags": ["dog_friendly", "wheelchair_accessible", "scenic", "fitness"],
            "best_time_to_visit": "Sunset for beautiful views",
            "tips": "Start at Battery Park and head north. Stop at Little Island for a break.",
            "rating": 4.7,
            "review_count": 1823,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "attraction_id": "attr_demo_003",
            "name": "Prospect Park",
            "description": "585-acre Brooklyn park designed by the creators of Central Park. Features meadows, woodlands, a lake, and the Prospect Park Zoo.",
            "attraction_type": "park",
            "address": "95 Prospect Park West",
            "city": "Brooklyn",
            "state": "NY",
            "zip_code": "11215",
            "latitude": 40.6602,
            "longitude": -73.9690,
            "image_url": "https://images.unsplash.com/photo-1595880500386-4b33c7eb4509?w=800",
            "hours": {"monday": {"open": "05:00", "close": "01:00"}, "tuesday": {"open": "05:00", "close": "01:00"}, "wednesday": {"open": "05:00", "close": "01:00"}, "thursday": {"open": "05:00", "close": "01:00"}, "friday": {"open": "05:00", "close": "01:00"}, "saturday": {"open": "05:00", "close": "01:00"}, "sunday": {"open": "05:00", "close": "01:00"}},
            "admission_fee": None,
            "is_free": True,
            "amenities": ["restrooms", "parking", "picnic_area", "playground", "zoo", "ice_rink"],
            "mood_tags": ["family_friendly", "dog_friendly", "scenic"],
            "best_time_to_visit": "Spring for cherry blossoms, Fall for foliage",
            "tips": "Visit the Boathouse for paddleboat rentals. Check out Smorgasburg food market on Sundays.",
            "rating": 4.8,
            "review_count": 2156,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "attraction_id": "attr_demo_004",
            "name": "The High Line",
            "description": "Elevated linear park built on historic freight rail lines. Features gardens, art installations, and unique city views.",
            "attraction_type": "park",
            "address": "820 Washington St",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10014",
            "latitude": 40.7480,
            "longitude": -74.0048,
            "image_url": "https://images.unsplash.com/photo-1573155993874-d5d48af862ba?w=800",
            "hours": {"monday": {"open": "07:00", "close": "22:00"}, "tuesday": {"open": "07:00", "close": "22:00"}, "wednesday": {"open": "07:00", "close": "22:00"}, "thursday": {"open": "07:00", "close": "22:00"}, "friday": {"open": "07:00", "close": "22:00"}, "saturday": {"open": "07:00", "close": "22:00"}, "sunday": {"open": "07:00", "close": "22:00"}},
            "admission_fee": None,
            "is_free": True,
            "trail_length": 1.45,
            "estimated_duration": "1-2 hours",
            "amenities": ["restrooms", "water_fountain", "food_vendors"],
            "mood_tags": ["wheelchair_accessible", "scenic", "romantic", "photography"],
            "best_time_to_visit": "Weekday mornings to avoid crowds",
            "tips": "Walk from Gansevoort Street to Hudson Yards for the full experience. Check out the viewing window over 10th Avenue.",
            "rating": 4.6,
            "review_count": 3421,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "attraction_id": "attr_demo_005",
            "name": "Staten Island Greenbelt",
            "description": "2,800 acres of protected parkland with 35+ miles of trails. Home to diverse ecosystems, wildlife, and historic sites.",
            "attraction_type": "nature_reserve",
            "address": "700 Rockland Ave",
            "city": "Staten Island",
            "state": "NY",
            "zip_code": "10314",
            "latitude": 40.5795,
            "longitude": -74.1502,
            "image_url": "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?w=800",
            "hours": None,
            "admission_fee": None,
            "is_free": True,
            "difficulty_level": "moderate",
            "trail_length": 35.0,
            "estimated_duration": "2-6 hours depending on trail",
            "amenities": ["restrooms", "parking", "nature_center", "camping"],
            "mood_tags": ["nature_lovers", "hiking", "birdwatching", "dog_friendly"],
            "best_time_to_visit": "Spring and Fall for best hiking weather",
            "tips": "Start at the Nature Center for maps. The Blue Trail offers the most scenic views.",
            "rating": 4.5,
            "review_count": 567,
            "created_at": datetime.now(timezone.utc).isoformat()
        },
        {
            "attraction_id": "attr_demo_006",
            "name": "Brooklyn Bridge",
            "description": "Iconic 1883 suspension bridge connecting Manhattan and Brooklyn. Walk the pedestrian path for stunning city views.",
            "attraction_type": "landmark",
            "address": "Brooklyn Bridge",
            "city": "Manhattan",
            "state": "NY",
            "zip_code": "10038",
            "latitude": 40.7061,
            "longitude": -73.9969,
            "image_url": "https://images.unsplash.com/photo-1496442226666-8d4d0e62e6e9?w=800",
            "hours": None,
            "admission_fee": None,
            "is_free": True,
            "trail_length": 1.1,
            "estimated_duration": "30-60 minutes",
            "amenities": ["none"],
            "mood_tags": ["scenic", "romantic", "photography", "historic"],
            "best_time_to_visit": "Sunrise or sunset for best photos",
            "tips": "Walk from Brooklyn to Manhattan for the best views. Visit DUMBO area in Brooklyn before/after.",
            "rating": 4.8,
            "review_count": 8932,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    ]
    
    # Sample Forum Posts
    sample_posts = [
        {
            "post_id": "post_demo_001",
            "title": "Best coffee shops for remote work?",
            "content": "Looking for coffee shops with good wifi and plenty of outlets. Somewhere I can work for a few hours without feeling rushed. Any recommendations in Manhattan or Brooklyn?",
            "category": "questions",
            "tags": ["coffee", "remote work", "wifi"],
            "location_specific": False,
            "author_id": "system",
            "author_name": "Local Explorer",
            "upvotes": 24,
            "downvotes": 1,
            "comment_count": 12,
            "is_pinned": False,
            "is_moderated": False,
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        },
        {
            "post_id": "post_demo_002",
            "title": "Streetwear swap this Saturday!",
            "content": "Organizing a streetwear swap at McCarren Park this Saturday at 2pm. Bring your vintage pieces, sneakers, or anything fashion-related you want to trade. All styles welcome!",
            "category": "meetups",
            "tags": ["fashion", "swap", "meetup"],
            "location_specific": True,
            "latitude": 40.7200,
            "longitude": -73.9500,
            "neighborhood": "Williamsburg",
            "author_id": "system",
            "author_name": "Fashion Forward",
            "upvotes": 45,
            "downvotes": 2,
            "comment_count": 23,
            "is_pinned": True,
            "is_moderated": False,
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        },
        {
            "post_id": "post_demo_003",
            "title": "Road closure on Broadway this weekend",
            "content": "Heads up everyone - Broadway will be closed between 42nd and 50th streets this weekend for a street fair. Plan alternate routes if you need to get through Times Square area.",
            "category": "alerts",
            "tags": ["traffic", "road closure", "times square"],
            "location_specific": True,
            "latitude": 40.7580,
            "longitude": -73.9855,
            "neighborhood": "Times Square",
            "author_id": "system",
            "author_name": "NYC Traffic Watch",
            "upvotes": 89,
            "downvotes": 0,
            "comment_count": 7,
            "is_pinned": True,
            "is_moderated": False,
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        },
        {
            "post_id": "post_demo_004",
            "title": "Free piano on Myrtle Ave - come get it!",
            "content": "We're moving and can't take our upright piano. It's in decent condition, just needs tuning. Located on Myrtle Ave near Fort Greene Park. You must pick up - we cannot deliver. Available until Sunday.",
            "category": "for_sale",
            "tags": ["free", "piano", "furniture"],
            "location_specific": True,
            "latitude": 40.6920,
            "longitude": -73.9745,
            "neighborhood": "Fort Greene",
            "author_id": "system",
            "author_name": "Moving Soon",
            "upvotes": 15,
            "downvotes": 0,
            "comment_count": 8,
            "is_pinned": False,
            "is_moderated": False,
            "created_at": (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
        },
        {
            "post_id": "post_demo_005",
            "title": "New Vietnamese restaurant on Smith St - Highly recommend!",
            "content": "Just tried the new pho place that opened on Smith St and it's amazing! Best pho I've had outside of Vietnam. The banh mi is also excellent. Very reasonable prices and the staff is super friendly.",
            "category": "recommendations",
            "tags": ["restaurant", "vietnamese", "food"],
            "location_specific": True,
            "latitude": 40.6850,
            "longitude": -73.9890,
            "neighborhood": "Carroll Gardens",
            "author_id": "system",
            "author_name": "Foodie Fan",
            "upvotes": 67,
            "downvotes": 3,
            "comment_count": 19,
            "is_pinned": False,
            "is_moderated": False,
            "created_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        }
    ]
    
    # Add mood_tags to existing events
    for event in sample_events:
        if event["category"] in ["concert", "happy_hour"]:
            event["mood_tags"] = ["adults_only", "lively"]
        elif event["category"] in ["market", "garage_sale", "food_festival"]:
            event["mood_tags"] = ["family_friendly", "dog_friendly", "outdoor"]
        elif event["category"] == "marathon":
            event["mood_tags"] = ["fitness", "outdoor", "family_friendly"]
        else:
            event["mood_tags"] = ["family_friendly"]
    
    # Insert all data
    await db.restaurants.insert_many(sample_restaurants)
    await db.attractions.insert_many(sample_attractions)
    await db.forum_posts.insert_many(sample_posts)
    
    return {
        "message": "Sample data seeded successfully", 
        "events": len(sample_events), 
        "food_trucks": len(sample_trucks),
        "restaurants": len(sample_restaurants),
        "attractions": len(sample_attractions),
        "forum_posts": len(sample_posts)
    }

# ============= MAIN ROUTES =============

@api_router.get("/")
async def root():
    return {"message": "LocalDrift API v1.0", "status": "running"}

@api_router.get("/health")
async def health():
    return {"status": "healthy"}


# ============= FEEDBACK =============

class FeedbackCreate(BaseModel):
    feedback_type: str  # bug | idea | data | business | other
    name: Optional[str] = None
    email: Optional[str] = None
    message: str
    page_url: Optional[str] = None


@api_router.post("/feedback")
async def submit_feedback(data: FeedbackCreate, request: Request):
    """Public endpoint — anyone can submit feedback during beta. Stored in
    db.feedback for review via /api/admin/feedback."""
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")

    feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
    doc = {
        "feedback_id": feedback_id,
        "feedback_type": data.feedback_type or "other",
        "name": (data.name or "").strip() or None,
        "email": (data.email or "").strip() or None,
        "message": data.message.strip(),
        "page_url": data.page_url,
        "user_agent": request.headers.get("User-Agent", ""),
        "ip": request.client.host if request.client else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "resolved": False,
    }
    await db.feedback.insert_one(doc)

    # Fire-and-forget admin notification so I see new feedback without
    # having to remember to check /admin/feedback. No-ops if
    # ADMIN_NOTIFY_EMAIL isn't set.
    site_url = os.environ.get("PUBLIC_FRONTEND_URL", "https://www.localdrift.app").rstrip("/")
    notify_subject = f"[LocalDrift] New feedback: {doc['feedback_type']}"
    notify_html = f"""
        <p><strong>Type:</strong> {escape_html(doc['feedback_type'])}</p>
        <p><strong>From:</strong> {escape_html(doc.get('name') or '(anonymous)')}
        {f"&lt;{escape_html(doc['email'])}&gt;" if doc.get('email') else ''}</p>
        <p><strong>Page:</strong> {escape_html(doc.get('page_url') or '(not provided)')}</p>
        <hr>
        <p style="white-space:pre-wrap;">{escape_html(doc['message'])}</p>
        <hr>
        <p><a href="{site_url}/admin/feedback">Review in admin</a> (paste your admin token)</p>
    """
    _fire_admin_notification(notify_subject, notify_html)

    return {"feedback_id": feedback_id, "status": "received"}


@api_router.get("/admin/feedback")
async def admin_get_feedback(
    request: Request,
    token: Optional[str] = None,
    limit: int = 100,
    feedback_type: Optional[str] = None,
):
    """Admin: review all feedback submissions, newest first."""
    _check_admin(request, token)
    query: dict = {}
    if feedback_type:
        query["feedback_type"] = feedback_type
    cursor = db.feedback.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(limit)
    return {"count": len(items), "items": items}


class EmailSignupCreate(BaseModel):
    email: str
    source: Optional[str] = None  # e.g. "homepage", "about", "footer"


@api_router.post("/email-signups")
async def submit_email_signup(data: EmailSignupCreate, request: Request):
    """Public endpoint — collect email addresses for the launch list.
    Stored in db.email_signups; deduped on lowercased email."""
    email = (data.email or "").strip().lower()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Valid email is required")

    existing = await db.email_signups.find_one({"email": email})
    if existing:
        return {"status": "already_subscribed"}

    doc = {
        "signup_id": f"es_{uuid.uuid4().hex[:12]}",
        "email": email,
        "source": (data.source or "unknown").strip()[:50],
        "user_agent": request.headers.get("User-Agent", ""),
        "ip": request.client.host if request.client else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_signups.insert_one(doc)
    return {"status": "subscribed"}


@api_router.get("/admin/email-signups")
async def admin_list_email_signups(
    request: Request,
    token: Optional[str] = None,
    limit: int = 500,
):
    """Admin: list email signups, newest first."""
    _check_admin(request, token)
    cursor = db.email_signups.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(limit)
    return {"count": len(items), "items": items}


# ============= EMAIL DIGEST =============
# Weekly "what's happening in Wilmington" newsletter. Two pieces:
#   1. Preview: build the HTML for any date range so admin can review
#      it in a browser before sending.
#   2. Send: blast the rendered digest to all subscribed emails. Done
#      synchronously over SMTP — for the early stages with <500 subs
#      this is fine. Move to a queue + Resend/SendGrid when it grows.
#
# The digest builder lives in digest.py; sending in email_helper.py.
# Both can be swapped without touching the routes here.

import digest as _digest
# email_helper is already imported at the top of the file


def _default_digest_range() -> tuple[str, str]:
    """Default to the upcoming Friday through Sunday window. Weekly
    digests typically go out Thursday/Friday morning for the weekend."""
    now = datetime.now(timezone.utc)
    # Days until Friday (weekday(): Mon=0 .. Sun=6, Fri=4)
    days_to_fri = (4 - now.weekday()) % 7
    if days_to_fri == 0 and now.hour > 12:
        days_to_fri = 7
    fri = (now + timedelta(days=days_to_fri)).replace(hour=0, minute=0, second=0, microsecond=0)
    sun = fri + timedelta(days=2, hours=23, minutes=59)
    return fri.isoformat(), sun.isoformat()


@api_router.get("/admin/digest/preview", response_class=HTMLResponse)
async def admin_digest_preview(
    request: Request,
    token: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
):
    """Admin: render the digest HTML for a date range so it can be
    previewed in a browser. Returns HTML directly, not JSON, so the
    admin page can drop it in an iframe."""
    _check_admin(request, token)
    if not start or not end:
        start, end = _default_digest_range()
    # Replace the placeholder so the preview unsub link doesn't 404
    site_url = os.environ.get("PUBLIC_FRONTEND_URL", "https://www.localdrift.app").rstrip("/")
    html = await _digest.generate_digest_html(db, start_iso=start, end_iso=end, site_url=site_url)
    html = html.replace("{{EMAIL}}", "preview@example.com")
    return HTMLResponse(content=html)


class DigestSendRequest(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    subject_override: Optional[str] = None
    test_to: Optional[str] = None  # if set, only send to this address (dry-run-ish)


@api_router.post("/admin/digest/send")
async def admin_digest_send(
    body: DigestSendRequest,
    request: Request,
    token: Optional[str] = None,
):
    """Admin: send the digest to either every subscriber or a single
    test_to address. Returns counts of attempted / sent / failed."""
    _check_admin(request, token)
    start = body.start or _default_digest_range()[0]
    end = body.end or _default_digest_range()[1]
    subject = body.subject_override or _digest.generate_digest_subject(start, end)
    site_url = os.environ.get("PUBLIC_FRONTEND_URL", "https://www.localdrift.app").rstrip("/")
    html_template = await _digest.generate_digest_html(db, start_iso=start, end_iso=end, site_url=site_url)

    if body.test_to:
        recipients = [{"email": body.test_to.strip().lower()}]
    else:
        cursor = db.email_signups.find(
            {"unsubscribed": {"$ne": True}},
            {"_id": 0, "email": 1},
        )
        recipients = await cursor.to_list(10000)

    attempted = sent = failed = 0
    for r in recipients:
        addr = r.get("email")
        if not addr:
            continue
        attempted += 1
        # Personalize unsub link per recipient. The {{EMAIL}} token in
        # digest.py gets URL-encoded so the unsubscribe page can pre-fill.
        from urllib.parse import quote
        html_personalized = html_template.replace("{{EMAIL}}", quote(addr))
        ok = _email_helper.send_email(addr, subject, html_personalized)
        if ok:
            sent += 1
        else:
            failed += 1

    # Log the send so admin can see history
    await db.digest_runs.insert_one({
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "start": start,
        "end": end,
        "subject": subject,
        "attempted": attempted,
        "sent": sent,
        "failed": failed,
        "test_mode": bool(body.test_to),
    })
    return {"attempted": attempted, "sent": sent, "failed": failed}


@api_router.get("/admin/digest/runs")
async def admin_digest_runs(request: Request, token: Optional[str] = None, limit: int = 50):
    _check_admin(request, token)
    cursor = db.digest_runs.find({}, {"_id": 0}).sort("ran_at", -1).limit(limit)
    return await cursor.to_list(limit)


# ============= REDDIT BOT PREVIEW =============
# Phase D: dry-run only. Renders markdown for any combination of style +
# month, with no Reddit API calls. Used by /admin/reddit to generate the
# previews we paste into the r/Wilmington community-vote post.
#
# Live posting machinery (PRAW + cron + sticky state machine) lands in
# a follow-up PR once the mods + community pick a winning format.

import reddit_bot.runner as _reddit_runner


@api_router.get("/admin/reddit/preview")
async def admin_reddit_preview(
    request: Request,
    token: Optional[str] = None,
    style: str = "weekly",
    month: Optional[str] = None,
    include_tickets: bool = False,
):
    """Render one style + month combination. Returns markdown + counts.
    style ∈ {weekly, by_category, chronological}; month is YYYY-MM
    (defaults to next month). include_tickets adds an off-platform
    "tickets" link to ticketed events — defaults False (Option A:
    clean, no per-event links)."""
    _check_admin(request, token)
    try:
        return await _reddit_runner.preview(
            db, style=style, month_key=month, include_tickets=include_tickets,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_router.get("/admin/reddit/preview-all")
async def admin_reddit_preview_all(
    request: Request,
    token: Optional[str] = None,
    month: Optional[str] = None,
    include_tickets: bool = False,
):
    """Render all three styles for the same month in one round trip.
    Used by the admin UI to show them side-by-side without three
    sequential calls."""
    _check_admin(request, token)
    return await _reddit_runner.preview_all(
        db, month_key=month, include_tickets=include_tickets,
    )


# Public unsubscribe endpoint (one-click, no auth — the email address
# itself is the token. Low-stakes: the worst an attacker can do is
# unsubscribe someone else, which is reversible by re-signing up.)
@api_router.post("/email-signups/unsubscribe")
async def public_unsubscribe(email: str):
    addr = (email or "").strip().lower()
    if not addr:
        raise HTTPException(status_code=400, detail="email required")
    result = await db.email_signups.update_one(
        {"email": addr},
        {"$set": {"unsubscribed": True, "unsubscribed_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"status": "unsubscribed" if result.matched_count else "not_found"}


# ============= UNIFIED SEARCH =============
# Cross-collection search powering the hero search bar. Single query string,
# fans out to events, restaurants, attractions, food trucks, and churches in
# parallel, returns grouped results.
#
# Synonym expansion: users type natural-language category words ("gym",
# "park", "pool") that won't literally appear in our data. We map those to
# search terms PLUS direct that result type to the front of the response so
# the homepage knows where to send the user if they hit Enter.

# Map intent keyword -> (extra search terms, primary collection to surface).
# Order matters: first-matching wins. Add aliases here as they come up.
_SEARCH_INTENT_MAP = [
    # word(s) typed -> (extra regex tokens, preferred type for "go-to" hint)
    (("gym", "gyms", "fitness", "workout", "crossfit"),
     ["gym", "fitness", "crossfit", "yoga", "pilates"], "fitness"),
    (("pool", "pools", "swim", "swimming", "aquatic"),
     ["pool", "swim", "aquatic"], "activities"),
    (("park", "parks", "trail", "trails", "hike", "hiking", "nature", "outdoors"),
     ["park", "trail", "garden", "nature", "preserve"], "attractions"),
    (("beach", "beaches", "ocean", "shore"),
     ["beach", "shore", "pier"], "attractions"),
    (("museum", "museums", "art", "gallery", "history"),
     ["museum", "gallery", "historic", "art"], "attractions"),
    (("food", "eat", "restaurant", "restaurants", "dining", "lunch", "dinner", "breakfast", "brunch"),
     ["restaurant", "cafe", "diner", "grill", "kitchen"], "restaurants"),
    (("truck", "trucks", "food truck", "food trucks"),
     ["truck"], "food_trucks"),
    (("bar", "bars", "pub", "pubs", "brewery", "breweries", "drinks", "cocktail", "cocktails"),
     ["bar", "pub", "brewery", "tavern", "lounge"], "restaurants"),
    (("concert", "concerts", "show", "shows", "live music", "music"),
     ["concert", "live", "music", "band"], "events"),
    (("sport", "sports", "game", "games"),
     ["sport", "game", "match"], "events"),
    (("kids", "family", "children", "child"),
     ["family", "kids", "children", "playground"], "activities"),
    (("bowling", "arcade", "go kart", "go karts", "putt putt", "mini golf", "minigolf"),
     ["bowling", "arcade", "kart", "putt", "mini golf"], "activities"),
    (("church", "churches", "worship", "mass", "service", "synagogue", "temple", "mosque"),
     ["church", "worship", "chapel"], "churches"),
    (("event", "events", "things to do", "happening"),
     [], "events"),
]


def _expand_search_terms(q: str) -> tuple[list[str], Optional[str]]:
    """Given a raw query string, return (search_terms, preferred_type).

    Search terms = original tokens + any synonym expansion based on intent.
    Preferred type = the collection most likely to satisfy the query, so
    the frontend can default to that tab on Enter."""
    raw = (q or "").strip().lower()
    if not raw:
        return [], None

    base_tokens = [t for t in re.split(r"\s+", raw) if len(t) >= 2]
    extras: list[str] = []
    preferred: Optional[str] = None

    for triggers, expansions, pref_type in _SEARCH_INTENT_MAP:
        if any(trig in raw for trig in triggers):
            extras.extend(expansions)
            if preferred is None:
                preferred = pref_type
            # Keep scanning so multiple intents can stack expansions.

    # Dedupe while preserving order
    seen = set()
    terms = []
    for t in base_tokens + extras:
        if t not in seen:
            seen.add(t)
            terms.append(t)
    return terms, preferred


def _build_search_filter(terms: list[str], fields: list[str]) -> dict:
    """Build a Mongo $or filter that matches ANY term against ANY field
    via case-insensitive regex. Empty -> match nothing (so callers can
    short-circuit on empty input)."""
    if not terms:
        return {"_id": {"$exists": False}}  # impossible match
    # Escape regex metachars in user input
    pattern = "|".join(re.escape(t) for t in terms)
    return {"$or": [{f: {"$regex": pattern, "$options": "i"}} for f in fields]}


@api_router.get("/search")
async def unified_search(
    q: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    limit_per_type: int = 8,
):
    """Unified search across events, restaurants, attractions, food trucks,
    and churches. Returns results grouped by type so the homepage search
    can render a multi-section results page or auto-route to the most
    relevant tab.

    Query string `q` is fuzzy: tokenized + synonym-expanded so that users
    typing "gym" find fitness centers, "park" finds outdoor attractions,
    "food truck" finds trucks, etc."""
    terms, preferred_type = _expand_search_terms(q)
    if not terms:
        return {
            "query": q,
            "preferred_type": None,
            "total": 0,
            "groups": {
                "events": [], "restaurants": [], "attractions": [],
                "fitness": [], "activities": [], "food_trucks": [], "churches": [],
            },
        }

    # Same category groups as routes/attractions.py — kept in sync
    # manually rather than imported to avoid circular dependency.
    ATTR_GROUPS = {
        "outdoor": [
            "park", "hiking_trail", "beach", "garden", "playground",
            "landmark", "museum", "nature_reserve", "viewpoint", "historic_site",
        ],
        "fitness": [
            "fitness", "sports_centre",
            "tennis_court", "basketball_court", "pickleball_court",
            "soccer_field", "volleyball_court",
            "ice_rink", "skate_park",
        ],
        "activities": [
            "golf_course", "mini_golf", "bowling", "go_karts", "arcade",
            "swimming_pool", "water_park", "amusement",
        ],
    }

    # Per-collection field lists. Keep narrow to avoid noisy matches on
    # long descriptions; we'll relax this later if precision is too tight.
    text_filters = {
        "events": _build_search_filter(terms, ["title", "description", "tags", "category", "location_name"]),
        "restaurants": _build_search_filter(terms, ["name", "description", "categories", "city"]),
        "attractions": _build_search_filter(terms, ["name", "description", "category", "tags", "city", "attraction_type"]),
        "food_trucks": _build_search_filter(terms, ["name", "description", "cuisine", "categories"]),
        "churches": _build_search_filter(terms, ["name", "description", "denomination", "religion", "city"]),
    }

    # For attractions, intersect the text filter with each category group's
    # attraction_type whitelist so a "gym" search lands in the fitness
    # bucket rather than getting lumped under generic "attractions".
    def attr_filter_for(group_name: str) -> dict:
        return {"$and": [
            text_filters["attractions"],
            {"attraction_type": {"$in": ATTR_GROUPS[group_name]}},
        ]}

    # Run queries in parallel — 5 base + 3 split attraction buckets
    events_t = db.events.find(text_filters["events"], {"_id": 0}).limit(limit_per_type).to_list(limit_per_type)
    rests_t = db.restaurants.find(text_filters["restaurants"], {"_id": 0}).limit(limit_per_type).to_list(limit_per_type)
    outdoor_t = db.attractions.find(attr_filter_for("outdoor"), {"_id": 0}).limit(limit_per_type).to_list(limit_per_type)
    fitness_t = db.attractions.find(attr_filter_for("fitness"), {"_id": 0}).limit(limit_per_type).to_list(limit_per_type)
    activities_t = db.attractions.find(attr_filter_for("activities"), {"_id": 0}).limit(limit_per_type).to_list(limit_per_type)
    trucks_t = db.food_trucks.find(text_filters["food_trucks"], {"_id": 0}).limit(limit_per_type).to_list(limit_per_type)
    churches_t = db.churches.find(text_filters["churches"], {"_id": 0}).limit(limit_per_type).to_list(limit_per_type)

    events, rests, outdoor, fitness, activities, trucks, churches = await asyncio.gather(
        events_t, rests_t, outdoor_t, fitness_t, activities_t, trucks_t, churches_t
    )

    def add_distance(items, lat_key="latitude", lon_key="longitude"):
        if latitude is None or longitude is None:
            return items
        for it in items:
            try:
                it["distance"] = round(calculate_distance(
                    latitude, longitude, it[lat_key], it[lon_key]
                ), 1)
            except (KeyError, TypeError):
                it["distance"] = None
        return items

    groups = {
        "events": add_distance(events),
        "restaurants": add_distance(rests),
        "attractions": add_distance(outdoor),  # outdoor — the /attractions tab
        "fitness": add_distance(fitness),       # the /fitness tab
        "activities": add_distance(activities), # the /activities tab
        "food_trucks": add_distance(trucks),
        "churches": add_distance(churches),
    }

    # If no preferred_type was inferred from intent, pick the bucket with
    # the most hits — that's where the user probably wants to land.
    if preferred_type is None:
        non_empty = [(k, len(v)) for k, v in groups.items() if v]
        if non_empty:
            preferred_type = max(non_empty, key=lambda kv: kv[1])[0]

    return {
        "query": q,
        "preferred_type": preferred_type,
        "total": sum(len(v) for v in groups.values()),
        "groups": groups,
    }


# ============= USER REPORTS / MODERATION =============
# Lightweight reporting system: any signed-in user can flag a forum post,
# comment, event, or other user-submitted content for admin review. Admin
# can review the queue and either take action (force-delete the target)
# or dismiss the report.
#
# Schema kept deliberately narrow — no notifications, no auto-hide
# thresholds, no mod logs. We can layer those on once the launch shows
# what abuse actually looks like.

REPORT_TARGET_TYPES = {"post", "comment", "event", "user", "creator"}
REPORT_REASONS = {"spam", "abuse", "inappropriate", "misinformation", "other"}
REPORT_STATUSES = {"pending", "reviewed", "actioned", "dismissed"}

# Auto-moderation: once N distinct users report the same target, hide it
# from public feeds pending admin review. Reports from the same user don't
# stack — only distinct reporter_id values count, so a single bad actor
# can't game the threshold by spamming reports.
_AUTO_HIDE_THRESHOLD = 3


async def _maybe_auto_hide(target_type: str, target_id: str) -> bool:
    """Count distinct pending reporters and auto-hide the target if the
    threshold is met. Returns True if the target was hidden by this call."""
    distinct = await db.reports.distinct(
        "reporter_id",
        {"target_type": target_type, "target_id": target_id, "status": "pending"},
    )
    if len(distinct) < _AUTO_HIDE_THRESHOLD:
        return False

    # Field varies per collection — posts already use is_moderated which the
    # community route filters on. Events and comments get a new is_hidden
    # flag (filtered in their respective list endpoints).
    now_iso = datetime.now(timezone.utc).isoformat()
    if target_type == "post":
        r = await db.forum_posts.update_one(
            {"post_id": target_id, "is_moderated": {"$ne": True}},
            {"$set": {"is_moderated": True, "auto_hidden_at": now_iso}},
        )
        return r.modified_count > 0
    if target_type == "comment":
        # Try both collections (forum_comments for community, comments for events)
        r1 = await db.forum_comments.update_one(
            {"comment_id": target_id, "is_hidden": {"$ne": True}},
            {"$set": {"is_hidden": True, "auto_hidden_at": now_iso}},
        )
        r2 = await db.comments.update_one(
            {"comment_id": target_id, "is_hidden": {"$ne": True}},
            {"$set": {"is_hidden": True, "auto_hidden_at": now_iso}},
        )
        return (r1.modified_count + r2.modified_count) > 0
    if target_type == "event":
        r = await db.events.update_one(
            {"event_id": target_id, "is_hidden": {"$ne": True}},
            {"$set": {"is_hidden": True, "auto_hidden_at": now_iso}},
        )
        return r.modified_count > 0
    if target_type == "creator":
        # Community-source directory entries — flip is_hidden so the
        # public list filters them out. The admin queue still surfaces
        # them so we can review.
        r = await db.community_sources.update_one(
            {"source_id": target_id, "is_hidden": {"$ne": True}},
            {"$set": {"is_hidden": True, "auto_hidden_at": now_iso}},
        )
        return r.modified_count > 0
    return False


async def _restore_target(target_type: str, target_id: str) -> bool:
    """Reverse of _maybe_auto_hide — clear the hide flag so the content
    becomes visible again. Used when admin dismisses a report."""
    if target_type == "post":
        r = await db.forum_posts.update_one(
            {"post_id": target_id},
            {"$set": {"is_moderated": False}, "$unset": {"auto_hidden_at": ""}},
        )
        return r.modified_count > 0
    if target_type == "comment":
        r1 = await db.forum_comments.update_one(
            {"comment_id": target_id},
            {"$set": {"is_hidden": False}, "$unset": {"auto_hidden_at": ""}},
        )
        r2 = await db.comments.update_one(
            {"comment_id": target_id},
            {"$set": {"is_hidden": False}, "$unset": {"auto_hidden_at": ""}},
        )
        return (r1.modified_count + r2.modified_count) > 0
    if target_type == "event":
        r = await db.events.update_one(
            {"event_id": target_id},
            {"$set": {"is_hidden": False}, "$unset": {"auto_hidden_at": ""}},
        )
        return r.modified_count > 0
    if target_type == "creator":
        r = await db.community_sources.update_one(
            {"source_id": target_id},
            {"$set": {"is_hidden": False}, "$unset": {"auto_hidden_at": ""}},
        )
        return r.modified_count > 0
    return False


class ReportCreate(BaseModel):
    target_type: str   # post | comment | event | user
    target_id: str
    reason: str        # spam | abuse | inappropriate | misinformation | other
    details: Optional[str] = None  # free-text user-supplied context


@api_router.post("/reports")
async def submit_report(data: ReportCreate, request: Request):
    """Authenticated users flag content for review.

    Lightweight: stores the report + denormalizes some target metadata
    so an admin can scan the queue without needing to cross-join. The
    same target+reporter can be reported multiple times (rate limiting
    can be added later if it's an issue)."""
    user = await _resolve_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in to report content")

    if data.target_type not in REPORT_TARGET_TYPES:
        raise HTTPException(status_code=400, detail=f"target_type must be one of {sorted(REPORT_TARGET_TYPES)}")
    if data.reason not in REPORT_REASONS:
        raise HTTPException(status_code=400, detail=f"reason must be one of {sorted(REPORT_REASONS)}")

    # Pull a snapshot of the target so we can show admins what was flagged
    # even if the original is deleted before review.
    snapshot = {}
    try:
        if data.target_type == "post":
            t = await db.forum_posts.find_one({"post_id": data.target_id}, {"_id": 0, "title": 1, "content": 1, "author_id": 1, "author_name": 1})
            snapshot = t or {}
        elif data.target_type == "comment":
            t = await db.comments.find_one({"comment_id": data.target_id}, {"_id": 0, "content": 1, "author_id": 1, "author_name": 1})
            snapshot = t or {}
        elif data.target_type == "event":
            t = await db.events.find_one({"event_id": data.target_id}, {"_id": 0, "title": 1, "description": 1, "organizer_id": 1, "organizer_name": 1})
            snapshot = t or {}
        elif data.target_type == "creator":
            t = await db.community_sources.find_one(
                {"source_id": data.target_id},
                {"_id": 0, "name": 1, "description": 1, "category": 1, "links": 1},
            )
            snapshot = t or {}
    except Exception:
        snapshot = {}

    report_id = f"rpt_{uuid.uuid4().hex[:12]}"
    doc = {
        "report_id": report_id,
        "target_type": data.target_type,
        "target_id": data.target_id,
        "reason": data.reason,
        "details": (data.details or "").strip()[:1000] or None,
        "reporter_id": user["user_id"],
        "reporter_name": user.get("name"),
        "reporter_email": user.get("email"),
        "target_snapshot": snapshot,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ip": request.client.host if request.client else None,
    }
    await db.reports.insert_one(doc)

    # Auto-moderation: if N distinct users have flagged this target, hide
    # it pending admin review. Same user reporting twice doesn't stack.
    auto_hidden = await _maybe_auto_hide(data.target_type, data.target_id)

    # Fire-and-forget admin notification. Surfaces "something was reported"
    # without forcing admin to remember to check /admin/reports.
    site_url = os.environ.get("PUBLIC_FRONTEND_URL", "https://www.localdrift.app").rstrip("/")
    target_label = {"post": "forum post", "comment": "comment", "event": "event", "user": "user", "creator": "community source"}.get(data.target_type, data.target_type)
    snap_preview = ""
    if snapshot:
        title = snapshot.get("title") or snapshot.get("name") or ""
        body = snapshot.get("content") or snapshot.get("description") or ""
        if title:
            snap_preview += f"<p><strong>{escape_html(title)}</strong></p>"
        if body:
            snap_preview += f"<p style='white-space:pre-wrap;'>{escape_html(body[:400])}{'…' if len(body) > 400 else ''}</p>"
    notify_subject = f"[LocalDrift] Report: {data.reason} on a {target_label}{' (AUTO-HIDDEN)' if auto_hidden else ''}"
    notify_html = f"""
        <p><strong>Reason:</strong> {escape_html(data.reason)}</p>
        <p><strong>Target:</strong> {escape_html(target_label)} <code>{escape_html(data.target_id)}</code></p>
        <p><strong>Reporter:</strong> {escape_html(user.get('name') or 'unknown')}
        {f"&lt;{escape_html(user.get('email', ''))}&gt;" if user.get('email') else ''}</p>
        {f"<p><strong>Reporter notes:</strong></p><p style='white-space:pre-wrap;'>{escape_html(data.details)}</p>" if data.details else ''}
        <hr>
        <p><em>Target snapshot:</em></p>
        {snap_preview or '<p>(no preview available)</p>'}
        <hr>
        {'<p><strong>This content was auto-hidden</strong> (3+ distinct reporters). Review to confirm or restore.</p>' if auto_hidden else ''}
        <p><a href="{site_url}/admin/reports">Review in admin</a> (paste your admin token)</p>
    """
    _fire_admin_notification(notify_subject, notify_html)

    return {"report_id": report_id, "status": "received", "auto_hidden": auto_hidden}


async def _resolve_user_from_request(request: Request) -> Optional[dict]:
    """Try to get the current user from the Authorization header without
    forcing it (so the endpoint can return a clean 401 instead of FastAPI's
    generic 'Not authenticated' error)."""
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"user_id": payload.get("user_id")}, {"_id": 0, "password": 0})
        return user
    except Exception:
        return None


@api_router.get("/admin/reports")
async def admin_list_reports(
    request: Request,
    token: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 100,
):
    """Admin: review the report queue. Default = pending only."""
    _check_admin(request, token)
    query: dict = {}
    if status_filter:
        if status_filter not in REPORT_STATUSES:
            raise HTTPException(status_code=400, detail="invalid status filter")
        query["status"] = status_filter
    else:
        query["status"] = "pending"
    cursor = db.reports.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(limit)
    return {"count": len(items), "items": items}


class ReportReviewRequest(BaseModel):
    status: str          # reviewed | actioned | dismissed
    notes: Optional[str] = None
    delete_target: bool = False  # admin force-delete the reported content
    restore_target: bool = False  # un-hide a falsely-auto-hidden target


@api_router.post("/admin/reports/{report_id}/review")
async def admin_review_report(
    report_id: str,
    body: ReportReviewRequest,
    request: Request,
    token: Optional[str] = None,
):
    """Admin: mark a report as reviewed/actioned/dismissed and optionally
    force-delete the underlying target as a single action."""
    _check_admin(request, token)
    if body.status not in {"reviewed", "actioned", "dismissed"}:
        raise HTTPException(status_code=400, detail="invalid status")

    report = await db.reports.find_one({"report_id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Restore (un-hide) takes priority over delete because if both flags
    # are set we want a hard delete, not "restore-then-delete". So handle
    # restore only when delete_target is False.
    restored_target = False
    if body.restore_target and not body.delete_target:
        restored_target = await _restore_target(report["target_type"], report["target_id"])

    deleted_target = False
    if body.delete_target:
        target_type = report["target_type"]
        target_id = report["target_id"]
        if target_type == "post":
            r = await db.forum_posts.delete_one({"post_id": target_id})
            await db.comments.delete_many({"target_id": target_id, "target_type": "post"})
            await db.votes.delete_many({"target_id": target_id, "target_type": "post"})
            deleted_target = r.deleted_count > 0
        elif target_type == "comment":
            r = await db.comments.delete_one({"comment_id": target_id})
            deleted_target = r.deleted_count > 0
        elif target_type == "event":
            r = await db.events.delete_one({"event_id": target_id})
            deleted_target = r.deleted_count > 0
        elif target_type == "creator":
            r = await db.community_sources.delete_one({"source_id": target_id})
            deleted_target = r.deleted_count > 0

    await db.reports.update_one(
        {"report_id": report_id},
        {"$set": {
            "status": body.status,
            "reviewer_notes": (body.notes or "").strip()[:1000] or None,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "deleted_target": deleted_target,
            "restored_target": restored_target,
        }},
    )
    return {
        "report_id": report_id,
        "status": body.status,
        "deleted_target": deleted_target,
        "restored_target": restored_target,
    }


# ============= COMMUNITY SOURCES DIRECTORY =============
# Public-facing directory of local content creators (subreddit mods,
# FB page owners, IG accounts, blogs, podcasts) who want to be featured
# on LocalDrift. Self-service signup, admin approval at intake. Reuses
# the existing reports + auto-hide infrastructure (target_type="creator"
# is wired into _maybe_auto_hide/_restore_target above).

COMMUNITY_SOURCE_CATEGORIES = {
    "subreddit", "facebook_group", "facebook_page", "instagram",
    "tiktok", "youtube", "blog", "newsletter", "podcast", "other",
}

COMMUNITY_SOURCE_STATUSES = {"pending", "approved", "rejected", "hidden"}


def _slugify(name: str) -> str:
    """Lowercase + hyphenate + strip junk. Used for dedup of submissions
    (two people independently submitting "Wilmington Foodies" should
    collide and we surface the existing record to the second submitter)."""
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80]


class CommunitySourceLink(BaseModel):
    platform: str  # e.g. "reddit", "instagram", "youtube" — free-form short label
    url: str
    handle: Optional[str] = None  # e.g. "@wilmingtonfoodies" — display-only


class CommunitySourceSubmit(BaseModel):
    name: str
    description: str
    category: str
    coverage_tags: List[str] = []
    links: List[CommunitySourceLink]
    submitter_email: EmailStr
    submitter_name: Optional[str] = None


class CommunitySourceAdminUpdate(BaseModel):
    status: str  # approved | rejected | hidden | pending
    admin_notes: Optional[str] = None
    # Optional in-place edits an admin can make at review time.
    patch_name: Optional[str] = None
    patch_description: Optional[str] = None
    patch_category: Optional[str] = None


def _public_source_projection(doc: dict) -> dict:
    """Strip private fields before returning to public consumers."""
    if not doc:
        return doc
    return {
        "source_id": doc.get("source_id"),
        "name": doc.get("name"),
        "slug": doc.get("slug"),
        "description": doc.get("description"),
        "category": doc.get("category"),
        "coverage_tags": doc.get("coverage_tags") or [],
        "links": doc.get("links") or [],
        "created_at": doc.get("created_at"),
    }


@api_router.post("/community-sources")
async def submit_community_source(data: CommunitySourceSubmit, request: Request):
    """Public: submit a creator for inclusion in the directory.
    Goes into the admin pending queue; not visible publicly until approved.
    Slug-deduped — submitting a name that collides with an existing
    pending/approved row returns 409 with the conflicting source's
    public projection so the user can see "you're already in the queue"
    rather than getting a confusing error."""
    name = (data.name or "").strip()
    description = (data.description or "").strip()
    if len(name) < 3 or len(name) > 80:
        raise HTTPException(status_code=400, detail="Name must be 3-80 characters")
    if len(description) > 500:
        raise HTTPException(status_code=400, detail="Description must be 500 characters or less")
    if data.category not in COMMUNITY_SOURCE_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of {sorted(COMMUNITY_SOURCE_CATEGORIES)}",
        )
    if not data.links or not any((lnk.url or "").strip() for lnk in data.links):
        raise HTTPException(status_code=400, detail="At least one link is required")

    # Light URL validation — reject anything that doesn't look like a URL.
    # Strict validation belongs at the schema layer but EmailStr / HttpUrl
    # for the link URLs would be too strict (we want to accept "reddit.com/r/x"
    # style entries too). Just require a dot.
    for lnk in data.links:
        url = (lnk.url or "").strip()
        if not url or "." not in url:
            raise HTTPException(status_code=400, detail=f"Invalid URL: {url!r}")

    slug = _slugify(name)
    if not slug:
        raise HTTPException(status_code=400, detail="Name contains no valid characters")

    # Dedup against existing pending/approved rows. Rejected/hidden don't
    # block re-submission (legitimate creator may want to try again).
    existing = await db.community_sources.find_one(
        {"slug": slug, "status": {"$in": ["pending", "approved"]}},
        {"_id": 0},
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "A submission with this name already exists",
                "existing": _public_source_projection(existing),
                "existing_status": existing.get("status"),
            },
        )

    # If the submitter is signed in, attach their user_id for follow-up.
    user = await _resolve_user_from_request(request)

    source_id = f"csrc_{uuid.uuid4().hex[:12]}"
    doc = {
        "source_id": source_id,
        "name": name,
        "slug": slug,
        "description": description,
        "category": data.category,
        "coverage_tags": [t.strip().lower() for t in (data.coverage_tags or []) if t.strip()][:10],
        "links": [
            {
                "platform": (lnk.platform or "").strip()[:30] or "other",
                "url": (lnk.url or "").strip()[:500],
                "handle": ((lnk.handle or "").strip() or None),
            }
            for lnk in data.links
        ],
        "submitter_email": data.submitter_email.lower(),
        "submitter_name": (data.submitter_name or "").strip() or None,
        "submitter_user_id": user["user_id"] if user else None,
        "status": "pending",
        "is_hidden": False,
        "auto_hidden_at": None,
        "admin_notes": None,
        "reviewed_at": None,
        "reviewed_by": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ip": request.client.host if request.client else None,
    }
    await db.community_sources.insert_one(doc)

    # Fire-and-forget admin notification — surfaces new submissions
    # without admin having to remember to check the queue.
    site_url = os.environ.get("PUBLIC_FRONTEND_URL", "https://www.localdrift.app").rstrip("/")
    primary_link = (data.links[0].url if data.links else "")
    notify_subject = f"[LocalDrift] New community source submitted: {doc['name']}"
    notify_html = f"""
        <p><strong>{escape_html(doc['name'])}</strong>
        <span style="color:#6b7280;">({escape_html(doc['category'])})</span></p>
        {f"<p style='white-space:pre-wrap;'>{escape_html(doc['description'])}</p>" if doc.get('description') else ''}
        {f"<p>Primary link: <a href='{escape_html(primary_link)}'>{escape_html(primary_link)}</a></p>" if primary_link else ''}
        <p><strong>Submitter:</strong> {escape_html(doc.get('submitter_name') or '(no name)')}
        &lt;{escape_html(doc['submitter_email'])}&gt;</p>
        <hr>
        <p><a href="{site_url}/admin/community-sources">Review in admin</a> (paste your admin token)</p>
    """
    _fire_admin_notification(notify_subject, notify_html)

    return {"source_id": source_id, "status": "pending"}


@api_router.get("/community-sources")
async def list_community_sources(
    category: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 200,
):
    """Public: list approved + visible community sources. Optional
    category filter + substring search on name/description/tags."""
    query: dict = {"status": "approved", "is_hidden": {"$ne": True}}
    if category:
        if category not in COMMUNITY_SOURCE_CATEGORIES:
            raise HTTPException(status_code=400, detail="invalid category")
        query["category"] = category
    if q:
        pattern = re.escape(q.strip())
        if pattern:
            query["$or"] = [
                {"name": {"$regex": pattern, "$options": "i"}},
                {"description": {"$regex": pattern, "$options": "i"}},
                {"coverage_tags": {"$elemMatch": {"$regex": pattern, "$options": "i"}}},
            ]
    cursor = db.community_sources.find(query, {"_id": 0}).sort("name", 1).limit(limit)
    items = await cursor.to_list(limit)
    return {"count": len(items), "items": [_public_source_projection(d) for d in items]}


@api_router.get("/community-sources/{source_id}")
async def get_community_source(source_id: str):
    """Public: fetch a single approved + visible community source by id."""
    doc = await db.community_sources.find_one(
        {"source_id": source_id, "status": "approved", "is_hidden": {"$ne": True}},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Community source not found")
    return _public_source_projection(doc)


@api_router.get("/admin/community-sources")
async def admin_list_community_sources(
    request: Request,
    token: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 200,
):
    """Admin: list community sources for the moderation queue.
    Defaults to status=pending. Returns full docs incl. submitter_email."""
    _check_admin(request, token)
    query: dict = {}
    if status_filter:
        if status_filter not in COMMUNITY_SOURCE_STATUSES:
            raise HTTPException(status_code=400, detail="invalid status filter")
        query["status"] = status_filter
    else:
        query["status"] = "pending"
    cursor = db.community_sources.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(limit)
    return {"count": len(items), "items": items}


@api_router.post("/admin/community-sources/{source_id}/review")
async def admin_review_community_source(
    source_id: str,
    body: CommunitySourceAdminUpdate,
    request: Request,
    token: Optional[str] = None,
):
    """Admin: approve / reject / hide / unhide a community source.
    Optionally edit name/description/category at review time."""
    _check_admin(request, token)
    if body.status not in COMMUNITY_SOURCE_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(COMMUNITY_SOURCE_STATUSES)}")

    existing = await db.community_sources.find_one({"source_id": source_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Community source not found")

    updates: dict = {
        "status": body.status,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "admin_notes": (body.admin_notes or "").strip()[:1000] or None,
    }
    # In-place edits at review time (correct typos, sharpen descriptions).
    if body.patch_name:
        new_name = body.patch_name.strip()
        if len(new_name) < 3 or len(new_name) > 80:
            raise HTTPException(status_code=400, detail="Patched name must be 3-80 characters")
        updates["name"] = new_name
        updates["slug"] = _slugify(new_name)
    if body.patch_description is not None:
        new_desc = body.patch_description.strip()
        if len(new_desc) > 500:
            raise HTTPException(status_code=400, detail="Patched description too long")
        updates["description"] = new_desc
    if body.patch_category:
        if body.patch_category not in COMMUNITY_SOURCE_CATEGORIES:
            raise HTTPException(status_code=400, detail="invalid category in patch")
        updates["category"] = body.patch_category

    # Setting status back to "approved" should clear any prior auto-hide.
    if body.status == "approved":
        updates["is_hidden"] = False
        updates["auto_hidden_at"] = None

    await db.community_sources.update_one({"source_id": source_id}, {"$set": updates})
    return {"source_id": source_id, "status": body.status}


@api_router.delete("/admin/community-sources/{source_id}")
async def admin_delete_community_source(
    source_id: str,
    request: Request,
    token: Optional[str] = None,
):
    """Admin: permanently delete a community source (and any related
    reports). The "remove in one click" requirement."""
    _check_admin(request, token)
    r = await db.community_sources.delete_one({"source_id": source_id})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Community source not found")
    # Cascade: drop any reports filed against this creator so they don't
    # clutter the report queue with orphaned entries.
    await db.reports.delete_many({"target_type": "creator", "target_id": source_id})
    return {"deleted": True, "source_id": source_id}


@api_router.delete("/admin/events/{event_id}")
async def admin_force_delete_event(
    event_id: str,
    request: Request,
    token: Optional[str] = None,
):
    """Admin: force-delete any event regardless of organizer. Cascades
    to comments and reports filed against the event so we don't leave
    orphans in the moderation queue.

    Tickets are intentionally NOT deleted — they carry payment history
    that needs to survive a moderation action for accounting. They're
    flagged as `event_deleted=True` so the my-tickets page can render
    them as "this event was removed" without crashing on the missing
    parent."""
    _check_admin(request, token)

    existing = await db.events.find_one(
        {"event_id": event_id},
        {"_id": 0, "title": 1, "organizer_id": 1, "source": 1},
    )
    if not existing:
        raise HTTPException(status_code=404, detail="Event not found")

    await db.events.delete_one({"event_id": event_id})
    # Comments collection stores event comments with target_type="event".
    deleted_comments = await db.comments.delete_many(
        {"target_id": event_id, "target_type": "event"}
    )
    deleted_reports = await db.reports.delete_many(
        {"target_type": "event", "target_id": event_id}
    )
    # Flag any tickets so the user can still see them in their dashboard.
    flagged_tickets = await db.tickets.update_many(
        {"event_id": event_id},
        {"$set": {"event_deleted": True, "event_deleted_at": datetime.now(timezone.utc).isoformat()}},
    )

    return {
        "deleted": True,
        "event_id": event_id,
        "title": existing.get("title"),
        "cascade": {
            "comments_removed": deleted_comments.deleted_count,
            "reports_removed": deleted_reports.deleted_count,
            "tickets_flagged": flagged_tickets.modified_count,
        },
    }


# ============= LOCAL NEWS =============

@api_router.get("/news")
async def get_news(limit: int = 20):
    """Recent local-area news headlines (Google News RSS, refreshed daily)."""
    cursor = db.news.find({}, {"_id": 0}).sort("published_at", -1).limit(limit)
    items = await cursor.to_list(limit)
    return items


# ============= ADMIN: INGESTION TRIGGER =============
# Gate with a simple shared secret in the X-Admin-Token header. Set ADMIN_TOKEN
# in Render env vars. Useful for manually triggering an ingestion run during
# the pilot before the daily cron has fired, or after fixing data.

def _fire_admin_notification(subject: str, html: str, text: str = "") -> None:
    """Schedule an admin notification email off-thread so the user's
    HTTP response isn't held up by SMTP. Errors are swallowed inside
    email_helper.notify_admin — this never raises.

    Usage: from any async route, after a user-submitted insert succeeds,
    call this and continue. The notification fires in the background
    and the user gets their normal success response immediately.

    Reads ADMIN_NOTIFY_EMAIL from env; no-ops if unset, so dev / unconfigured
    deploys don't crash."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(_email_helper.notify_admin, subject, html, text))
    except RuntimeError:
        # No running event loop (sync context — unlikely in our FastAPI
        # routes but defensive). Fall back to a direct blocking call.
        _email_helper.notify_admin(subject, html, text)


def _check_admin(request: Request, token_query: Optional[str]):
    """Validate the admin token from header OR ?token= query param.
    Query param support makes it easy to test from the Swagger /docs UI."""
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN not configured")
    provided = request.headers.get("X-Admin-Token") or token_query
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid admin token")


@api_router.post("/admin/ingest")
async def admin_trigger_ingest(request: Request, token: Optional[str] = None):
    """Trigger an ingestion run. Pass token via ?token=... or X-Admin-Token header."""
    _check_admin(request, token)
    from ingestion.runner import run_all
    summary = await run_all()
    return summary


@api_router.get("/admin/ingestion-runs")
async def admin_get_ingestion_runs(request: Request, token: Optional[str] = None, limit: int = 20):
    """Recent ingestion run history for monitoring."""
    _check_admin(request, token)
    runs = await db.ingestion_runs.find({}, {"_id": 0}).sort("started_at", -1).to_list(limit)
    return runs


@api_router.get("/admin/test-yelp-chains")
async def admin_test_yelp_chains(request: Request, token: Optional[str] = None):
    """Debug: run the explicit chain searches and return per-term diagnostics
    (HTTP status, raw business names returned, names that survived our match
    filter). Tells us exactly where chain detection is breaking."""
    _check_admin(request, token)
    from ingestion import yelp
    return await yelp.debug_chain_searches()


@api_router.get("/admin/find-duplicates")
async def admin_find_duplicates(request: Request, token: Optional[str] = None):
    """Find events that look like duplicates by either:
      - coordinates (2dp) + same hour
      - day + similar lat (1dp) — catches venue geocode disagreements

    Shows the actual stored title pairs and dedup keys so we can see why
    the dedup didn't catch them."""
    _check_admin(request, token)

    pipeline = [
        {"$match": {"_source": {"$exists": True}}},
        {"$addFields": {
            "lat_round1": {"$round": ["$latitude", 1]},
            "lon_round1": {"$round": ["$longitude", 1]},
            "date_day": {"$substr": ["$start_date", 0, 10]},
        }},
        # Group by day + 1-decimal lat/lon (~11km) so we cast a wide net for
        # things that might be the same venue with disagreed-upon geocoding.
        {"$group": {
            "_id": {
                "lat": "$lat_round1",
                "lon": "$lon_round1",
                "day": "$date_day",
            },
            "count": {"$sum": 1},
            "events": {"$push": {
                "title": "$title",
                "source": "$_source",
                "event_id": "$event_id",
                "lat": "$latitude",
                "lon": "$longitude",
                "start_date": "$start_date",
                "dedup_key": "$_dedup_key",
                "loc_dedup_key": "$_loc_dedup_key",
                "set_dedup_key": "$_set_dedup_key",
            }},
        }},
        {"$match": {"count": {"$gt": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 30},
    ]
    duplicates = []
    async for group in db.events.aggregate(pipeline):
        duplicates.append({
            "lat_round1": group["_id"]["lat"],
            "lon_round1": group["_id"]["lon"],
            "day": group["_id"]["day"],
            "count": group["count"],
            "events": group["events"],
        })
    return {
        "duplicate_groups_found": len(duplicates),
        "groups": duplicates,
    }


@api_router.get("/admin/test-yelp-full")
async def admin_test_yelp_full(request: Request, token: Optional[str] = None):
    """Debug: run the full Yelp restaurant fetch (all 3 passes) and report
    how many businesses came from each pass, the deduped total, and how
    many got tagged as chains/markets/food_trucks. Confirms whether the
    chain pass is actually reaching the unified candidate list."""
    _check_admin(request, token)
    from ingestion import yelp
    return await yelp.debug_full_fetch()


@api_router.get("/admin/test-osm")
async def admin_test_osm(request: Request, token: Optional[str] = None):
    """Debug: run only the OSM Overpass fetch and return rich diagnostics
    (HTTP status, byte count, raw element count, normalization stats,
    plus a sample of records). Does not touch the database."""
    _check_admin(request, token)
    from ingestion import osm_attractions
    return await osm_attractions.fetch_attractions_with_debug()


@api_router.get("/admin/data-counts")
async def admin_data_counts(request: Request, token: Optional[str] = None):
    """Quick diagnostic: counts per collection, broken down by source.
    Useful to confirm OSM/Yelp/Ticketmaster ingestion actually wrote records."""
    _check_admin(request, token)
    collections = ["events", "restaurants", "food_trucks", "attractions", "churches", "ingestion_runs"]
    out: Dict[str, Any] = {}
    for col in collections:
        total = await db[col].count_documents({})
        by_source: Dict[str, int] = {}
        async for r in db[col].aggregate([
            {"$group": {"_id": "$_source", "count": {"$sum": 1}}}
        ]):
            label = r["_id"] or "user_submitted"
            by_source[label] = r["count"]
        out[col] = {"total": total, "by_source": by_source}

    # Chain breakdown for restaurants — sanity-check the chain ingestion
    chain_count = await db.restaurants.count_documents({"is_chain": True})
    independent_count = await db.restaurants.count_documents(
        {"$or": [{"is_chain": False}, {"is_chain": {"$exists": False}}]}
    )
    out["restaurants"]["chains"] = chain_count
    out["restaurants"]["independents"] = independent_count

    # Sample chain names so we can see WHAT got tagged as chains
    chain_sample = await db.restaurants.find(
        {"is_chain": True}, {"_id": 0, "name": 1}
    ).limit(30).to_list(30)
    out["restaurants"]["chain_sample"] = [r["name"] for r in chain_sample]

    return out


# ============= BULK EVENT IMPORT =============
# Admin tool for getting many events into the DB at once without
# clicking through /create-event N times. The expected workflow:
# - Admin gathers event info from wherever (Instagram captions, venue
#   websites, hand-typed notes)
# - Admin (or Claude) shapes it into a JSON array
# - Paste, submit, done.
# Auth: admin token (no user-login required); attributes events to
# "system_admin" rather than a real user_id so the import is traceable.


class BulkEventItem(BaseModel):
    """A single event in a bulk-import payload. Mirrors EventCreate but
    loosens optional fields so admins don't have to pad lat/lng or
    zip for every row."""
    title: str
    description: str = ""
    category: str = "other"
    start_date: datetime
    end_date: Optional[datetime] = None
    location_name: str = ""
    address: str = ""
    city: str = "Wilmington"
    state: str = "NC"
    zip_code: str = ""
    latitude: float = 34.2257
    longitude: float = -77.9447
    image_url: Optional[str] = None
    external_url: Optional[str] = None  # link out to original source if applicable
    tags: List[str] = []
    mood_tags: List[str] = []
    source: Optional[str] = None  # e.g. "manual", "instagram", "venue_website"
    organizer_name: Optional[str] = None  # for events where the venue/org is the organizer


class BulkEventRequest(BaseModel):
    events: List[BulkEventItem]
    dry_run: bool = False  # if True, validate + count but don't write


@api_router.post("/admin/events/bulk")
async def admin_bulk_events(
    body: BulkEventRequest,
    request: Request,
    token: Optional[str] = None,
):
    """Bulk-create events from a JSON array. Returns counts + any
    per-row errors so the admin UI can show what succeeded and what
    needs fixing."""
    _check_admin(request, token)

    if not body.events:
        raise HTTPException(status_code=400, detail="events array is required and non-empty")

    inserted: list[str] = []
    skipped: list[dict] = []

    for idx, item in enumerate(body.events):
        try:
            # Duplicate detection — same title + start_date within 12h +
            # coordinates within ~0.005 deg. Means re-running the same
            # JSON payload is safe and won't double-insert.
            start_iso = item.start_date.isoformat()
            window_low = (item.start_date - timedelta(hours=12)).isoformat()
            window_high = (item.start_date + timedelta(hours=12)).isoformat()
            dup_lat = item.latitude or 0
            dup_lng = item.longitude or 0
            existing = await db.events.find_one(
                {
                    "title": item.title.strip(),
                    "start_date": {"$gte": window_low, "$lte": window_high},
                    "latitude": {"$gte": dup_lat - 0.005, "$lte": dup_lat + 0.005},
                    "longitude": {"$gte": dup_lng - 0.005, "$lte": dup_lng + 0.005},
                },
                {"_id": 0, "event_id": 1},
            )
            if existing:
                skipped.append({
                    "index": idx,
                    "title": item.title,
                    "error": f"Duplicate of existing event {existing.get('event_id')}",
                })
                continue

            event_id = f"event_{uuid.uuid4().hex[:12]}"
            doc = {
                "event_id": event_id,
                "title": item.title,
                "description": item.description or "",
                "category": item.category,
                "start_date": start_iso,
                "end_date": item.end_date.isoformat() if item.end_date else None,
                "location_name": item.location_name or "",
                "address": item.address or "",
                "city": item.city or "Wilmington",
                "state": item.state or "NC",
                "zip_code": item.zip_code or "",
                "latitude": item.latitude,
                "longitude": item.longitude,
                "image_url": item.image_url,
                "external_url": item.external_url,
                "is_paid": False,
                "ticket_price": None,
                "discount_percentage": None,
                "discounted_price": None,
                "total_tickets": None,
                "tickets_sold": 0,
                "is_promoted": False,
                "promotion_expires": None,
                "tags": item.tags or [],
                "mood_tags": item.mood_tags or [],
                "organizer_id": "system_admin",
                "organizer_name": item.organizer_name or "Local",
                "organizer_type": "external",
                "source": item.source or "manual",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "_bulk_import": True,
            }
            if body.dry_run:
                inserted.append(event_id)
                continue
            await db.events.insert_one(doc)
            inserted.append(event_id)
        except Exception as e:
            skipped.append({"index": idx, "title": item.title, "error": str(e)})

    return {
        "dry_run": body.dry_run,
        "attempted": len(body.events),
        "inserted": len(inserted),
        "skipped": len(skipped),
        "errors": skipped,
        "inserted_ids": inserted if body.dry_run else inserted[:50],
    }


@api_router.post("/admin/run-attractions")
async def admin_run_attractions(request: Request, token: Optional[str] = None):
    """Re-run JUST the attractions ingester. Useful when OSM Overpass was
    rate-limited during a full ingestion run and we need to retry that
    one piece without re-fetching everything else."""
    _check_admin(request, token)
    from ingestion.runner import ingest_attractions, _get_db
    db_local = _get_db()
    return await ingest_attractions(db_local)


@api_router.post("/admin/run-news")
async def admin_run_news(request: Request, token: Optional[str] = None):
    """Re-run JUST the news ingester."""
    _check_admin(request, token)
    from ingestion.runner import ingest_news, _get_db
    db_local = _get_db()
    return await ingest_news(db_local)


@api_router.post("/admin/run-churches")
async def admin_run_churches(request: Request, token: Optional[str] = None):
    """Re-run JUST the OSM churches ingester."""
    _check_admin(request, token)
    from ingestion.runner import ingest_churches, _get_db
    db_local = _get_db()
    return await ingest_churches(db_local)


@api_router.post("/admin/wipe-seed-community")
async def admin_wipe_seed_community(request: Request, token: Optional[str] = None):
    """Delete the NYC mockup forum posts that were inserted by /api/seed.
    Identified by post_id starting with 'post_demo_' OR author_id 'system'.
    Real user-submitted posts (real account ids) are preserved."""
    _check_admin(request, token)
    result = await db.forum_posts.delete_many({
        "$or": [
            {"post_id": {"$regex": "^post_demo_"}},
            {"author_id": "system"},
        ]
    })
    return {"deleted": result.deleted_count}


@api_router.post("/admin/reset-external")
async def admin_reset_external(request: Request, token: Optional[str] = None):
    """Wipe all externally-ingested records (events, restaurants, attractions)
    so a fresh ingestion run will re-import them with the latest schema.
    User-submitted records (no `_source` field) are NOT touched."""
    _check_admin(request, token)
    events_result = await db.events.delete_many({"_source": {"$exists": True}})
    restaurants_result = await db.restaurants.delete_many({"_source": {"$exists": True}})
    attractions_result = await db.attractions.delete_many({"_source": {"$exists": True}})
    food_trucks_result = await db.food_trucks.delete_many({"_source": {"$exists": True}})
    churches_result = await db.churches.delete_many({"_source": {"$exists": True}})
    return {
        "events_deleted": events_result.deleted_count,
        "restaurants_deleted": restaurants_result.deleted_count,
        "attractions_deleted": attractions_result.deleted_count,
        "food_trucks_deleted": food_trucks_result.deleted_count,
        "churches_deleted": churches_result.deleted_count,
    }


# Include all routers
app.include_router(api_router)
app.include_router(auth_router)
app.include_router(events_router)
app.include_router(foodtrucks_router)
app.include_router(payments_router)
app.include_router(ai_router)
app.include_router(flash_deals_router)

# Import and setup new feature routers
from routes import restaurants, attractions, community, gamification, subscriptions, churches

restaurants_router = restaurants.setup_routes(db, calculate_distance, get_current_user, get_optional_user)
attractions_router = attractions.setup_routes(db, calculate_distance, get_current_user, get_optional_user)
community_router = community.setup_routes(db, calculate_distance, get_current_user, get_optional_user)
gamification_router = gamification.setup_routes(db, calculate_distance, get_current_user, get_optional_user)
subscriptions_router = subscriptions.setup_routes(db, calculate_distance, get_current_user, get_optional_user)
churches_router = churches.setup_routes(db, calculate_distance, get_current_user, get_optional_user)

app.include_router(restaurants_router)
app.include_router(attractions_router)
app.include_router(community_router)
app.include_router(gamification_router)
app.include_router(subscriptions_router)
app.include_router(churches_router)

# CORS: read allowed origins from env (comma-separated). Use "*" only in dev.
# Note: `allow_credentials=True` with `allow_origins=["*"]` is invalid per CORS spec,
# so we disable credentials when wildcard is used.
_cors_raw = os.environ.get("CORS_ORIGINS", "*").strip()
if _cors_raw == "*":
    _cors_origins: List[str] = ["*"]
    _cors_credentials = False
else:
    _cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
    _cors_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_credentials=_cors_credentials,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
