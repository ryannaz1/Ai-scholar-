from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks, Request, Body
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid
import asyncio

from core import (
    db, logger, AssignmentCreate, AssignmentResponse,
    calculate_price, get_current_user,
    storage_put, MIME_BY_EXT, APP_STORAGE_PREFIX,
    extract_text_from_pdf, extract_text_from_docx,
)
from routers.generation import (
    run_generation, run_section_regeneration,
    trigger_generation_if_needed,
    FREE_REGENS_PER_SECTION, REGEN_PRICE, VALID_SECTIONS,
)

router = APIRouter(prefix="/api")


@router.post("/assignments", response_model=AssignmentResponse)
async def create_assignment(data: AssignmentCreate, user: dict = Depends(get_current_user)):
    pricing = calculate_price(data.word_count)
    assignment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "id": assignment_id,
        "user_id": user["id"],
        "title": data.title,
        "subject": data.subject,
        "requirements": data.requirements,
        "word_count": data.word_count,
        "writing_style": data.writing_style,
        "additional_notes": data.additional_notes or "",
        "status": "draft",
        "price": pricing.base_price,
        "discount_applied": pricing.discount_percent > 0,
        "final_price": pricing.final_price,
        "generated_content": None,
        "outline": None,
        "draft": None,
        "writing_tips": None,
        "generation_status": "pending",
        "generation_error": None,
        "assignment_format": data.assignment_format or "general",
        "concert_structure": data.concert_structure,
        "has_conductor": data.has_conductor,
        "citation_style": data.citation_style or "apa",
        "ai_model": data.ai_model or "gpt-5.2",
        "outline_regens": 0,
        "draft_regens": 0,
        "writing_tips_regens": 0,
        "course_materials": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.assignments.insert_one(doc)
    return AssignmentResponse(**{k: v for k, v in doc.items() if k != "_id"})


@router.get("/assignments", response_model=List[AssignmentResponse])
async def get_assignments(user: dict = Depends(get_current_user)):
    rows = await db.assignments.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [AssignmentResponse(**a) for a in rows]


@router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(assignment_id: str, user: dict = Depends(get_current_user)):
    a = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return AssignmentResponse(**a)


@router.post("/assignments/{assignment_id}/duplicate", response_model=AssignmentResponse)
async def duplicate_assignment(assignment_id: str, user: dict = Depends(get_current_user)):
    """Create a fresh, unpaid draft copy of an existing assignment (no content, no materials)."""
    src = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Assignment not found")

    from core import calculate_price
    pricing = calculate_price(src["word_count"])
    new_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": new_id,
        "user_id": user["id"],
        "title": f"{src['title']} (copy)",
        "subject": src["subject"],
        "requirements": src["requirements"],
        "word_count": src["word_count"],
        "writing_style": src.get("writing_style", "academic"),
        "additional_notes": src.get("additional_notes", ""),
        "status": "draft",
        "price": pricing.base_price,
        "discount_applied": pricing.discount_percent > 0,
        "final_price": pricing.final_price,
        "generated_content": None,
        "outline": None,
        "draft": None,
        "writing_tips": None,
        "generation_status": "pending",
        "generation_error": None,
        "assignment_format": src.get("assignment_format", "general"),
        "concert_structure": src.get("concert_structure"),
        "has_conductor": src.get("has_conductor"),
        "citation_style": src.get("citation_style", "apa"),
        "ai_model": src.get("ai_model", "gpt-5.2"),
        "outline_regens": 0,
        "draft_regens": 0,
        "writing_tips_regens": 0,
        "course_materials": [],
        "created_at": now,
        "updated_at": now,
    }
    await db.assignments.insert_one(doc)
    return AssignmentResponse(**{k: v for k, v in doc.items() if k != "_id"})


