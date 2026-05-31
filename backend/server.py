from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Request, Body, BackgroundTasks, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import json
import re
import asyncio
import resend
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
    assignment_format: Optional[str] = "general"  # general | concert_report | lab_report | literature_review | case_study
    concert_structure: Optional[str] = None  # single_work | multiple_pieces
    has_conductor: Optional[bool] = None

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
    generation_status: Optional[str] = "pending"  # pending | generating | completed | failed
    generation_error: Optional[str] = None
    assignment_format: Optional[str] = "general"
    concert_structure: Optional[str] = None
    has_conductor: Optional[bool] = None
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
        "outline": None,
        "draft": None,
        "writing_tips": None,
        "generation_status": "pending",
        "generation_error": None,
        "assignment_format": data.assignment_format or "general",
        "concert_structure": data.concert_structure,
        "has_conductor": data.has_conductor,
        "outline_regens": 0,
        "draft_regens": 0,
        "writing_tips_regens": 0,
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
    category: str = Form("course_material"),
    user: dict = Depends(get_current_user)
):
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    # Validate category
    valid_categories = ["course_material", "previous_assignment", "requirements"]
    if category not in valid_categories:
        category = "course_material"

    # Validate file type
    allowed_types = [".pdf", ".docx", ".doc", ".txt"]
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_types:
        raise HTTPException(status_code=400, detail=f"File type {file_ext} not allowed")

    # Save file
    file_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{file_id}{file_ext}"

    content = await file.read()
    # Size cap 10MB
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

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
        "category": category,
        "extracted_text": extracted_text[:50000],  # Limit text
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.course_materials.insert_one(material_doc)

    # Update assignment
    await db.assignments.update_one(
        {"id": assignment_id},
        {"$push": {"course_materials": file_id}}
    )

    return {"id": file_id, "filename": file.filename, "category": category, "status": "uploaded"}

# ==================== AI GENERATION ROUTES ====================

ETHICAL_SYSTEM_MESSAGE = """You are Scholar, an ethical academic writing assistant designed to help students LEARN and IMPROVE their writing skills. You do not write final submission-ready work for students to pass off as their own. Instead, you produce educational scaffolding that teaches them how to approach their assignment.

For every assignment, you produce THREE distinct sections:

1. OUTLINE — A detailed, hierarchical outline (sections, sub-sections, key points, suggested arguments, evidence to look for). This is the structural blueprint.

2. DRAFT — A reference draft written at approximately the requested word count. It demonstrates the structure, tone, evidence use, and academic register the student should aim for. It is explicitly framed as a learning template, NOT a final submission. Use clear section headings and proper academic prose.

3. WRITING_TIPS — Concrete, actionable feedback and learning tips: how to research further, how to refine arguments, common mistakes to avoid, citation guidance, paraphrasing strategy, and specific suggestions to make the draft personal to the student's voice and original analysis.

ADAPT the OUTLINE and DRAFT structure to the assignment_format the user provides:
- general → standard intro / body / conclusion academic essay
- lab_report → Abstract / Introduction / Methods / Results / Discussion / Conclusion / References
- literature_review → Introduction / Thematic synthesis (organized by themes, NOT one paper per paragraph) / Gaps & Future research / Conclusion
- case_study → Background / Problem / Analysis / Recommendation / Implementation considerations
- concert_report → see CONCERT_REPORT block in the user prompt for structure variations

OUTPUT FORMAT (CRITICAL): Return ONLY a valid JSON object — no markdown fences, no explanations — with exactly these three string keys: "outline", "draft", "writing_tips". Each value must be plain text (markdown headings like ## allowed) using \\n for line breaks. Example:
{"outline": "...", "draft": "...", "writing_tips": "..."}"""


