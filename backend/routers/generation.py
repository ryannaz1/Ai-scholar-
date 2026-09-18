"""AI generation background tasks + prompts (shared, not exposed as routes)."""
import os
import re
import json
import uuid
from datetime import datetime, timezone
from fastapi import BackgroundTasks

from core import db, logger


ETHICAL_SYSTEM_MESSAGE = """You are AIScholar, an ethical academic writing assistant designed to help students LEARN and IMPROVE their writing skills. You do not write final submission-ready work for students to pass off as their own. Instead, you produce educational scaffolding that teaches them how to approach their assignment.

For every assignment, you produce THREE distinct sections:

1. OUTLINE — A detailed, hierarchical outline (sections, sub-sections, key points, suggested arguments, evidence to look for). This is the structural blueprint.

2. DRAFT — A reference draft written at approximately the requested word count. **The DRAFT MUST include the following standard academic components** (use markdown headings):
   • A Cover Page block at the very top (title, student name placeholder [Your Name], course placeholder [Course Code – Course Name], instructor placeholder [Instructor Name], date placeholder [Submission Date]).
   • A Table of Contents listing the section/heading hierarchy with page-number placeholders ([p. X]).
   • The main body content with proper in-text citations in the requested citation_style (APA, MLA, Harvard, Chicago, or IEEE). Use placeholder author-year (or numeric) markers like (Smith, 2022) / (Smith 47) / [12] consistently.
   • A References / Works Cited / Bibliography section at the end formatted in the requested citation_style with 5–10 realistic-sounding scholarly references the student should VERIFY before submitting.
   • An Appendix section with at least one placeholder appendix (e.g., "Appendix A: [supplementary material — e.g., raw data table, interview schedule, code excerpts]") relevant to the subject.

3. WRITING_TIPS — Concrete, actionable feedback: how to research further, how to refine arguments, common mistakes to avoid, citation-style-specific guidance, paraphrasing strategy, and suggestions to make the draft personal.

ADAPT the OUTLINE and DRAFT structure to the assignment_format the user provides (see CONCERT_REPORT / LAB_REPORT / LITERATURE_REVIEW / CASE_STUDY / MASTERS_THESIS / DISSERTATION blocks in the user prompt for structural variants).

OUTPUT FORMAT (CRITICAL): Return ONLY a valid JSON object — no markdown fences, no explanations — with exactly these three string keys: "outline", "draft", "writing_tips". Each value must be plain text (markdown headings like ## allowed) using \\n for line breaks. Example:
{"outline": "...", "draft": "...", "writing_tips": "..."}"""


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


FREE_REGENS_PER_SECTION = 2
REGEN_PRICE = 5.0
VALID_SECTIONS = ("outline", "draft", "writing_tips")
SECTION_LABELS = {"outline": "Outline", "draft": "Draft", "writing_tips": "Writing Tips"}


