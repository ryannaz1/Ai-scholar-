from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Request, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict
import uuid
from datetime import datetime, timezone, timedelta
import jwt
import bcrypt
import aiofiles
from PyPDF2 import PdfReader
from docx import Document
import io

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Config
JWT_SECRET = os.environ.get('JWT_SECRET', 'default-secret')
JWT_ALGORITHM = "HS256"

# Pricing Config
PRICE_PER_PAGE = 7.0  # $7 per 280 words
WORDS_PER_PAGE = 280
BULK_DISCOUNT_THRESHOLD = 10000  # 10% discount over 10k words
BULK_DISCOUNT_RATE = 0.10

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")
security = HTTPBearer(auto_error=False)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Upload directory
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ==================== MODELS ====================

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
    course_materials: List[str] = []
    created_at: str
    updated_at: str

class GenerateContentRequest(BaseModel):
    assignment_id: str

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

# ==================== AUTH HELPERS ====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def create_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7)
    }
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

# ==================== PRICING HELPERS ====================

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
        pages=round(pages, 2)
    )

# ==================== FILE EXTRACTION ====================

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
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    except Exception as e:
        logger.error(f"DOCX extraction error: {e}")
        return ""

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/register", response_model=TokenResponse)
async def register(data: UserCreate):
    existing = await db.users.find_one({"email": data.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": data.email,
        "password": hash_password(data.password),
        "name": data.name,
        "created_at": now,
        "credits": 0.0
    }
    
    await db.users.insert_one(user_doc)
    token = create_token(user_id)
    
    return TokenResponse(
        token=token,
        user=UserResponse(id=user_id, email=data.email, name=data.name, created_at=now)
    )

@api_router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin):
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user or not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["id"])
    
    return TokenResponse(
        token=token,
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            name=user["name"],
            created_at=user["created_at"]
        )
    )

@api_router.get("/auth/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        created_at=user["created_at"]
    )

# ==================== PRICING ROUTES ====================

@api_router.post("/pricing/calculate", response_model=PriceCalculation)
async def calculate_pricing(word_count: int = Body(..., embed=True)):
    if word_count <= 0:
        raise HTTPException(status_code=400, detail="Word count must be positive")
    return calculate_price(word_count)

@api_router.get("/pricing/info")
async def get_pricing_info():
    return {
        "price_per_page": PRICE_PER_PAGE,
        "words_per_page": WORDS_PER_PAGE,
        "bulk_discount_threshold": BULK_DISCOUNT_THRESHOLD,
        "bulk_discount_rate": BULK_DISCOUNT_RATE * 100
    }

# ==================== ASSIGNMENT ROUTES ====================

@api_router.post("/assignments", response_model=AssignmentResponse)
async def create_assignment(data: AssignmentCreate, user: dict = Depends(get_current_user)):
    pricing = calculate_price(data.word_count)
    
    assignment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    assignment_doc = {
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
        "course_materials": [],
        "created_at": now,
        "updated_at": now
    }
    
    await db.assignments.insert_one(assignment_doc)
    
    return AssignmentResponse(**{k: v for k, v in assignment_doc.items() if k != "_id"})

@api_router.get("/assignments", response_model=List[AssignmentResponse])
async def get_assignments(user: dict = Depends(get_current_user)):
    assignments = await db.assignments.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [AssignmentResponse(**a) for a in assignments]