def _format_specific_brief(assignment: dict) -> str:
    """Return extra instructions appended to the user prompt based on assignment_format."""
    fmt = (assignment.get("assignment_format") or "general").lower()
    if fmt == "concert_report":
        structure = (assignment.get("concert_structure") or "single_work").lower()
        has_conductor = assignment.get("has_conductor")
        parts = ["CONCERT_REPORT MODE"]
        if structure == "single_work":
            parts.append(
                "Structure: ONE major work in depth. Sections to cover in BOTH outline and draft:\n"
                "  1) Concert overview (date, venue, ensemble, performer(s)) — keep brief\n"
                "  2) Composer & work context (era, style, historical placement)\n"
                "  3) Movement-by-movement analysis (form, harmonic language, thematic development)\n"
                "  4) Interpretation in performance (tempi, dynamics, phrasing choices)\n"
                "  5) Personal response (must be subjective and concrete, not generic)\n"
                "  6) Conclusion linking back to the listening experience"
            )
        else:
            parts.append(
                "Structure: MULTIPLE PIECES on one program. Sections:\n"
                "  1) Concert overview (program order)\n"
                "  2) Brief context per piece (composer, work, why on this program)\n"
                "  3) Analysis of EACH piece (1–2 paragraphs each — do not over-template; vary length by significance)\n"
                "  4) Synthesis: how the pieces conversed with each other (thematic / stylistic juxtaposition)\n"
                "  5) Personal response\n"
                "  6) Conclusion"
            )
        if has_conductor is True:
            parts.append(
                "Conductor present: discuss interpretive choices — tempo decisions, dynamic shaping, baton-led ensemble cohesion, "
                "and how their gestural vocabulary affected expression. Name the conductor if provided."
            )
        elif has_conductor is False:
            parts.append(
                "No conductor (chamber / orchestra-without-conductor): focus on ensemble communication, "
                "leadership from concertmaster/section principals, eye contact, breathing as unified cues, "
                "and chamber-style coordination. Do NOT invent a conductor."
            )
        return "\n".join(parts)

    if fmt == "lab_report":
        return (
            "LAB_REPORT MODE\n"
            "Use scientific IMRaD structure:\n"
            "  1) Title page note (informational, single line)\n"
            "  2) Abstract (~150 words: purpose, methods, key result, conclusion)\n"
            "  3) Introduction (background → hypothesis → why it matters)\n"
            "  4) Methods (materials, procedure, controls — written so another student could reproduce)\n"
            "  5) Results (descriptive text + table/figure placeholders; report values and units; no interpretation)\n"
            "  6) Discussion (compare to hypothesis, explain anomalies, sources of error, limits)\n"
            "  7) Conclusion (1 paragraph)\n"
            "  8) References (suggest 3–5 likely sources for the student to verify)\n"
            "Use passive voice for Methods; active voice for Discussion. Use SI units throughout."
        )

    if fmt == "literature_review":
        return (
            "LITERATURE_REVIEW MODE\n"
            "Organize THEMATICALLY, NOT one paragraph per paper. Sections:\n"
            "  1) Introduction (research question / scope / why this review matters)\n"
            "  2) Methodology of the review (search strategy, databases used, inclusion criteria — even if hypothetical)\n"
            "  3) Thematic body — group studies by theme/argument. Each theme paragraph should: state the theme, "
            "     synthesize multiple authors' positions, identify points of consensus vs disagreement, "
            "     cite ≥3 sources where possible (use placeholder author-year format like (Smith, 2022))\n"
            "  4) Critical synthesis: gaps, contradictions, methodological weaknesses across the field\n"
            "  5) Future research directions\n"
            "  6) Conclusion\n"
            "Avoid the trap of 'Smith said X. Jones said Y. Lee said Z.' — always synthesize across studies."
        )

    if fmt == "case_study":
        return (
            "CASE_STUDY MODE\n"
            "Use the analytical case structure:\n"
            "  1) Executive summary (3–4 sentences)\n"
            "  2) Background / context (who, where, when, what triggered the situation)\n"
            "  3) Problem statement (the specific decision or issue to be analyzed)\n"
            "  4) Analysis using a relevant framework (e.g., SWOT, Porter's Five Forces, PESTEL, "
            "     stakeholder analysis — choose ONE clearly named framework appropriate to the discipline)\n"
            "  5) Alternative courses of action (≥2, with pros/cons)\n"
            "  6) Recommendation with justification\n"
            "  7) Implementation considerations / risks\n"
            "Use evidence from the case directly; quote/paraphrase specific facts the student supplied."
        )

    if fmt in ("masters_thesis", "dissertation"):
        level = "Master's thesis" if fmt == "masters_thesis" else "Doctoral dissertation"
        depth = (
            "Master's-level: ~12,000–25,000 words total. Original contribution should be the application or extension "
            "of existing theory; defensible methodology over groundbreaking novelty."
            if fmt == "masters_thesis" else
            "Doctoral level: 60,000–100,000 words total. MUST demonstrate an original, substantive contribution "
            "to the field. Methodology rigorous and defensible to viva-level scrutiny."
        )
        return (
            f"{level.upper()} MODE\n"
            f"{depth}\n"
            "The OUTLINE must lay out the FULL chapter structure (not just one chapter):\n"
            "  CH 1. Introduction (problem, aim, objectives, RQs, significance, structure of thesis)\n"
            "  CH 2. Literature Review (thematic — see LITERATURE_REVIEW MODE structure, but deeper)\n"
            "  CH 3. Methodology (philosophy/paradigm, approach, design, data collection, analysis, ethics, limitations)\n"
            "  CH 4. Findings / Results (presentation only, organized by RQ or theme)\n"
            "  CH 5. Discussion (interpret findings against literature; theoretical & practical implications)\n"
            "  CH 6. Conclusion (key contributions, limitations, recommendations, future research)\n"
            "  Appendices placeholder (interview schedules, coding frames, consent forms, etc.)\n"
            "\n"
            "The DRAFT should sample ONE representative chapter in depth (default: Chapter 1 Introduction, "
            "OR the chapter the student names in additional_notes) — written at ~the requested word count — "
            "showing the academic register, citation density, and argumentative scaffolding the student should match. "
            "Reference candidate frameworks the student should explore (Saunders' research onion, etc.). "
            "Use UK or US academic conventions consistently per the writing_style.\n"
            "\n"
            "The WRITING_TIPS section MUST include: supervisor-meeting prep checklist, how to keep a research diary, "
            "viva/defense preparation pointers, plagiarism & AI-disclosure considerations for thesis examination, "
            "and references-management workflow (Zotero/Mendeley/EndNote)."
        )

    if fmt == "masters_thesis_proposal":
        return (
            "MASTER'S THESIS PROPOSAL MODE\n"
            "This is the proposal/registration document, NOT the full thesis. Structure:\n"
            "  1) Title (working title — keep editable)\n"
            "  2) Background & rationale (~500 words: why this topic, why now, gap)\n"
            "  3) Aim & Objectives (1 aim, 3–5 objectives)\n"
            "  4) Research Questions (or hypotheses)\n"
            "  5) Preliminary literature review (4–6 thematic clusters with key authors)\n"
            "  6) Proposed methodology (philosophy, approach, design, sampling, data collection, analysis plan, ethics)\n"
            "  7) Timeline / Gantt-style milestone list\n"
            "  8) Anticipated contribution & limitations\n"
            "  9) References (8–15 candidate sources)\n"
            "Tone: scholarly but provisional ('this study WILL...', not 'this study HAS...'). "
            "Use future tense for methodology and findings sections."
        )

    return ""


