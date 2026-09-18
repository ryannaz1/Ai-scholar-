"""Shared core: config, db, models, auth, pricing, storage, file extraction, logging."""
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import os
import io
import logging
import jwt
import bcrypt
import requests as _requests
from PyPDF2 import PdfReader
from docx import Document

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("aischolar")

# ---------- Mongo ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# ---------- JWT ----------
JWT_SECRET = os.environ.get("JWT_SECRET", "default-secret")
JWT_ALGORITHM = "HS256"
security = HTTPBearer(auto_error=False)

# ---------- Pricing config ----------
PRICE_PER_PAGE = 7.0
WORDS_PER_PAGE = 280
BULK_DISCOUNT_THRESHOLD = 10000
BULK_DISCOUNT_RATE = 0.10

# ---------- Storage ----------
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_STORAGE_PREFIX = "aischolar"
_storage_key: Optional[str] = None

MIME_BY_EXT = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
}


def init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    emergent_key = os.environ.get("EMERGENT_LLM_KEY")
    resp = _requests.post(f"{STORAGE_URL}/init", json={"emergent_key": emergent_key}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def storage_put(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = _requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = _requests.put(
            f"{STORAGE_URL}/objects/{path}",
            headers={"X-Storage-Key": key, "Content-Type": content_type},
            data=data,
            timeout=120,
        )
    resp.raise_for_status()
    return resp.json()


def storage_get(path: str) -> tuple:
    key = init_storage()
    resp = _requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = _requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


# ---------- Models ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    created_at: str


class TokenResponse(BaseModel):
    token: str
    user: UserResponse


class AssignmentCreate(BaseModel):
    title: str
    subject: str
    requirements: str
    word_count: int
    writing_style: Optional[str] = "academic"
    additional_notes: Optional[str] = ""
    assignment_format: Optional[str] = "general"
    concert_structure: Optional[str] = None
    has_conductor: Optional[bool] = None
    citation_style: Optional[str] = "apa"
    ai_model: Optional[str] = "gpt-5.2"


class AssignmentResponse(BaseModel):
    id: str
    user_id: str
    title: str
    subject: str
    requirements: str
    word_count: int
    writing_style: str
    additional_notes: str
    status: str
    price: float
    discount_applied: bool
    final_price: float
    generated_content: Optional[str] = None
    outline: Optional[str] = None
    draft: Optional[str] = None
    writing_tips: Optional[str] = None
    generation_status: Optional[str] = "pending"
    generation_error: Optional[str] = None
    assignment_format: Optional[str] = "general"
    concert_structure: Optional[str] = None
    has_conductor: Optional[bool] = None
    citation_style: Optional[str] = "apa"
    ai_model: Optional[str] = "gpt-5.2"
    outline_regens: Optional[int] = 0
    draft_regens: Optional[int] = 0
    writing_tips_regens: Optional[int] = 0
    outline_regenerated_at: Optional[str] = None
    draft_regenerated_at: Optional[str] = None
    writing_tips_regenerated_at: Optional[str] = None
    outline_previous: Optional[str] = None
    draft_previous: Optional[str] = None
    writing_tips_previous: Optional[str] = None
    course_materials: List[str] = []
    created_at: str
    updated_at: str


class PriceCalculation(BaseModel):
    word_count: int
    base_price: float
    discount_percent: float
    discount_amount: float
    final_price: float
    pages: float


class CheckoutRequest(BaseModel):
    assignment_id: str
    origin_url: str


class CheckoutResponse(BaseModel):
    url: str
    session_id: str


# ---------- Auth helpers ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: str) -> str:
    payload = {"user_id": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["user_id"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def is_admin(user: dict) -> bool:
    owner = (os.environ.get("OWNER_EMAIL") or "").strip().lower()
    return bool(owner) and user.get("email", "").lower() == owner


async def require_admin(user: dict = Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ---------- Pricing ----------
def calculate_price(word_count: int) -> PriceCalculation:
    pages = word_count / WORDS_PER_PAGE
    base_price = pages * PRICE_PER_PAGE
    discount_percent = 0.0
    discount_amount = 0.0
    if word_count >= BULK_DISCOUNT_THRESHOLD:
        discount_percent = BULK_DISCOUNT_RATE * 100
        discount_amount = base_price * BULK_DISCOUNT_RATE
    final_price = base_price - discount_amount
    return PriceCalculation(
        word_count=word_count,
        base_price=round(base_price, 2),
        discount_percent=discount_percent,
        discount_amount=round(discount_amount, 2),
        final_price=round(final_price, 2),
        pages=round(pages, 2),
    )


# ---------- File extraction ----------
async def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return ""


async def extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        return ""


# ---------- Settings (Resend domain etc.) ----------
async def get_app_setting(key: str, default=None):
    doc = await db.app_settings.find_one({"key": key}, {"_id": 0})
    return doc.get("value") if doc else default


async def set_app_setting(key: str, value):
    await db.app_settings.update_one(
        {"key": key},
        {"$set": {"key": key, "value": value, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )


async def get_sender_email() -> str:
    """Prefer DB-configured sender, fall back to env, then Resend default."""
    domain = await get_app_setting("resend_sender_email")
    if domain:
        return domain
    return os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")


# ---------- AI models ----------
# Maps public model IDs to emergentintegrations (provider, model_name) tuples
AI_MODELS = {
    "gpt-5.2": {
        "label": "Balanced (GPT-5.2)",
        "description": "Default — best quality/speed trade-off",
        "provider": "openai",
        "model": "gpt-5.2",
    },
    "gpt-5.4-mini": {
        "label": "Fast (GPT-5.4 Mini)",
        "description": "Quicker turnaround, lighter reasoning",
        "provider": "openai",
        "model": "gpt-5.4-mini",
    },
    "claude-sonnet-4.6": {
        "label": "Premium (Claude Sonnet 4.6)",
        "description": "Higher-quality prose, richer synthesis",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    },
}


def resolve_model(ai_model: Optional[str]) -> tuple:
    cfg = AI_MODELS.get(ai_model or "gpt-5.2") or AI_MODELS["gpt-5.2"]
    return cfg["provider"], cfg["model"]


# ---------- Referral / credit helpers ----------
REFERRAL_BONUS = 5.0  # $5 for both parties when referred user makes first paid order


async def apply_credits_to_price(user_id: str, price: float) -> tuple:
    """Return (final_charge, credits_used). Leaves a $0.50 minimum charge."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "credits": 1})
    credits = float((user or {}).get("credits") or 0)
    if credits <= 0 or price <= 0.50:
        return price, 0.0
    max_usable = max(0.0, price - 0.50)
    used = min(credits, max_usable)
    return round(price - used, 2), round(used, 2)


async def deduct_credits(user_id: str, amount: float):
    if amount <= 0:
        return
    await db.users.update_one({"id": user_id}, {"$inc": {"credits": -amount}})
    await db.credit_ledger.insert_one({
        "user_id": user_id,
        "delta": -amount,
        "reason": "checkout_apply",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def award_credit(user_id: str, amount: float, reason: str):
    await db.users.update_one({"id": user_id}, {"$inc": {"credits": amount}})
    await db.credit_ledger.insert_one({
        "user_id": user_id,
        "delta": amount,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


async def maybe_pay_referral_bonus(user_id: str):
    """When a user completes their FIRST paid assignment, credit both them and their referrer."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or user.get("referral_bonus_paid"):
        return
    # Count paid assignments
    paid_count = await db.assignments.count_documents(
        {"user_id": user_id, "status": {"$in": ["paid", "completed"]}}
    )
    if paid_count < 1:
        return
    referrer_id = user.get("referred_by")
    await db.users.update_one({"id": user_id}, {"$set": {"referral_bonus_paid": True}})
    if referrer_id:
        await award_credit(referrer_id, REFERRAL_BONUS, f"referral_reward_from_{user_id}")
        await award_credit(user_id, REFERRAL_BONUS, "referral_signup_bonus")
        logger.info(f"Referral bonus paid: {referrer_id} <- {user_id}")
