from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid

from core import (
    db, UserCreate, UserLogin, UserResponse, TokenResponse,
    hash_password, verify_password, create_token, get_current_user, is_admin,
)

router = APIRouter(prefix="/api")


class UserCreateWithRef(UserCreate):
    referral_code: Optional[str] = None


@router.post("/auth/register", response_model=TokenResponse)
async def register(data: UserCreateWithRef):
    existing = await db.users.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    referred_by = None
    if data.referral_code:
        ref = await db.users.find_one({"id": data.referral_code}, {"_id": 0, "id": 1})
        if ref and ref["id"] != user_id:
            referred_by = ref["id"]

    await db.users.insert_one({
        "id": user_id,
        "email": data.email,
        "password": hash_password(data.password),
        "name": data.name,
        "created_at": now,
        "credits": 0.0,
        "referred_by": referred_by,
        "referral_bonus_paid": False,
    })
    return TokenResponse(
        token=create_token(user_id),
        user=UserResponse(id=user_id, email=data.email, name=data.name, created_at=now),
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user or not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(
        token=create_token(user["id"]),
        user=UserResponse(id=user["id"], email=user["email"], name=user["name"], created_at=user["created_at"]),
    )


@router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(id=user["id"], email=user["email"], name=user["name"], created_at=user["created_at"])


@router.get("/auth/me-admin")
async def me_admin(user: dict = Depends(get_current_user)):
    return {"is_admin": is_admin(user), "email": user.get("email")}
