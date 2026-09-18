"""Stripe payments, webhook, and post-payment confirmation email."""
import os
import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
import resend

from core import (
    db, logger, CheckoutRequest, CheckoutResponse,
    get_current_user, get_sender_email,
    apply_credits_to_price, deduct_credits, maybe_pay_referral_bonus,
)
from routers.generation import trigger_generation_if_needed

router = APIRouter(prefix="/api")


async def send_order_confirmation_email(assignment_id: str):
    """Send order confirmation to the student after successful payment."""
    try:
        assignment = await db.assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not assignment:
            return
        user = await db.users.find_one({"id": assignment["user_id"]}, {"_id": 0})
        if not user:
            return

        api_key = os.environ.get("RESEND_API_KEY", "")
        if not api_key or api_key.startswith("re_placeholder"):
            logger.warning(f"Resend not configured; skipping confirmation email for {assignment_id}")
            return

        resend.api_key = api_key
        sender = await get_sender_email()

        title = assignment.get("title", "Your assignment")
        word_count = assignment.get("word_count", 0)
        price = assignment.get("final_price", 0)
        student_name = user.get("name", "there")
        student_email = user["email"]

        html = f"""
        <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; color: #1a2842;">
          <h2 style="color: #1a2842; border-bottom: 2px solid #1a2842; padding-bottom: 8px;">Payment received — AIScholar</h2>
          <p>Hi {student_name},</p>
          <p>Thanks for your order. We've received your payment and our AI has started generating your learning materials.</p>
          <table style="width:100%; border-collapse: collapse; margin: 20px 0; font-family: Arial, sans-serif; font-size: 14px;">
            <tr><td style="padding:10px; background:#f5f1e8; width: 35%;"><b>Assignment</b></td><td style="padding:10px; background:#f5f1e8;">{title}</td></tr>
            <tr><td style="padding:10px;"><b>Word count</b></td><td style="padding:10px;">{word_count:,} words</td></tr>
            <tr><td style="padding:10px; background:#f5f1e8;"><b>Amount paid</b></td><td style="padding:10px; background:#f5f1e8;">${price:.2f} USD</td></tr>
            <tr><td style="padding:10px;"><b>Order ID</b></td><td style="padding:10px; font-family: monospace;">{assignment_id[:8]}</td></tr>
          </table>
          <p><b>What's next?</b> Our AI is drafting your outline, reference draft, and writing tips right now. Longer assignments can take a few minutes — you'll see everything in your dashboard as soon as it's ready.</p>
          <p style="margin-top: 24px;">Please be patient — quality writing takes a moment. You can safely close this page and come back later.</p>
          <p style="color: #666; font-size: 12px; margin-top: 32px; border-top: 1px solid #ddd; padding-top: 12px;">
            — The AIScholar Team<br/>
            <i>Remember: AIScholar materials are learning references. Always write your final version in your own voice.</i>
          </p>
        </div>
        """
        params = {
            "from": sender,
            "to": [student_email],
            "subject": f"Order confirmed — {title[:60]}",
            "html": html,
        }
        email = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Order confirmation sent for assignment {assignment_id}: {email}")
    except Exception as e:
        logger.exception(f"Failed to send confirmation email for {assignment_id}: {e}")


