"""Admin-managed application settings (Resend sender/domain) + test email."""
import os
import re
import asyncio
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional
import resend

from core import get_app_setting, set_app_setting, require_admin, get_sender_email, logger

router = APIRouter(prefix="/api")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ResendSettings(BaseModel):
    sender_email: Optional[str] = None  # e.g. "orders@yourdomain.com"


class TestEmailRequest(BaseModel):
    to_email: EmailStr


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


@router.post("/settings/resend/test")
async def send_test_email(data: TestEmailRequest, _admin: dict = Depends(require_admin)):
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key or api_key.startswith("re_placeholder"):
        raise HTTPException(status_code=400, detail="RESEND_API_KEY not configured")
    resend.api_key = api_key
    sender = await get_sender_email()
    try:
        result = await asyncio.to_thread(resend.Emails.send, {
            "from": sender,
            "to": [data.to_email],
            "subject": "AIScholar — Resend test email",
            "html": f"""
                <div style="font-family: Georgia, serif; max-width: 500px; color: #1a2842;">
                  <h2 style="color: #1a2842;">Resend is working ✓</h2>
                  <p>This is a test email sent from <b>{sender}</b>.</p>
                  <p style="color: #666; font-size: 12px;">If you received this, your Resend integration is fully wired up and student order confirmations will deliver.</p>
                </div>
            """,
        })
        email_id = result.get("id") if isinstance(result, dict) else None
        return {"status": "sent", "email_id": email_id, "from": sender, "to": data.to_email}
    except Exception as e:
        logger.exception(f"Test email failed: {e}")
        msg = str(e)
        if "domain" in msg.lower() or "verify" in msg.lower():
            raise HTTPException(status_code=400, detail=f"Domain not verified in Resend: {msg}")
        raise HTTPException(status_code=500, detail=f"Send failed: {msg}")