def _parse_ai_json(raw: str) -> dict:
    """Robustly extract the JSON object from the model response."""
    if not raw:
        return {}
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find first { ... last }
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {}


async def run_generation(assignment_id: str):
    """Background task: generate outline + draft + writing tips for a paid assignment."""
    try:
        assignment = await db.assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not assignment:
            logger.error(f"Generation: assignment {assignment_id} not found")
            return

        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {
                "generation_status": "generating",
                "generation_error": None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )

        materials = await db.course_materials.find(
            {"assignment_id": assignment_id},
            {"_id": 0, "extracted_text": 1, "filename": 1, "category": 1}
        ).to_list(20)

        # Group materials by category for clearer prompt structure
        grouped = {"course_material": [], "previous_assignment": [], "requirements": []}
        for m in materials:
            cat = m.get("category") or "course_material"
            if cat not in grouped:
                cat = "course_material"
            grouped[cat].append(m)

        def section(label, items, char_limit=6000):
            if not items:
                return ""
            blocks = "\n\n".join(
                f"[{m['filename']}]\n{m['extracted_text'][:char_limit]}" for m in items
            )
            return f"\n\n=== {label} ===\n{blocks}"

        materials_context = (
            section("ASSIGNMENT BRIEF / REQUIREMENTS DOCS", grouped["requirements"], 8000)
            + section("COURSE MATERIAL (syllabus, readings, slides)", grouped["course_material"], 6000)
            + section("STUDENT'S PREVIOUS WORK (use ONLY to match their voice/style — never copy)", grouped["previous_assignment"], 4000)
        ).strip()

        user_prompt = f"""Assignment Details:
Title: {assignment['title']}
Subject: {assignment['subject']}
Format: {assignment.get('assignment_format', 'general')}
Requirements: {assignment['requirements']}
Word Count Target: {assignment['word_count']} words (this applies to the DRAFT section only)
Writing Style: {assignment['writing_style']}
Additional Notes: {assignment.get('additional_notes', '')}

{_format_specific_brief(assignment)}

{materials_context if materials_context else "No supplemental materials provided."}

Produce the JSON object with the three required keys (outline, draft, writing_tips).
The DRAFT must be approximately {assignment['word_count']} words and demonstrate scholarly structure.
If STUDENT'S PREVIOUS WORK is provided, subtly match their tone & vocabulary in the draft (without copying phrases).
Remember: this is a LEARNING REFERENCE, not a final submission. Encourage the student's own voice in writing_tips."""

        from emergentintegrations.llm.chat import LlmChat, UserMessage

        api_key = os.environ.get('EMERGENT_LLM_KEY')
        chat = LlmChat(
            api_key=api_key,
            session_id=f"assignment-{assignment_id}",
            system_message=ETHICAL_SYSTEM_MESSAGE
        ).with_model("openai", "gpt-5.2")

        response = await chat.send_message(UserMessage(text=user_prompt))
        parsed = _parse_ai_json(response)

        outline = parsed.get("outline", "").strip()
        draft = parsed.get("draft", "").strip()
        writing_tips = parsed.get("writing_tips", "").strip()

        if not (outline or draft or writing_tips):
            # Fallback: store raw response in draft so user still gets value
            draft = response or ""

        combined = f"# Outline\n\n{outline}\n\n# Draft\n\n{draft}\n\n# Writing Tips\n\n{writing_tips}"

        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {
                "outline": outline,
                "draft": draft,
                "writing_tips": writing_tips,
                "generated_content": combined,
                "status": "completed",
                "generation_status": "completed",
                "generation_error": None,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        logger.info(f"Generation complete for assignment {assignment_id}")

    except Exception as e:
        logger.exception(f"Generation failed for {assignment_id}: {e}")
        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {
                "generation_status": "failed",
                "generation_error": str(e)[:500],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )


async def trigger_generation_if_needed(assignment_id: str, background_tasks: BackgroundTasks):
    """Schedule generation if the assignment is paid and not already generating/completed."""
    assignment = await db.assignments.find_one({"id": assignment_id}, {"_id": 0})
    if not assignment:
        return
    gen_status = assignment.get("generation_status", "pending")
    if assignment.get("status") in ("paid", "completed") and gen_status in ("pending", "failed"):
        background_tasks.add_task(run_generation, assignment_id)


@api_router.post("/assignments/{assignment_id}/generate")
async def generate_content(
    assignment_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    assignment = await db.assignments.find_one(
        {"id": assignment_id, "user_id": user["id"]},
        {"_id": 0}
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if assignment["status"] not in ("paid", "completed"):
        raise HTTPException(status_code=400, detail="Assignment must be paid before generation")

    if assignment.get("generation_status") == "generating":
        return {"status": "generating", "message": "Generation already in progress"}

    background_tasks.add_task(run_generation, assignment_id)
    await db.assignments.update_one(
        {"id": assignment_id},
        {"$set": {"generation_status": "generating", "generation_error": None}}
    )
    return {"status": "generating", "message": "Generation started"}


# ---------- Per-section regenerate (2 free, then $5) ----------

FREE_REGENS_PER_SECTION = 2
REGEN_PRICE = 5.0
VALID_SECTIONS = ("outline", "draft", "writing_tips")

SECTION_LABELS = {"outline": "Outline", "draft": "Draft", "writing_tips": "Writing Tips"}


async def run_section_regeneration(assignment_id: str, section: str):
    """Background task: regenerate ONE section, preserving the others."""
    try:
        assignment = await db.assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not assignment:
            return
        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {"generation_status": "generating", "generation_error": None}}
        )

        materials = await db.course_materials.find(
            {"assignment_id": assignment_id},
            {"_id": 0, "extracted_text": 1, "filename": 1, "category": 1}
        ).to_list(20)
        grouped = {"course_material": [], "previous_assignment": [], "requirements": []}
        for m in materials:
            cat = m.get("category") or "course_material"
            if cat not in grouped:
                cat = "course_material"
            grouped[cat].append(m)
        materials_context = "\n\n".join(
            f"[{m['filename']}] {m['extracted_text'][:6000]}"
            for cat in grouped for m in grouped[cat]
        )

        keep = {k: assignment.get(k) or "" for k in VALID_SECTIONS if k != section}
        target_label = SECTION_LABELS[section]

        regen_system = (
            "You are Scholar, an ethical academic writing tutor. "
            f"The student has asked you to REGENERATE just the {target_label.upper()} section of their learning materials, "
            "keeping the other sections consistent with this regeneration. "
            "Take a meaningfully different angle from the previous version (different structure, new examples, alternative framing) "
            "while still satisfying the assignment requirements. "
            'Return ONLY a JSON object with one key: {"' + section + '": "..."}'
        )

        regen_user = f"""Assignment Details:
Title: {assignment['title']}
Subject: {assignment['subject']}
Format: {assignment.get('assignment_format', 'general')}
Requirements: {assignment['requirements']}
Word Count Target: {assignment['word_count']} words (applies to DRAFT only)
Writing Style: {assignment['writing_style']}
Additional Notes: {assignment.get('additional_notes', '')}

{_format_specific_brief(assignment)}

EXISTING SECTIONS (for consistency — do NOT regenerate these):
""" + "\n\n".join([f"--- {SECTION_LABELS[k].upper()} ---\n{v[:5000]}" for k, v in keep.items() if v]) + f"""

{materials_context[:12000] if materials_context else ''}

Regenerate ONLY the {target_label.upper()} section with a fresh angle. Return JSON with the single key "{section}"."""

        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        chat = LlmChat(
            api_key=api_key,
            session_id=f"regen-{assignment_id}-{section}-{uuid.uuid4().hex[:6]}",
            system_message=regen_system
        ).with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=regen_user))
        parsed = _parse_ai_json(response)
        new_text = (parsed.get(section, "") or "").strip()
        if not new_text:
            new_text = response.strip() if isinstance(response, str) else ""

        regen_field = f"{section}_regens"
        regen_ts_field = f"{section}_regenerated_at"
        prev_version_field = f"{section}_previous"

        previous_text = (assignment.get(section) or "")
        now_iso = datetime.now(timezone.utc).isoformat()

        update = {
            section: new_text,
            prev_version_field: previous_text,
            regen_ts_field: now_iso,
            "generation_status": "completed",
            "updated_at": now_iso,
        }
        # Rebuild combined content
        outline = new_text if section == "outline" else (assignment.get("outline") or "")
        draft = new_text if section == "draft" else (assignment.get("draft") or "")
        writing_tips = new_text if section == "writing_tips" else (assignment.get("writing_tips") or "")
        update["generated_content"] = f"# Outline\n\n{outline}\n\n# Draft\n\n{draft}\n\n# Writing Tips\n\n{writing_tips}"

        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": update, "$inc": {regen_field: 1}}
        )
        logger.info(f"Section regenerated: {assignment_id} / {section}")
    except Exception as e:
        logger.exception(f"Regen failed {assignment_id}/{section}: {e}")
        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {"generation_status": "failed", "generation_error": str(e)[:300]}}
        )