@router.post("/payments/checkout", response_model=CheckoutResponse)
async def create_checkout(data: CheckoutRequest, request: Request, user: dict = Depends(get_current_user)):
    assignment = await db.assignments.find_one({"id": data.assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment["status"] == "paid":
        raise HTTPException(status_code=400, detail="Assignment already paid")

    try:
        from emergentintegrations.payments.stripe.checkout import (
            StripeCheckout, CheckoutSessionRequest, CheckoutSessionResponse,
        )
        api_key = os.environ.get("STRIPE_API_KEY")
        host_url = str(request.base_url).rstrip("/")
        webhook_url = f"{host_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)

        origin = data.origin_url.rstrip("/")
        success_url = f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/dashboard"

        # Apply user credits (min $0.50 charge)
        base_price = float(assignment["final_price"])
        charge_amount, credits_used = await apply_credits_to_price(user["id"], base_price)

        checkout_request = CheckoutSessionRequest(
            amount=charge_amount,
            currency="usd",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "assignment_id": data.assignment_id,
                "user_id": user["id"],
                "user_email": user["email"],
                "credits_applied": str(credits_used),
            },
        )
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)

        await db.payment_transactions.insert_one({
            "id": str(uuid.uuid4()),
            "session_id": session.session_id,
            "assignment_id": data.assignment_id,
            "user_id": user["id"],
            "amount": charge_amount,
            "credits_applied": credits_used,
            "currency": "usd",
            "status": "pending",
            "payment_status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return CheckoutResponse(url=session.url, session_id=session.session_id)
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        raise HTTPException(status_code=500, detail=f"Checkout failed: {str(e)}")


@router.get("/payments/attempts/{assignment_id}")
async def get_payment_attempts(assignment_id: str, user: dict = Depends(get_current_user)):
    """Number of prior (non-paid) checkout attempts, so UI can render 'Retry Payment' vs 'Pay'."""
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    count = await db.payment_transactions.count_documents({"assignment_id": assignment_id, "user_id": user["id"]})
    return {"attempts": count, "assignment_status": assignment["status"]}


@router.get("/payments/status/{session_id}")
async def get_payment_status(
    session_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    try:
        from emergentintegrations.payments.stripe.checkout import StripeCheckout
        api_key = os.environ.get("STRIPE_API_KEY")
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url="")
        status = await stripe_checkout.get_checkout_status(session_id)

        transaction = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})

        if transaction and status.payment_status == "paid" and transaction.get("payment_status") != "paid":
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"status": "completed", "payment_status": "paid"}},
            )
            if transaction.get("assignment_id"):
                await db.assignments.update_one(
                    {"id": transaction["assignment_id"]},
                    {"$set": {"status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                # Deduct any credits used at checkout
                credits_used = float(transaction.get("credits_applied") or 0)
                if credits_used > 0:
                    await deduct_credits(transaction["user_id"], credits_used)
                await trigger_generation_if_needed(transaction["assignment_id"], background_tasks)
                background_tasks.add_task(send_order_confirmation_email, transaction["assignment_id"])
                background_tasks.add_task(maybe_pay_referral_bonus, transaction["user_id"])

        return {
            "status": status.status,
            "payment_status": status.payment_status,
            "amount_total": status.amount_total,
            "currency": status.currency,
            "assignment_id": transaction.get("assignment_id") if transaction else None,
        }
    except Exception as e:
        logger.error(f"Payment status error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get payment status: {str(e)}")


@router.post("/webhook/stripe")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        from emergentintegrations.payments.stripe.checkout import StripeCheckout
        api_key = os.environ.get("STRIPE_API_KEY")
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url="")

        body = await request.body()
        signature = request.headers.get("Stripe-Signature")
        webhook_response = await stripe_checkout.handle_webhook(body, signature)

        if webhook_response.payment_status == "paid":
            session_id = webhook_response.session_id
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"status": "completed", "payment_status": "paid"}},
            )
            transaction = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
            if transaction and transaction.get("assignment_id"):
                assignment = await db.assignments.find_one({"id": transaction["assignment_id"]}, {"_id": 0})
                was_unpaid = assignment and assignment.get("status") != "paid" and assignment.get("status") != "completed"
                await db.assignments.update_one(
                    {"id": transaction["assignment_id"]},
                    {"$set": {"status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                credits_used = float(transaction.get("credits_applied") or 0)
                if credits_used > 0 and was_unpaid:
                    await deduct_credits(transaction["user_id"], credits_used)
                await trigger_generation_if_needed(transaction["assignment_id"], background_tasks)
                if was_unpaid:
                    background_tasks.add_task(send_order_confirmation_email, transaction["assignment_id"])
                    background_tasks.add_task(maybe_pay_referral_bonus, transaction["user_id"])

        return {"status": "received"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}
