"""Admin-managed application settings (Resend sender/domain)."""
import os
import re
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from core import get_app_setting, set_app_setting, require_admin

router = APIRouter(prefix="/api")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ResendSettings(BaseModel):
    sender_email: Optional[str] = None  # e.g. "orders@yourdomain.com"


@router.get("/settings/resend")
async def get_resend_settings(_admin: dict = Depends(require_admin)):
    sender = await get_app_setting("resend_sender_email")
    api_key = os.environ.get("RESEND_API_KEY", "")
    key_configured = bool(api_key) and not api_key.startswith("re_placeholder")
    return {
        "sender_email": sender or "",
        "fallback_sender_email": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
        "api_key_configured": key_configured,
    }


@router.put("/settings/resend")
async def update_resend_settings(data: ResendSettings, _admin: dict = Depends(require_admin)):
    sender = (data.sender_email or "").strip()
    if sender and not EMAIL_RE.match(sender):
        raise HTTPException(status_code=400, detail="Invalid email format")
    await set_app_setting("resend_sender_email", sender or None)
    return {"status": "saved", "sender_email": sender}
