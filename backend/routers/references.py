"""CrossRef suggested references + free public AI-check."""
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import httpx

from core import db, logger, get_current_user
from routers.generation import REWRITE_COACH_SYSTEM, _parse_ai_json

router = APIRouter(prefix="/api")


@router.get("/assignments/{assignment_id}/suggested-references")
async def suggested_references(assignment_id: str, limit: int = 8, user: dict = Depends(get_current_user)):
    assignment = await db.assignments.find_one({"id": assignment_id, "user_id": user["id"]}, {"_id": 0})
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    query_parts = [assignment.get("title", ""), assignment.get("subject", ""), (assignment.get("requirements") or "")[:300]]
    query = " ".join(q for q in query_parts if q).strip()
    if not query:
        return {"references": []}
    rows = max(3, min(int(limit), 20))
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://api.crossref.org/works",
                params={"query": query[:300], "rows": rows,
                        "select": "DOI,title,author,issued,container-title,URL,abstract,type"},
                headers={"User-Agent": "AIScholar/1.0 (mailto:ryannazha@gmail.com)"},
            )
            r.raise_for_status()
            items = r.json().get("message", {}).get("items", [])
    except Exception as e:
        logger.warning(f"CrossRef query failed: {e}")
        return {"references": [], "error": "Reference service temporarily unavailable"}

    refs = []
    for it in items:
        authors = it.get("author") or []
        author_str = ", ".join(
            f"{a.get('family', '')}{', ' + a.get('given', '') if a.get('given') else ''}"
            for a in authors[:3]
        )
        if len(authors) > 3:
            author_str += ", et al."
        issued = it.get("issued", {}).get("date-parts", [[None]])[0][0]
        title_arr = it.get("title") or []
        title = title_arr[0] if title_arr else "(untitled)"
        venue_arr = it.get("container-title") or []
        venue = venue_arr[0] if venue_arr else ""
        doi = it.get("DOI", "")
        refs.append({
            "title": title, "authors": author_str or "Unknown", "year": issued,
            "venue": venue, "doi": doi,
            "url": it.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
            "type": it.get("type", ""),
            "abstract_excerpt": (it.get("abstract") or "")[:300].replace("<jats:p>", "").replace("</jats:p>", ""),
        })
    return {"references": refs, "query": query[:200]}


_free_check_counter: dict = {}


class FreeAICheckRequest(BaseModel):
    text: str


@router.post("/free-ai-check")
async def free_ai_check(data: FreeAICheckRequest, request: Request):
    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Paste some text to check")
    if len(text) > 4000:
        raise HTTPException(status_code=400, detail="Free tier limit is 4000 characters (~700 words). Sign up for unlimited.")

    client_ip = request.client.host if request.client else "unknown"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{client_ip}:{today}"
    count = _free_check_counter.get(key, 0)
    if count >= 5:
        raise HTTPException(status_code=429, detail="Free tier: max 5 checks per day. Create a free account for unlimited.")
    _free_check_counter[key] = count + 1

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"free-check-{uuid.uuid4().hex[:8]}",
            system_message=REWRITE_COACH_SYSTEM,
        ).with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=f"Analyze this text:\n\n{text}"))
        parsed = _parse_ai_json(response) or {}
        return {
            "summary": parsed.get("summary", ""),
            "ai_likelihood": parsed.get("ai_likelihood", 50),
            "issues": (parsed.get("issues", []) or [])[:8],
            "remaining_today": max(0, 5 - count - 1),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Free AI check failed: {e}")
        raise HTTPException(status_code=500, detail="AI checker temporarily unavailable")