def format_specific_brief(assignment: dict) -> str:
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
            parts.append("Conductor present: discuss interpretive choices — tempo, dynamics, baton-led cohesion. Name the conductor if provided.")
        elif has_conductor is False:
            parts.append("No conductor: focus on ensemble communication, section-principal leadership, chamber-style coordination. Do NOT invent a conductor.")
        return "\n".join(parts)

    if fmt == "lab_report":
        return (
            "LAB_REPORT MODE\nUse scientific IMRaD structure:\n"
            "  1) Title page note (informational, single line)\n  2) Abstract (~150 words)\n  3) Introduction\n"
            "  4) Methods\n  5) Results\n  6) Discussion\n  7) Conclusion\n  8) References (3–5)\n"
            "Passive voice for Methods; active for Discussion. Use SI units."
        )
    if fmt == "literature_review":
        return (
            "LITERATURE_REVIEW MODE\nOrganize THEMATICALLY. Sections:\n"
            "  1) Introduction  2) Methodology of the review  3) Thematic body (synthesize across authors)\n"
            "  4) Critical synthesis (gaps, contradictions)  5) Future directions  6) Conclusion\n"
            "Cite ≥3 sources per theme (Smith, 2022). Do NOT do one paragraph per paper."
        )
    if fmt == "case_study":
        return (
            "CASE_STUDY MODE\n  1) Executive summary  2) Background  3) Problem statement\n"
            "  4) Analysis using ONE named framework (SWOT / Porter's / PESTEL / stakeholder)\n"
            "  5) Alternatives (≥2, pros/cons)  6) Recommendation  7) Implementation & risks"
        )
    if fmt in ("masters_thesis", "dissertation"):
        level = "Master's thesis" if fmt == "masters_thesis" else "Doctoral dissertation"
        depth = (
            "Master's-level: ~12k–25k words. Contribution = application/extension of existing theory."
            if fmt == "masters_thesis" else
            "Doctoral level: 60k–100k words. MUST demonstrate original contribution."
        )
        return (
            f"{level.upper()} MODE\n{depth}\n"
            "OUTLINE = FULL chapter plan (CH 1 Intro, CH 2 Lit Review, CH 3 Methodology, CH 4 Findings, CH 5 Discussion, CH 6 Conclusion, Appendices).\n"
            "DRAFT samples ONE representative chapter in depth (default: Chapter 1) at the requested word count.\n"
            "WRITING_TIPS: supervisor prep, research diary, viva prep, plagiarism/AI-disclosure, references management."
        )
    if fmt == "masters_thesis_proposal":
        return (
            "MASTER'S THESIS PROPOSAL MODE (proposal, NOT full thesis):\n"
            "  1) Title  2) Background & rationale  3) Aim & Objectives  4) Research Questions\n"
            "  5) Prelim lit review (4–6 clusters)  6) Proposed methodology  7) Timeline  8) Contribution & limits  9) References (8–15)\n"
            "Tone: scholarly, future tense ('this study WILL...')."
        )
    return ""


def _parse_ai_json(raw: str) -> dict:
    if not raw:
        return {}
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {}


async def run_generation(assignment_id: str):
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
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )

        materials = await db.course_materials.find(
            {"assignment_id": assignment_id},
            {"_id": 0, "extracted_text": 1, "filename": 1, "category": 1},
        ).to_list(20)

        grouped = {"course_material": [], "previous_assignment": [], "requirements": []}
        for m in materials:
            cat = m.get("category") or "course_material"
            if cat not in grouped:
                cat = "course_material"
            grouped[cat].append(m)

        def section(label, items, char_limit=6000):
            if not items:
                return ""
            blocks = "\n\n".join(f"[{m['filename']}]\n{m['extracted_text'][:char_limit]}" for m in items)
            return f"\n\n=== {label} ===\n{blocks}"

        materials_context = (
            section("ASSIGNMENT BRIEF / REQUIREMENTS DOCS", grouped["requirements"], 8000)
            + section("COURSE MATERIAL (syllabus, readings, slides)", grouped["course_material"], 6000)
            + section("STUDENT'S PREVIOUS WORK (use ONLY to match voice/style — never copy)", grouped["previous_assignment"], 4000)
        ).strip()

        user_prompt = f"""Assignment Details:
Title: {assignment['title']}
Subject: {assignment['subject']}
Format: {assignment.get('assignment_format', 'general')}
Citation Style: {assignment.get('citation_style', 'apa').upper()}
Requirements: {assignment['requirements']}
Word Count Target: {assignment['word_count']} words (this applies to the DRAFT section only)
Writing Style: {assignment['writing_style']}
Additional Notes: {assignment.get('additional_notes', '')}

{format_specific_brief(assignment)}

{materials_context if materials_context else "No supplemental materials provided."}

Produce the JSON object with the three required keys (outline, draft, writing_tips).
The DRAFT must be approximately {assignment['word_count']} words with Cover Page block, Table of Contents, in-text citations in {assignment.get('citation_style', 'apa').upper()} style, References, and Appendix.
Remember: this is a LEARNING REFERENCE. Encourage the student's own voice in writing_tips."""

        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"assignment-{assignment_id}",
            system_message=ETHICAL_SYSTEM_MESSAGE,
        ).with_model("openai", "gpt-5.2")

        response = await chat.send_message(UserMessage(text=user_prompt))
        parsed = _parse_ai_json(response)

        outline = parsed.get("outline", "").strip()
        draft = parsed.get("draft", "").strip()
        writing_tips = parsed.get("writing_tips", "").strip()

        if not (outline or draft or writing_tips):
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
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(f"Generation complete for assignment {assignment_id}")

    except Exception as e:
        logger.exception(f"Generation failed for {assignment_id}: {e}")
        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {
                "generation_status": "failed",
                "generation_error": str(e)[:500],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )


async def trigger_generation_if_needed(assignment_id: str, background_tasks: BackgroundTasks):
    assignment = await db.assignments.find_one({"id": assignment_id}, {"_id": 0})
    if not assignment:
        return
    gen_status = assignment.get("generation_status", "pending")
    if assignment.get("status") in ("paid", "completed") and gen_status in ("pending", "failed"):
        background_tasks.add_task(run_generation, assignment_id)


async def run_section_regeneration(assignment_id: str, section: str):
    try:
        assignment = await db.assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not assignment:
            return
        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {"generation_status": "generating", "generation_error": None}},
        )

        materials = await db.course_materials.find(
            {"assignment_id": assignment_id},
            {"_id": 0, "extracted_text": 1, "filename": 1, "category": 1},
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
            "keeping the other sections consistent. "
            "Take a meaningfully different angle from the previous version. "
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

{format_specific_brief(assignment)}

EXISTING SECTIONS (for consistency — do NOT regenerate these):
""" + "\n\n".join([f"--- {SECTION_LABELS[k].upper()} ---\n{v[:5000]}" for k, v in keep.items() if v]) + f"""

{materials_context[:12000] if materials_context else ''}

Regenerate ONLY the {target_label.upper()} section with a fresh angle. Return JSON with key "{section}"."""

        from emergentintegrations.llm.chat import LlmChat, UserMessage
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"regen-{assignment_id}-{section}-{uuid.uuid4().hex[:6]}",
            system_message=regen_system,
        ).with_model("openai", "gpt-5.2")
        response = await chat.send_message(UserMessage(text=regen_user))
        parsed = _parse_ai_json(response)
        new_text = (parsed.get(section, "") or "").strip()
        if not new_text:
            new_text = response.strip() if isinstance(response, str) else ""

        regen_field = f"{section}_regens"
        regen_ts_field = f"{section}_regenerated_at"
        prev_version_field = f"{section}_previous"

        previous_text = assignment.get(section) or ""
        now_iso = datetime.now(timezone.utc).isoformat()

        update = {
            section: new_text,
            prev_version_field: previous_text,
            regen_ts_field: now_iso,
            "generation_status": "completed",
            "updated_at": now_iso,
        }
        outline = new_text if section == "outline" else (assignment.get("outline") or "")
        draft = new_text if section == "draft" else (assignment.get("draft") or "")
        writing_tips = new_text if section == "writing_tips" else (assignment.get("writing_tips") or "")
        update["generated_content"] = f"# Outline\n\n{outline}\n\n# Draft\n\n{draft}\n\n# Writing Tips\n\n{writing_tips}"

        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": update, "$inc": {regen_field: 1}},
        )
        logger.info(f"Section regenerated: {assignment_id} / {section}")
    except Exception as e:
        logger.exception(f"Regen failed {assignment_id}/{section}: {e}")
        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {"generation_status": "failed", "generation_error": str(e)[:300]}},
        )