class RegenerateResponse(BaseModel):
    status: str  # "regenerating" | "payment_required"
    remaining_free: int
    checkout_url: Optional[str] = None
    session_id: Optional[str] = None


@api_router.post("/assignments/{assignment_id}/regenerate/{section}", response_model=RegenerateResponse)
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
    assignment = await db.assignments.find_one(
        {"id": assignment_id, "user_id": user["id"]}, {"_id": 0}
    )
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
        # Free regen
        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {"generation_status": "generating"}}
        )
        background_tasks.add_task(run_section_regeneration, assignment_id, section)
        return RegenerateResponse(status="regenerating", remaining_free=remaining_free - 1)

    # Paid regen — create Stripe checkout
    try:
        from emergentintegrations.payments.stripe.checkout import (
            StripeCheckout, CheckoutSessionRequest, CheckoutSessionResponse
        )
        stripe_api_key = os.environ.get('STRIPE_API_KEY')
        host_url = str(request.base_url).rstrip('/')
        webhook_url = f"{host_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)
        origin = (origin_url or "").rstrip('/') or str(request.base_url).rstrip('/')
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
        # Persist pending regen
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
            status="payment_required",
            remaining_free=0,
            checkout_url=session.url,
            session_id=session.session_id,
        )
    except Exception as e:
        logger.exception(f"Regen checkout failed: {e}")
        raise HTTPException(status_code=500, detail=f"Could not start checkout: {str(e)}")