@router.post("/assignments/{assignment_id}/upload")
async def upload_course_material(
    assignment_id: str,
    file: UploadFile = File(...),
    category: str = Form("course_material"),
    user: dict = Depends(get_current_user),
):
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    valid_categories = ["course_material", "previous_assignment", "requirements"]
    if category not in valid_categories:
        category = "course_material"

    allowed_types = [".pdf", ".docx", ".doc", ".txt"]
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type {file_ext} not allowed")

    file_id = str(uuid.uuid4())
    storage_path = f"{APP_STORAGE_PREFIX}/uploads/{user['id']}/{file_id}{file_ext}"

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    try:
        put_result = await asyncio.to_thread(
            storage_put, storage_path, content, MIME_BY_EXT.get(file_ext, "application/octet-stream")
        )
        storage_path = put_result.get("path", storage_path)
    except Exception as e:
        logger.exception(f"Object storage upload failed: {e}")
        raise HTTPException(status_code=500, detail="File storage temporarily unavailable")

    extracted_text = ""
    if file_ext == ".pdf":
        extracted_text = await extract_text_from_pdf(content)
    elif file_ext == ".docx":
        extracted_text = await extract_text_from_docx(content)
    elif file_ext == ".txt":
        extracted_text = content.decode("utf-8", errors="ignore")

    await db.course_materials.insert_one({
        "id": file_id,
        "assignment_id": assignment_id,
        "user_id": user["id"],
        "filename": file.filename,
        "file_path": storage_path,
        "category": category,
        "extracted_text": extracted_text[:50000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    await db.assignments.update_one({"id": assignment_id}, {"$push": {"course_materials": file_id}})
    return {"id": file_id, "filename": file.filename, "category": category, "status": "uploaded"}


class CourseMaterialItem(BaseModel):
    id: str
    filename: str
    category: str
    created_at: str


@router.get("/assignments/{assignment_id}/materials", response_model=List[CourseMaterialItem])
async def list_materials(assignment_id: str, user: dict = Depends(get_current_user)):
    a = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]})
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    docs = await db.course_materials.find(
        {"assignment_id": assignment_id},
        {"_id": 0, "id": 1, "filename": 1, "category": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(50)
    for d in docs:
        d.setdefault("category", "course_material")
    return [CourseMaterialItem(**d) for d in docs]


@router.post("/assignments/{assignment_id}/generate")
async def generate_content(
    assignment_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment["status"] not in ("paid", "completed"):
        raise HTTPException(status_code=400, detail="Assignment must be paid before generation")
    if assignment.get("generation_status") == "generating":
        return {"status": "generating", "message": "Generation already in progress"}

    background_tasks.add_task(run_generation, assignment_id)
    await db.assignments.update_one(
        {"id": assignment_id},
        {"$set": {"generation_status": "generating", "generation_error": None}},
    )
    return {"status": "generating", "message": "Generation started"}


class RegenerateResponse(BaseModel):
    status: str
    remaining_free: int
    checkout_url: Optional[str] = None
    session_id: Optional[str] = None


@router.post("/assignments/{assignment_id}/regenerate/{section}", response_model=RegenerateResponse)
async def regenerate_section(
    assignment_id: str,
    section: str,
    background_tasks: BackgroundTasks,
    request: Request,
    origin_url: Optional[str] = Body(None, embed=True),
    user: dict = Depends(get_current_user),
):
    if section not in VALID_SECTIONS:
        raise HTTPException(status_code=400, detail="Invalid section")
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment["status"] not in ("paid", "completed"):
        raise HTTPException(status_code=400, detail="Pay for the assignment first")
    if assignment.get("generation_status") == "generating":
        return RegenerateResponse(status="regenerating", remaining_free=0)

    regen_field = f"{section}_regens"
    used = int(assignment.get(regen_field) or 0)
    remaining_free = max(0, FREE_REGENS_PER_SECTION - used)

    if remaining_free > 0:
        await db.assignments.update_one({"id": assignment_id}, {"$set": {"generation_status": "generating"}})
        background_tasks.add_task(run_section_regeneration, assignment_id, section)
        return RegenerateResponse(status="regenerating", remaining_free=remaining_free - 1)

    # Paid regen
    import os
    try:
        from emergentintegrations.payments.stripe.checkout import (
            StripeCheckout, CheckoutSessionRequest, CheckoutSessionResponse,
        )
        stripe_api_key = os.environ.get("STRIPE_API_KEY")
        host_url = str(request.base_url).rstrip("/")
        webhook_url = f"{host_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
        origin = (origin_url or "").rstrip("/") or str(request.base_url).rstrip("/")
        success_url = f"{origin}/assignment/{assignment_id}?regen_session={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/assignment/{assignment_id}"

        checkout_request = CheckoutSessionRequest(
            amount=REGEN_PRICE,
            currency="usd",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "purpose": "regen",
                "assignment_id": assignment_id,
                "section": section,
                "user_id": user["id"],
            },
        )
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)
        await db.regen_orders.insert_one({
            "id": str(uuid.uuid4()),
            "session_id": session.session_id,
            "user_id": user["id"],
            "assignment_id": assignment_id,
            "section": section,
            "amount": REGEN_PRICE,
            "status": "pending_payment",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return RegenerateResponse(
            status="payment_required", remaining_free=0,
            checkout_url=session.url, session_id=session.session_id,
        )
    except Exception as e:
        logger.exception(f"Regen checkout failed: {e}")
        raise HTTPException(status_code=500, detail=f"Could not start checkout: {str(e)}")


@router.get("/assignments/{assignment_id}/regen-status/{session_id}")
async def regen_status(
    assignment_id: str,
    session_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    import os
    order = await db.regen_orders.find_one({"session_id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Regen order not found")
    if order["status"] == "completed":
        return {"status": "already_processed"}
    try:
        from emergentintegrations.payments.stripe.checkout import StripeCheckout
        stripe_checkout = StripeCheckout(api_key=os.environ.get("STRIPE_API_KEY"), webhook_url="")
        stripe_status = await stripe_checkout.get_checkout_status(session_id)
        if stripe_status.payment_status == "paid":
            await db.regen_orders.update_one(
                {"session_id": session_id},
                {"$set": {"status": "completed", "paid_at": datetime.now(timezone.utc).isoformat()}},
            )
            await db.assignments.update_one({"id": assignment_id}, {"$set": {"generation_status": "generating"}})
            background_tasks.add_task(run_section_regeneration, assignment_id, order["section"])
            return {"status": "regenerating", "section": order["section"]}
        return {"status": stripe_status.payment_status}
    except Exception as e:
        logger.exception(f"Regen status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