@api_router.get("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def get_assignment(assignment_id: str, user: dict = Depends(get_current_user)):
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return AssignmentResponse(**assignment)

@api_router.post("/assignments/{assignment_id}/upload")
async def upload_course_material(
    assignment_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Validate file type
    allowed_types = [".pdf", ".docx", ".doc", ".txt"]
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type {file_ext} not allowed")
    
    # Save file
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    
    content = await file.read()
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(content)
    
    # Extract text
    extracted_text = ""
    if file_ext == ".pdf":
        extracted_text = await extract_text_from_pdf(content)
    elif file_ext == ".docx":
        extracted_text = await extract_text_from_docx(content)
    elif file_ext == ".txt":
        extracted_text = content.decode('utf-8', errors='ignore')
    
    # Store material info
    material_doc = {
        "id": file_id,
        "assignment_id": assignment_id,
        "user_id": user["id"],
        "filename": file.filename,
        "file_path": str(file_path),
        "extracted_text": extracted_text[:50000],  # Limit text
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.course_materials.insert_one(material_doc)
    
    # Update assignment
    await db.assignments.update_one(
        {"id": assignment_id},
        {"$push": {"course_materials": file_id}}
    )
    
    return {"id": file_id, "filename": file.filename, "status": "uploaded"}

# ==================== AI GENERATION ROUTES ====================

@api_router.post("/assignments/{assignment_id}/generate")
async def generate_content(assignment_id: str, user: dict = Depends(get_current_user)):
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    if assignment["status"] != "paid":
        raise HTTPException(status_code=400, detail="Assignment must be paid before generation")
    
    # Get course materials
    materials = await db.course_materials.find(
        {"assignment_id": assignment_id},
        {"_id": 0, "extracted_text": 1, "filename": 1}
    ).to_list(10)
    
    materials_context = "\n\n".join([
        f"--- {m['filename']} ---\n{m['extracted_text'][:10000]}"
        for m in materials
    ])
    
    # Build prompt
    system_message = """You are an expert academic writing assistant. Your role is to help students learn and improve their writing skills by providing:
1. Well-structured outlines and drafts
2. Clear explanations of concepts
3. Proper academic formatting and citations guidance
4. Writing that serves as a learning template

Create content that helps students understand how to approach academic writing. The content should be educational and serve as a guide for the student's own learning.

Important: Generate content that is approximately the requested word count. Use proper academic language, include section headings, and maintain a scholarly tone."""

    user_prompt = f"""Assignment Details:
Title: {assignment['title']}
Subject: {assignment['subject']}
Requirements: {assignment['requirements']}
Word Count Target: {assignment['word_count']} words
Writing Style: {assignment['writing_style']}
Additional Notes: {assignment['additional_notes']}

{"Course Materials Context:" if materials_context else ""}
{materials_context[:15000] if materials_context else "No additional materials provided."}

Please generate a comprehensive academic writing sample that:
1. Follows the requirements exactly
2. Is approximately {assignment['word_count']} words
3. Includes proper structure (introduction, body, conclusion)
4. Uses academic language appropriate for the subject
5. Provides educational value to help the student learn"""

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        chat = LlmChat(
            api_key=api_key,
            session_id=f"assignment-{assignment_id}",
            system_message=system_message
        ).with_model("openai", "gpt-5.2")
        
        user_message = UserMessage(text=user_prompt)
        generated_content = await chat.send_message(user_message)
        
        # Update assignment
        await db.assignments.update_one(
            {"id": assignment_id},
            {
                "$set": {
                    "generated_content": generated_content,
                    "status": "completed",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        return {
            "status": "success",
            "content": generated_content,
            "word_count": len(generated_content.split())
        }
        
    except Exception as e:
        logger.error(f"AI generation error: {e}")
        raise HTTPException(status_code=500, detail=f"Content generation failed: {str(e)}")

# ==================== PAYMENT ROUTES ====================

@api_router.post("/payments/checkout", response_model=CheckoutResponse)
async def create_checkout(data: CheckoutRequest, request: Request, user: dict = Depends(get_current_user)):
    assignment = await db.assignments.find_one({"id": data.assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    if assignment["status"] == "paid":
        raise HTTPException(status_code=400, detail="Assignment already paid")
    
    try:
        from emergentintegrations.payments.stripe.checkout import (
            StripeCheckout, CheckoutSessionRequest, CheckoutSessionResponse
        )
        
        api_key = os.environ.get('STRIPE_API_KEY')
        host_url = str(request.base_url).rstrip('/')
        webhook_url = f"{host_url}/api/webhook/stripe"
        
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url=webhook_url)
        
        origin = data.origin_url.rstrip('/')
        success_url = f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/dashboard"
        
        checkout_request = CheckoutSessionRequest(
            amount=float(assignment["final_price"]),
            currency="usd",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "assignment_id": data.assignment_id,
                "user_id": user["id"],
                "user_email": user["email"]
            }
        )
        
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)
        
        # Create payment transaction record
        transaction_doc = {
            "id": str(uuid.uuid4()),
            "session_id": session.session_id,
            "assignment_id": data.assignment_id,
            "user_id": user["id"],
            "amount": assignment["final_price"],
            "currency": "usd",
            "status": "pending",
            "payment_status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.payment_transactions.insert_one(transaction_doc)
        
        return CheckoutResponse(url=session.url, session_id=session.session_id)
        
    except Exception as e:
        logger.error(f"Checkout error: {e}")
        raise HTTPException(status_code=500, detail=f"Checkout failed: {str(e)}")

@api_router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, user: dict = Depends(get_current_user)):
    try:
        from emergentintegrations.payments.stripe.checkout import StripeCheckout
        
        api_key = os.environ.get('STRIPE_API_KEY')
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url="")
        
        status = await stripe_checkout.get_checkout_status(session_id)
        
        # Update transaction
        transaction = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        
        if transaction and status.payment_status == "paid" and transaction.get("payment_status") != "paid":
            # Update transaction status
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"status": "completed", "payment_status": "paid"}}
            )
            
            # Update assignment status
            if transaction.get("assignment_id"):
                await db.assignments.update_one(
                    {"id": transaction["assignment_id"]},
                    {"$set": {"status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
        
        return {
            "status": status.status,
            "payment_status": status.payment_status,
            "amount_total": status.amount_total,
            "currency": status.currency
        }
        
    except Exception as e:
        logger.error(f"Payment status error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get payment status: {str(e)}")

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    try:
        from emergentintegrations.payments.stripe.checkout import StripeCheckout
        
        api_key = os.environ.get('STRIPE_API_KEY')
        stripe_checkout = StripeCheckout(api_key=api_key, webhook_url="")
        
        body = await request.body()
        signature = request.headers.get("Stripe-Signature")
        
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        
        if webhook_response.payment_status == "paid":
            session_id = webhook_response.session_id
            
            # Update transaction
            await db.payment_transactions.update_one(
                {"session_id": session_id},
                {"$set": {"status": "completed", "payment_status": "paid"}}
            )
            
            # Update assignment
            transaction = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
            if transaction and transaction.get("assignment_id"):
                await db.assignments.update_one(
                    {"id": transaction["assignment_id"]},
                    {"$set": {"status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

# ==================== STATS ROUTES ====================

@api_router.get("/stats/dashboard")
async def get_dashboard_stats(user: dict = Depends(get_current_user)):
    total_assignments = await db.assignments.count_documents({"user_id": user["id"]})
    completed_assignments = await db.assignments.count_documents({"user_id": user["id"], "status": "completed"})
    paid_assignments = await db.assignments.count_documents({"user_id": user["id"], "status": {"$in": ["paid", "completed"]}})
    
    # Calculate total words
    pipeline = [
        {"$match": {"user_id": user["id"], "status": {"$in": ["paid", "completed"]}}},
        {"$group": {"_id": None, "total_words": {"$sum": "$word_count"}, "total_spent": {"$sum": "$final_price"}}}
    ]
    result = await db.assignments.aggregate(pipeline).to_list(1)
    
    total_words = result[0]["total_words"] if result else 0
    total_spent = result[0]["total_spent"] if result else 0
    
    return {
        "total_assignments": total_assignments,
        "completed_assignments": completed_assignments,
        "paid_assignments": paid_assignments,
        "total_words": total_words,
        "total_spent": round(total_spent, 2)
    }

# ==================== ROOT ====================

@api_router.get("/")
async def root():
    return {"message": "Scholar Academic Writing Assistant API", "version": "1.0.0"}

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