@api_router.get("/assignments/{assignment_id}/regen-status/{session_id}")
async def regen_status(
    assignment_id: str,
    session_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    order = await db.regen_orders.find_one(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Regen order not found")
    if order["status"] == "completed":
        return {"status": "already_processed"}
    try:
        from emergentintegrations.payments.stripe.checkout import StripeCheckout
        stripe_checkout = StripeCheckout(
            api_key=os.environ.get('STRIPE_API_KEY'), webhook_url=""
        )
        stripe_status = await stripe_checkout.get_checkout_status(session_id)
        if stripe_status.payment_status == "paid":
            await db.regen_orders.update_one(
                {"session_id": session_id},
                {"$set": {"status": "completed", "paid_at": datetime.now(timezone.utc).isoformat()}}
            )
            # Allow one paid regen by NOT incrementing free counter; bump the regen field is done by the task itself
            await db.assignments.update_one(
                {"id": assignment_id},
                {"$set": {"generation_status": "generating"}}
            )
            background_tasks.add_task(run_section_regeneration, assignment_id, order["section"])
            return {"status": "regenerating", "section": order["section"]}
        return {"status": stripe_status.payment_status}
    except Exception as e:
        logger.exception(f"Regen status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
async def get_payment_status(
    session_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
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
            
            # Update assignment status and trigger generation
            if transaction.get("assignment_id"):
                await db.assignments.update_one(
                    {"id": transaction["assignment_id"]},
                    {"$set": {"status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                await trigger_generation_if_needed(transaction["assignment_id"], background_tasks)
        
        # Return assignment_id for frontend redirect convenience
        return {
            "status": status.status,
            "payment_status": status.payment_status,
            "amount_total": status.amount_total,
            "currency": status.currency,
            "assignment_id": transaction.get("assignment_id") if transaction else None
        }
        
    except Exception as e:
        logger.error(f"Payment status error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get payment status: {str(e)}")

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request, background_tasks: BackgroundTasks):
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
            
            # Update assignment and trigger AI generation
            transaction = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
            if transaction and transaction.get("assignment_id"):
                await db.assignments.update_one(
                    {"id": transaction["assignment_id"]},
                    {"$set": {"status": "paid", "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                await trigger_generation_if_needed(transaction["assignment_id"], background_tasks)
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

# ==================== COURSE MATERIALS / REWRITE / AI CHECK ====================

class CourseMaterialItem(BaseModel):
    id: str
    filename: str
    category: str
    created_at: str

@api_router.get("/assignments/{assignment_id}/materials", response_model=List[CourseMaterialItem])
async def list_materials(assignment_id: str, user: dict = Depends(get_current_user)):
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    docs = await db.course_materials.find(
        {"assignment_id": assignment_id},
        {"_id": 0, "id": 1, "filename": 1, "category": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(50)
    # Backfill category if missing
    for d in docs:
        d.setdefault("category", "course_material")
    return [CourseMaterialItem(**d) for d in docs]


class RewriteAnalyzeRequest(BaseModel):
    text: str
    mode: Optional[str] = "draft"  # "draft" = full one-shot; "paragraph" = single paragraph workspace mode

REWRITE_COACH_SYSTEM = """You are an expert academic writing tutor. The student is rewriting an AI-generated reference draft in their own voice. Identify phrases or passages that read as "AI-generated" — over-formal hedging, em-dash overload, generic cliches ("delve into", "navigate the complexities", "in today's world"), uniform sentence rhythm, vague abstractions, redundant tricolons.

For each issue, return the EXACT phrase to flag, classify the type, explain why in one sentence, and provide a concrete human-style rewrite.

OUTPUT FORMAT (CRITICAL): Return ONLY a valid JSON object (no markdown fences) shaped exactly:
{
  "summary": "1-2 sentence overall impression",
  "ai_likelihood": 0-100 integer (rough estimate of how AI-ish the text reads),
  "issues": [
    {"phrase": "<exact substring>", "type": "cliche|hedge|uniform|abstract|em_dash|passive|other", "why": "<one short sentence>", "suggestion": "<rewrite>"}
  ]
}
Return at most 15 issues. Pick the highest-impact ones."""

@api_router.post("/rewrite-coach/analyze")
async def rewrite_coach_analyze(data: RewriteAnalyzeRequest, user: dict = Depends(get_current_user)):
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    # No hard word cap — cap at 200k chars (~40k words) only to avoid token blow-ups
    if len(text) > 200000:
        text = text[:200000]
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get('EMERGENT_LLM_KEY')
        chat = LlmChat(
            api_key=api_key,
            session_id=f"rewrite-coach-{user['id']}-{uuid.uuid4().hex[:8]}",
            system_message=REWRITE_COACH_SYSTEM
        ).with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=f"Analyze this text:\n\n{text}"))
        parsed = _parse_ai_json(response)
        if not isinstance(parsed, dict):
            parsed = {}
        return {
            "summary": parsed.get("summary", ""),
            "ai_likelihood": int(parsed.get("ai_likelihood", 50)) if isinstance(parsed.get("ai_likelihood"), (int, float, str)) and str(parsed.get("ai_likelihood")).isdigit() else parsed.get("ai_likelihood", 50),
            "issues": parsed.get("issues", [])[:15],
        }
    except Exception as e:
        logger.exception(f"Rewrite coach error: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


# ----- AI Check orders (manual: emailed to owner) -----

AI_CHECK_PRICES = {"originality": 10.0, "turnitin": 15.0}

class AICheckOrderRequest(BaseModel):
    assignment_id: str
    tier: str  # 'originality' | 'turnitin'
    text_to_check: str
    origin_url: str

class AICheckOrderResponse(BaseModel):
    url: str
    session_id: str
    order_id: str


async def send_ai_check_email(order_id: str):
    """Background task: notify owner about a paid AI check order with the text attached."""
    try:
        order = await db.ai_check_orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            logger.error(f"AI check email: order {order_id} not found")
            return

        owner_email = os.environ.get("OWNER_EMAIL")
        api_key = os.environ.get("RESEND_API_KEY")
        sender = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")

        if not (api_key and owner_email) or api_key.startswith("re_placeholder"):
            logger.warning(f"Resend not configured; skipping email for order {order_id}")
            await db.ai_check_orders.update_one(
                {"id": order_id}, {"$set": {"email_status": "skipped_no_key"}}
            )
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

        import base64
        text_bytes = text.encode("utf-8")
        b64 = base64.b64encode(text_bytes).decode("ascii")

        params = {
            "from": sender,
            "to": [owner_email],
            "reply_to": student_email,
            "subject": f"[Scholar AI Check] {tier_label} — {student_name} — {assignment_title}",
            "html": html_content,
            "attachments": [
                {"filename": f"order_{order_id}_text.txt", "content": b64}
            ],
        }
        email = await asyncio.to_thread(resend.Emails.send, params)
        email_id = email.get("id") if isinstance(email, dict) else None
        await db.ai_check_orders.update_one(
            {"id": order_id},
            {"$set": {"email_status": "sent", "email_id": email_id}}
        )
        logger.info(f"AI check order {order_id} emailed to owner (resend id={email_id})")
    except Exception as e:
        logger.exception(f"Failed to email AI check order {order_id}: {e}")
        await db.ai_check_orders.update_one(
            {"id": order_id}, {"$set": {"email_status": "failed", "email_error": str(e)[:300]}}
        )


@api_router.post("/ai-check/order", response_model=AICheckOrderResponse)
async def create_ai_check_order(
    data: AICheckOrderRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    if data.tier not in AI_CHECK_PRICES:
        raise HTTPException(status_code=400, detail="Invalid tier")
    text = (data.text_to_check or "").strip()
    if len(text) < 50:
        raise HTTPException(status_code=400, detail="Text is too short to check")

    assignment = await db.assignments.find_one(
        {"id": data.assignment_id, "user_id": user["id"]}, {"_id": 0}
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    order_id = str(uuid.uuid4())
    word_count = len(text.split())
    amount = AI_CHECK_PRICES[data.tier]
    now = datetime.now(timezone.utc).isoformat()

    try:
        from emergentintegrations.payments.stripe.checkout import (
            StripeCheckout, CheckoutSessionRequest, CheckoutSessionResponse
        )
        stripe_api_key = os.environ.get('STRIPE_API_KEY')
        host_url = str(request.base_url).rstrip('/')
        webhook_url = f"{host_url}/api/webhook/stripe"
        stripe_checkout = StripeCheckout(api_key=stripe_api_key, webhook_url=webhook_url)

        origin = data.origin_url.rstrip('/')
        success_url = f"{origin}/assignment/{data.assignment_id}?ai_check_session={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{origin}/assignment/{data.assignment_id}"

        checkout_request = CheckoutSessionRequest(
            amount=amount,
            currency="usd",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "purpose": "ai_check_order",
                "order_id": order_id,
                "tier": data.tier,
                "assignment_id": data.assignment_id,
                "user_id": user["id"],
            },
        )
        session: CheckoutSessionResponse = await stripe_checkout.create_checkout_session(checkout_request)

        order_doc = {
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
        }
        await db.ai_check_orders.insert_one(order_doc)

        return AICheckOrderResponse(url=session.url, session_id=session.session_id, order_id=order_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"AI check order creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")


@api_router.get("/ai-check/status/{session_id}")
async def ai_check_status(
    session_id: str,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    order = await db.ai_check_orders.find_one(
        {"session_id": session_id, "user_id": user["id"]}, {"_id": 0, "text_to_check": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # If still pending, check Stripe
    if order["status"] == "pending_payment":
        try:
            from emergentintegrations.payments.stripe.checkout import StripeCheckout
            stripe_checkout = StripeCheckout(
                api_key=os.environ.get('STRIPE_API_KEY'), webhook_url=""
            )
            stripe_status = await stripe_checkout.get_checkout_status(session_id)
            if stripe_status.payment_status == "paid":
                await db.ai_check_orders.update_one(
                    {"id": order["id"]},
                    {"$set": {"status": "paid", "paid_at": datetime.now(timezone.utc).isoformat()}}
                )
                order["status"] = "paid"
                # Fire-and-forget email
                background_tasks.add_task(send_ai_check_email, order["id"])
        except Exception as e:
            logger.warning(f"Stripe status check failed for {session_id}: {e}")

    return {
        "order_id": order["id"],
        "tier": order["tier"],
        "amount": order["amount"],
        "status": order["status"],
        "email_status": order.get("email_status", "not_sent"),
        "created_at": order.get("created_at"),
    }


@api_router.get("/ai-check/orders/{assignment_id}")
async def list_ai_check_orders(assignment_id: str, user: dict = Depends(get_current_user)):
    docs = await db.ai_check_orders.find(
        {"user_id": user["id"], "assignment_id": assignment_id},
        {"_id": 0, "text_to_check": 0}
    ).sort("created_at", -1).to_list(50)
    return docs


# ----- Student: download completed report -----

@api_router.get("/ai-check/orders/{order_id}/report")
async def download_ai_check_report(order_id: str, user: dict = Depends(get_current_user)):
    order = await db.ai_check_orders.find_one(
        {"id": order_id, "user_id": user["id"]}, {"_id": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.get("status") != "completed" or not order.get("report_path"):
        raise HTTPException(status_code=400, detail="Report not ready yet")
    report_path = Path(order["report_path"])
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file missing")
    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(report_path),
        filename=order.get("report_filename", "ai_check_report.pdf"),
        media_type="application/octet-stream"
    )


# ----- Admin (reviewer) endpoints -----

def is_admin(user: dict) -> bool:
    owner = (os.environ.get("OWNER_EMAIL") or "").strip().lower()
    return bool(owner) and user.get("email", "").lower() == owner

async def require_admin(user: dict = Depends(get_current_user)):
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin only")
    return user


@api_router.get("/admin/ai-check/orders")
async def admin_list_all_orders(
    status_filter: Optional[str] = None,
    _admin: dict = Depends(require_admin),
):
    query = {}
    if status_filter:
        query["status"] = status_filter
    docs = await db.ai_check_orders.find(
        query, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return docs


@api_router.get("/admin/ai-check/orders/{order_id}")
async def admin_get_order(order_id: str, _admin: dict = Depends(require_admin)):
    order = await db.ai_check_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


async def send_report_ready_email(order_id: str):
    """Notify the student that their report is ready, attaching the PDF."""
    try:
        order = await db.ai_check_orders.find_one({"id": order_id}, {"_id": 0})
        if not order:
            return
        api_key = os.environ.get("RESEND_API_KEY")
        sender = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
        if not api_key or api_key.startswith("re_placeholder"):
            logger.warning(f"Resend not configured; skipping completion email for {order_id}")
            return
        resend.api_key = api_key

        tier_label = "Turnitin" if order["tier"] == "turnitin" else "Originality.ai"
        report_path = Path(order.get("report_path", ""))
        attachments = []
        if report_path.exists():
            import base64
            with open(report_path, "rb") as f:
                attachments.append({
                    "filename": order.get("report_filename", "report.pdf"),
                    "content": base64.b64encode(f.read()).decode("ascii"),
                })

        notes = order.get("completion_notes") or ""
        notes_html = f'<p style="background:#fafafa;padding:12px;border-left:3px solid #1a2842;">{notes}</p>' if notes else ""

        html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <h2 style="color: #1a2842;">Your {tier_label} report is ready</h2>
          <p>Hi {order.get('student_name','')},</p>
          <p>Your AI-check report for <b>{order.get('assignment_title','')}</b> has been completed.
             The full report is attached as a PDF.</p>
          {notes_html}
          <p style="color:#666; font-size: 12px; margin-top: 24px;">— Scholar Reviewer Team</p>
        </div>
        """

        params = {
            "from": sender,
            "to": [order["student_email"]],
            "subject": f"Your {tier_label} report — {order.get('assignment_title','')}",
            "html": html,
            "attachments": attachments,
        }
        email = await asyncio.to_thread(resend.Emails.send, params)
        logger.info(f"Report-ready email sent for order {order_id}: {email}")
    except Exception as e:
        logger.exception(f"Failed sending report-ready email for {order_id}: {e}")


@api_router.post("/admin/ai-check/orders/{order_id}/complete")
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

    # Save report file
    file_ext = Path(report.filename or "report.pdf").suffix.lower() or ".pdf"
    if file_ext not in [".pdf", ".docx", ".doc", ".txt"]:
        raise HTTPException(status_code=400, detail="Report must be PDF, DOCX, DOC, or TXT")
    content = await report.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Report too large (max 25MB)")

    report_id = str(uuid.uuid4())
    saved_path = UPLOAD_DIR / f"report_{order_id}_{report_id}{file_ext}"
    async with aiofiles.open(saved_path, "wb") as f:
        await f.write(content)

    now = datetime.now(timezone.utc).isoformat()
    await db.ai_check_orders.update_one(
        {"id": order_id},
        {"$set": {
            "status": "completed",
            "report_filename": report.filename or f"report{file_ext}",
            "report_path": str(saved_path),
            "completion_notes": notes,
            "completed_at": now,
        }}
    )

    background_tasks.add_task(send_report_ready_email, order_id)
    return {"status": "completed", "order_id": order_id, "email": "queued"}


@api_router.post("/admin/ai-check/orders/{order_id}/mark-in-progress")
async def admin_mark_in_progress(order_id: str, _admin: dict = Depends(require_admin)):
    res = await db.ai_check_orders.update_one(
        {"id": order_id, "status": "paid"},
        {"$set": {"status": "in_progress"}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=400, detail="Order not in paid state")
    return {"status": "in_progress"}


@api_router.get("/auth/me-admin")
async def me_admin(user: dict = Depends(get_current_user)):
    return {"is_admin": is_admin(user), "email": user.get("email")}


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
