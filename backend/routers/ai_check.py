"""AI-check orders (manual/reviewer) + Rewrite Coach + Admin review."""
import os
import uuid
import base64
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel
import resend

from core import (
    db, logger, get_current_user, require_admin,
    storage_put, storage_get, MIME_BY_EXT, APP_STORAGE_PREFIX,
    get_sender_email,
)
from routers.generation import REWRITE_COACH_SYSTEM, _parse_ai_json

router = APIRouter(prefix="/api")

AI_CHECK_PRICES = {"originality": 10.0, "turnitin": 15.0}


class RewriteAnalyzeRequest(BaseModel):
    text: str
    mode: Optional[str] = "draft"


@router.post("/rewrite-coach/analyze")
async def rewrite_coach_analyze(data: RewriteAnalyzeRequest, user: dict = Depends(get_current_user)):
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    if len(text) > 200000:
        text = text[:200000]
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"rewrite-coach-{user['id']}-{uuid.uuid4().hex[:8]}",
            system_message=REWRITE_COACH_SYSTEM,
        ).with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=f"Analyze this text:\n\n{text}"))
        parsed = _parse_ai_json(response) or {}
        return {
            "summary": parsed.get("summary", ""),
            "ai_likelihood": int(parsed.get("ai_likelihood", 50)) if str(parsed.get("ai_likelihood", "")).isdigit() else parsed.get("ai_likelihood", 50),
            "issues": (parsed.get("issues", []) or [])[:15],
        }
    except Exception as e:
        logger.exception(f"Rewrite coach error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


class AICheckOrderRequest(BaseModel):
    assignment_id: str
    tier: str
    text_to_check: str
    origin_url: str


class AICheckOrderResponse(BaseModel):
    url: str
    session_id: str
    order_id: str


async def send_ai_check_email(order_id: str):
    try:
        order = await db.ai_check_orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            return
        owner_email = os.environ.get("OWNER_EMAIL")
        api_key = os.environ.get("RESEND_API_KEY")
        sender = await get_sender_email()
        if not (api_key and owner_email) or api_key.startswith("re_placeholder"):
            await db.ai_check_orders.update_one({"id": order_id}, {"$set": {"email_status": "skipped_no_key"}})
            return
        resend.api_key = api_key
        tier_label = "Turnitin" if order["tier"] == "turnitin" else "Originality.ai"
        student_name = order.get("student_name", "Unknown")
        student_email = order.get("student_email", "unknown@example.com")
        assignment_title = order.get("assignment_title", "Untitled")
        word_count = order.get("word_count", 0)
        text = order.get("text_to_check", "")

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <h2 style="color: #1a2842;">New AI Check Order — {tier_label}</h2>
          <table style="width:100%; border-collapse: collapse; margin: 16px 0;">
            <tr><td style="padding:8px; background:#f5f1e8;"><b>Order ID</b></td><td style="padding:8px; background:#f5f1e8;">{order_id}</td></tr>
            <tr><td style="padding:8px;"><b>Tier</b></td><td style="padding:8px;">{tier_label} (${AI_CHECK_PRICES[order['tier']]:.2f})</td></tr>
            <tr><td style="padding:8px; background:#f5f1e8;"><b>Student</b></td><td style="padding:8px; background:#f5f1e8;">{student_name} &lt;{student_email}&gt;</td></tr>
            <tr><td style="padding:8px;"><b>Assignment</b></td><td style="padding:8px;">{assignment_title}</td></tr>
            <tr><td style="padding:8px; background:#f5f1e8;"><b>Word count</b></td><td style="padding:8px; background:#f5f1e8;">{word_count}</td></tr>
            <tr><td style="padding:8px;"><b>Payment status</b></td><td style="padding:8px;">PAID</td></tr>
          </table>
          <h3 style="color:#1a2842;">Text submitted for checking</h3>
          <pre style="background:#fafafa; padding:12px; border:1px solid #e0e0e0; white-space: pre-wrap; font-family: Georgia, serif; font-size: 13px;">{text[:50000]}</pre>
          <p style="color:#666; font-size: 12px;">Reply directly to {student_email} with the {tier_label} report.</p>
        </div>
        """
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        params = {
            "from": sender,
            "to": [owner_email],
            "reply_to": student_email,
            "subject": f"[Scholar AI Check] {tier_label} — {student_name} — {assignment_title}",
            "html": html_content,
            "attachments": [{"filename": f"order_{order_id}_text.txt", "content": b64}],
        }
        email = await asyncio.to_thread(resend.Emails.send, params)
        email_id = email.get("id") if isinstance(email, dict) else None
        await db.ai_check_orders.update_one({"id": order_id}, {"$set": {"email_status": "sent", "email_id": email_id}})
    except Exception as e:
        logger.exception(f"Failed to email AI check order {order_id}: {e}")
        await db.ai_check_orders.update_one({"id": order_id}, {"$set": {"email_status": "failed", "email_error": str(e)[:300]}})


@router.post("/ai-check/order", response_model=AICheckOrderResponse)
async def create_ai_check_order(data: AICheckOrderRequest, request: Request, user: dict = Depends(get_current_user)):
    if data.tier not in AI_CHECK_PRICES:
        raise HTTPException(status_code=400, detail="Invalid tier")
    text = (data.text_to_check or "").strip()
    if len(text) < 50:
        raise HTTPException(status_code=400, detail="Text is too short to check")

    assignment = await db.assignments.find_one({"id": data.assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    order_id = str(uuid.uuid4())
    word_count = len(text.split())
    amount = AI_CHECK_PRICES[data.tier]
    now = datetime.now(timezone.utc).isoformat()

    try:
        from emergentintegrations.payments.stripe.checkout import (
            StripeCheckout, CheckoutSessionRequest, CheckoutSessionResponse,
        )
        stripe_api_key = os.environ.get("STRIPE_API_KEY")
        host_url = str(request.base_url).rstrip("/")
        webhook_url = f"{host_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)

        origin = data.origin_url.rstrip("/")
        success_url = f"{origin}/assignment/{data.assignment_id}?ai_check_session={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/assignment/{data.assignment_id}"

        checkout_request = CheckoutSessionRequest(
            amount=amount, currency="usd",
            success_url=success_url, cancel_url=cancel_url,
            metadata={
                "purpose": "ai_check_order",
                "order_id": order_id, "tier": data.tier,
                "assignment_id": data.assignment_id, "user_id": user["id"],
            },
        )
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)

        await db.ai_check_orders.insert_one({
            "id": order_id,
            "user_id": user["id"],
            "student_name": user.get("name", ""),
            "student_email": user["email"],
            "assignment_id": data.assignment_id,
            "assignment_title": assignment.get("title", ""),
            "tier": data.tier,
            "amount": amount,
            "word_count": word_count,
            "text_to_check": text[:80000],
            "status": "pending_payment",
            "session_id": session.session_id,
            "email_status": "not_sent",
            "created_at": now,
        })
        return AICheckOrderResponse(url=session.url, session_id=session.session_id, order_id=order_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"AI check order creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")


@router.get("/ai-check/status/{session_id}")
async def ai_check_status(session_id: str, background_tasks: BackgroundTasks, user: dict = Depends(get_current_user)):
    order = await db.ai_check_orders.find_one(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0, "text_to_check": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] == "pending_payment":
        try:
            from emergentintegrations.payments.stripe.checkout import StripeCheckout
            stripe_checkout = StripeCheckout(api_key=os.environ.get("STRIPE_API_KEY"), webhook_url="")
            stripe_status = await stripe_checkout.get_checkout_status(session_id)
            if stripe_status.payment_status == "paid":
                await db.ai_check_orders.update_one(
                    {"id": order["id"]},
                    {"$set": {"status": "paid", "paid_at": datetime.now(timezone.utc).isoformat()}},
                )
                order["status"] = "paid"
                background_tasks.add_task(send_ai_check_email, order["id"])
        except Exception as e:
            logger.warning(f"Stripe status check failed for {session_id}: {e}")
    return {
        "order_id": order["id"], "tier": order["tier"], "amount": order["amount"],
        "status": order["status"], "email_status": order.get("email_status", "not_sent"),
        "created_at": order.get("created_at"),
    }


@router.get("/ai-check/orders/{assignment_id}")
async def list_ai_check_orders(assignment_id: str, user: dict = Depends(get_current_user)):
    docs = await db.ai_check_orders.find(
        {"user_id": user["id"], "assignment_id": assignment_id},
        {"_id": 0, "text_to_check": 0},
    ).sort("created_at", -1).to_list(50)
    return docs


@router.get("/ai-check/orders/{order_id}/report")
async def download_ai_check_report(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.ai_check_orders.find_one({"id": order_id, "user_id": user["id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") != "completed" or not order.get("report_path"):
        raise HTTPException(status_code=400, detail="Report not ready yet")
    try:
        data, content_type = await asyncio.to_thread(storage_get, order["report_path"])
    except Exception as e:
        logger.exception(f"Report download failed: {e}")
        raise HTTPException(status_code=404, detail="Report file missing")
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{order.get("report_filename", "ai_check_report.pdf")}"'},
    )


# ---------- Admin ----------
@router.get("/admin/ai-check/orders")
async def admin_list_all_orders(status_filter: Optional[str] = None, _admin: dict = Depends(require_admin)):
    query = {}
    if status_filter:
        query["status"] = status_filter
    return await db.ai_check_orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)


@router.get("/admin/ai-check/orders/{order_id}")
async def admin_get_order(order_id: str, _admin: dict = Depends(require_admin)):
    order = await db.ai_check_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def send_report_ready_email(order_id: str):
    try:
        order = await db.ai_check_orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            return
        api_key = os.environ.get("RESEND_API_KEY")
        sender = await get_sender_email()
        if not api_key or api_key.startswith("re_placeholder"):
            return
        resend.api_key = api_key
        tier_label = "Turnitin" if order["tier"] == "turnitin" else "Originality.ai"
        attachments = []
        if order.get("report_path"):
            try:
                content, _ct = await asyncio.to_thread(storage_get, order["report_path"])
                attachments.append({
                    "filename": order.get("report_filename", "report.pdf"),
                    "content": base64.b64encode(content).decode("ascii"),
                })
            except Exception as e:
                logger.warning(f"Report attachment fetch failed: {e}")

        notes = order.get("completion_notes") or ""
        notes_html = f'<p style="background:#fafafa;padding:12px;border-left:3px solid #1a2842;">{notes}</p>' if notes else ""

        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <h2 style="color: #1a2842;">Your {tier_label} report is ready</h2>
          <p>Hi {order.get('student_name','')},</p>
          <p>Your AI-check report for <b>{order.get('assignment_title','')}</b> has been completed. Full PDF attached.</p>
          {notes_html}
          <p style="color:#666; font-size: 12px; margin-top: 24px;">— Scholar Reviewer Team</p>
        </div>
        """
        params = {"from": sender, "to": [order["student_email"]],
                  "subject": f"Your {tier_label} report — {order.get('assignment_title','')}",
                  "html": html, "attachments": attachments}
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logger.exception(f"Failed sending report-ready email for {order_id}: {e}")


@router.post("/admin/ai-check/orders/{order_id}/complete")
async def admin_complete_order(
    order_id: str,
    background_tasks: BackgroundTasks,
    report: UploadFile = File(...),
    notes: str = Form(""),
    _admin: dict = Depends(require_admin),
):
    order = await db.ai_check_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") not in ("paid", "in_progress"):
        raise HTTPException(status_code=400, detail=f"Order not in paid state (current: {order.get('status')})")

    file_ext = Path(report.filename or "report.pdf").suffix.lower() or ".pdf"
    if file_ext not in [".pdf", ".docx", ".doc", ".txt"]:
        raise HTTPException(status_code=400, detail="Report must be PDF, DOCX, DOC, or TXT")
    content = await report.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Report too large (max 25MB)")

    report_id = str(uuid.uuid4())
    storage_path = f"{APP_STORAGE_PREFIX}/reports/{order_id}/{report_id}{file_ext}"
    try:
        put_result = await asyncio.to_thread(
            storage_put, storage_path, content, MIME_BY_EXT.get(file_ext, "application/octet-stream")
        )
        storage_path = put_result.get("path", storage_path)
    except Exception as e:
        logger.exception(f"Report storage upload failed: {e}")
        raise HTTPException(status_code=500, detail="Storage upload failed")

    await db.ai_check_orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "completed",
            "report_filename": report.filename or f"report{file_ext}",
            "report_path": storage_path,
            "completion_notes": notes,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    background_tasks.add_task(send_report_ready_email, order_id)
    return {"status": "completed", "order_id": order_id, "email": "queued"}


@router.post("/admin/ai-check/orders/{order_id}/mark-in-progress")
async def admin_mark_in_progress(order_id: str, _admin: dict = Depends(require_admin)):
    res = await db.ai_check_orders.update_one(
        {"id": order_id, "status": "paid"},
        {"$set": {"status": "in_progress"}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=400, detail="Order not in paid state")
    return {"status": "in_progress"}
