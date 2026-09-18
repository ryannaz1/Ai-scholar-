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
    """Multi-step chained pipeline. Plan → chapter-by-chapter → references → tips.
    Handles up to ~30k words by decomposing the LLM work across many small calls."""
    try:
        assignment = await db.assignments.find_one({"id": assignment_id}, {"_id": 0})
        if not assignment:
            logger.error(f"Generation: assignment {assignment_id} not found")
            return

        await _set_progress(assignment_id, step="Starting generation…", pct=1,
                            gen_status="generating", err=None)

        # Load categorized materials
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

        def section(label, items, cap=6000):
            if not items:
                return ""
            blocks = "\n\n".join(f"[{m['filename']}]\n{m['extracted_text'][:cap]}" for m in items)
            return f"\n\n=== {label} ===\n{blocks}"

        materials_context = (
            section("ASSIGNMENT BRIEF / REQUIREMENTS DOCS", grouped["requirements"], 8000)
            + section("COURSE MATERIAL (readings, slides)", grouped["course_material"], 6000)
            + section("STUDENT'S PREVIOUS WORK (voice only — never copy)", grouped["previous_assignment"], 4000)
        ).strip()

        # STEP 1: Plan
        await _set_progress(assignment_id, step="Planning chapters…", pct=5)
        plan = await _plan_document(assignment, materials_context)
        chapters = plan.get("chapters") or []
        if not chapters:
            # fallback: 1 chapter covering everything
            chapters = [{"id": 1, "title": assignment["title"], "target_words": assignment["word_count"], "key_points": []}]
        outline_md = plan.get("outline_markdown") or _plan_to_markdown(chapters)
        writing_tips_seed = plan.get("writing_tips_seed", "")
        total = len(chapters)
        await _set_progress(assignment_id, step=f"Planned {total} chapter(s)", pct=10,
                            total_chapters=total, chapters_completed=0)

        # STEP 2: Chapter-by-chapter writing with context injection
        chapter_bodies = []
        chapter_summaries = []
        chapter_refs_lists = []  # list[list[str]] — per-chapter mini reference lists
        for i, chap in enumerate(chapters):
            start_pct = 10 + int(70 * (i / max(total, 1)))
            await _set_progress(
                assignment_id,
                step=f"Writing chapter {i+1}/{total}: {chap.get('title', '')[:60]}",
                pct=start_pct,
                chapters_completed=i,
            )
            body, summary, refs_list = await _write_chapter(assignment, chap, chapter_summaries, materials_context)
            chapter_bodies.append(body)
            chapter_summaries.append(summary or f"Chapter {i+1}: {chap.get('title','')}")
            chapter_refs_lists.append(refs_list)
            await _set_progress(
                assignment_id,
                pct=10 + int(70 * ((i + 1) / max(total, 1))),
                chapters_completed=i + 1,
            )

        # STEP 3: Editor — merge/dedupe/alphabetize mini-lists into master References
        await _set_progress(assignment_id, step="Merging references (editor)…", pct=85)
        references_md = await _compile_references(assignment, chapter_refs_lists)

        # STEP 4: Writing tips
        await _set_progress(assignment_id, step="Finalizing writing tips…", pct=92)
        writing_tips = await _write_tips(assignment, outline_md, writing_tips_seed, chapter_summaries)

        # STEP 5: Assemble — strip mini-refs from each chapter body so refs only appear at the end
        cleaned_chapter_bodies = [_strip_mini_references(b) for b in chapter_bodies]
        cover = _make_cover_page(assignment, plan.get("title") or assignment["title"])
        toc = _make_toc(chapters)
        appendix = _make_appendix(assignment)
        full_draft = "\n\n".join([cover, toc, *cleaned_chapter_bodies, references_md, appendix])
        combined = f"# Outline\n\n{outline_md}\n\n# Draft\n\n{full_draft}\n\n# Writing Tips\n\n{writing_tips}"

        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {
                "outline": outline_md,
                "draft": full_draft,
                "writing_tips": writing_tips,
                "generated_content": combined,
                "status": "completed",
                "generation_status": "completed",
                "generation_progress": 100,
                "generation_step": "Complete",
                "generation_error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        logger.info(f"Chained generation complete for {assignment_id} ({total} chapters)")

        # STEP 6: Notify user their doc is ready
        try:
            from routers.payments import send_assignment_ready_email
            await send_assignment_ready_email(assignment_id)
        except Exception as e:
            logger.warning(f"Ready email skipped for {assignment_id}: {e}")

    except Exception as e:
        logger.exception(f"Generation failed for {assignment_id}: {e}")
        await db.assignments.update_one(
            {"id": assignment_id},
            {"$set": {
                "generation_status": "failed",
                "generation_step": "Failed",
                "generation_error": str(e)[:500],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )


# ---------- Chained pipeline helpers ----------

PLANNER_SYSTEM = """You are AIScholar's planning phase. Given an assignment brief, produce a chapter-by-chapter plan for a long-form academic document.

Return ONLY a JSON object (no markdown fences) with this shape:
{
  "title": "<refined title>",
  "total_word_target": <int>,
  "chapters": [
    {"id": 1, "title": "<meaningful chapter title>", "target_words": <int>, "key_points": ["point 1", "point 2"], "notes": "any specific structural guidance"}
  ],
  "outline_markdown": "<full hierarchical outline as markdown ready to display>",
  "writing_tips_seed": "3-5 short bullets on how the student should approach this"
}

Split the total word target across chapters proportionally, respecting the assignment_format:
- <2000 words: 2-4 chapters
- 2000-6000 words: 4-7 chapters
- 6000-15000 words: 7-10 chapters
- 15000+ words: 10-14 chapters

Chapter titles must be substantive, not generic ("Chapter 2"). Use the citation style, subject, and format conventions provided."""


CHAPTER_WRITER_SYSTEM = """You are AIScholar's chapter writer. You are writing ONE chapter of a longer academic reference draft. The goal is to give the student a strong learning scaffold — well-structured, cited, coherent — that they will rewrite in their own voice.

Return ONLY a JSON object (no markdown fences):
{
  "body": "<chapter markdown, starting with `## <chapter title>` heading, ~target_words long, with in-text APA 7 citations in the requested citation style (default APA 7 unless another style is explicitly requested). END the chapter body with a heading `### References Cited in This Chapter` followed by a fully-formatted APA 7 reference list of ONLY the sources you cited in this chapter>",
  "summary": "<2-3 sentence recap of what this chapter argued/covered, for the next chapter's context>",
  "references": ["<full APA 7 entry #1>", "<full APA 7 entry #2>", "..."]
}

MANDATORY RULES (do NOT skip):
1. Every in-text citation MUST have a matching full-form entry in BOTH the chapter's `### References Cited in This Chapter` section AND the top-level `references` JSON array.
2. Reference entries must be complete APA 7 format:
   `Author, A. A., & Author, B. B. (Year). Title of work. Journal Title, Volume(Issue), pp-pp. https://doi.org/xx.xxxx/xxxxxx`
   For books: `Author, A. A. (Year). Title of book (Xth ed.). Publisher.`
3. If you invent a source, keep it internally consistent (same author, year, journal on every mention).
4. The target word count applies to the narrative content — the mini-reference list is extra and not counted toward it.
5. Do NOT include a cover page, table of contents, references section for the whole document, or appendix — those are compiled separately.
6. Do NOT start with "In this chapter, we will..." — write substantively from sentence one.
7. Maintain narrative cohesion with the previous chapter summaries provided."""


REFERENCES_SYSTEM = """You are AIScholar's citation editor. You will receive the mini-reference lists that each chapter writer produced. Your ONLY job is to merge, deduplicate, and alphabetize them into one final master References section.

You will NOT receive the chapter body text — only the reference lists. Do NOT invent new sources. Do NOT hunt for missing citations. Work exclusively with what you're given.

Return ONLY the markdown for the master References section — start with the appropriate heading (`## References` for APA 7 / Harvard / IEEE, `## Works Cited` for MLA, `## Bibliography` for Chicago).

RULES:
1. Deduplicate: entries that describe the same source (same author + year + title) collapse to one canonical entry — prefer the most complete formatting.
2. Alphabetize by first author's surname (APA/Harvard/Chicago/MLA) or by citation number order (IEEE — number them [1], [2], …).
3. Fix obvious inconsistencies (e.g., missing italics markers, inconsistent DOI URLs — normalize to https://doi.org/… form).
4. Preserve every distinct source — do not delete anything just because it looks redundant with something else in a different way.
5. No commentary before or after the list."""


TIPS_SYSTEM = """You are AIScholar's writing coach. Given an outline, brief tips seed, and chapter recaps, produce final actionable "Writing Tips" for the student to make this their own.

Return ONLY the markdown for the writing tips section (no JSON, no fences). Cover:
- How to make the draft personal (their voice)
- Research directions to deepen the argument
- Common mistakes for this subject/format
- Citation-style-specific guidance
- Practical revision workflow

Keep it focused — 400-700 words of concrete advice, not platitudes."""


async def _llm_call(assignment: dict, system_message: str, user_prompt: str, session_suffix: str) -> str:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    from core import resolve_model
    provider, model_name = resolve_model(assignment.get("ai_model"))
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"aischolar-{assignment['id']}-{session_suffix}-{uuid.uuid4().hex[:6]}",
        system_message=system_message,
    ).with_model(provider, model_name)
    return await chat.send_message(UserMessage(text=user_prompt))


async def _plan_document(assignment: dict, materials_context: str) -> dict:
    user_prompt = f"""Assignment Details:
Title: {assignment['title']}
Subject: {assignment['subject']}
Format: {assignment.get('assignment_format', 'general')}
Citation Style: {assignment.get('citation_style', 'apa').upper()}
Requirements: {assignment['requirements']}
Total Word Count Target: {assignment['word_count']} words
Writing Style: {assignment['writing_style']}
Additional Notes: {assignment.get('additional_notes', '')}

{format_specific_brief(assignment)}

{materials_context[:15000] if materials_context else 'No supplemental materials.'}

Produce the JSON plan. Split {assignment['word_count']} words across chapters proportionally."""
    raw = await _llm_call(assignment, PLANNER_SYSTEM, user_prompt, "plan")
    return _parse_ai_json(raw) or {}


async def _write_chapter(assignment: dict, chapter_spec: dict, prev_summaries: list, materials_context: str) -> tuple:
    prev_block = "\n".join(f"- Ch {i+1} recap: {s}" for i, s in enumerate(prev_summaries[-8:])) or "(this is the first chapter)"
    key_points = "\n".join(f"  • {kp}" for kp in (chapter_spec.get("key_points") or []))
    user_prompt = f"""Assignment: {assignment['title']}
Subject: {assignment['subject']}
Format: {assignment.get('assignment_format', 'general')}
Citation Style: {assignment.get('citation_style', 'apa').upper()} (use APA 7 formatting for the mini reference list at the bottom of this chapter regardless of citation_style — the Editor step will convert if needed)
Writing Style: {assignment['writing_style']}

CHAPTER TO WRITE:
Chapter {chapter_spec.get('id')}: {chapter_spec.get('title')}
Target words: {chapter_spec.get('target_words', 500)} (narrative only — the mini reference list is EXTRA)
Key points to cover:
{key_points or '  (open — use your judgment based on chapter title)'}
Structural notes: {chapter_spec.get('notes', '')}

PREVIOUS CHAPTER RECAPS (for continuity):
{prev_block}

RELEVANT SOURCE MATERIAL (excerpts):
{materials_context[:8000] if materials_context else '(none provided)'}

Write this chapter now. Return the JSON with `body`, `summary`, and `references` keys.
- End `body` with a `### References Cited in This Chapter` heading followed by the APA 7 formatted list of ONLY sources you cited in this chapter.
- Duplicate that same list into the `references` JSON array (each entry a full APA 7 string)."""
    raw = await _llm_call(assignment, CHAPTER_WRITER_SYSTEM, user_prompt, f"ch{chapter_spec.get('id', 'x')}")
    parsed = _parse_ai_json(raw) or {}
    body = (parsed.get("body") or "").strip()
    summary = (parsed.get("summary") or "").strip()
    refs_list = parsed.get("references") or []
    # Normalize refs to list[str]
    if isinstance(refs_list, str):
        refs_list = [line.strip() for line in refs_list.split("\n") if line.strip()]
    refs_list = [str(r).strip() for r in refs_list if str(r).strip()]

    if not body:
        body = raw.strip() if isinstance(raw, str) else ""
    if not body.startswith("#"):
        body = f"## {chapter_spec.get('title', 'Chapter')}\n\n{body}"

    # If the JSON `references` array is empty, try to salvage from the body's mini-list
    if not refs_list:
        refs_list = _extract_mini_refs_from_body(body)

    return body, summary, refs_list


MINI_REF_HEADING_RE = re.compile(
    r"\n#{2,4}\s*(references cited in this chapter|chapter references|references)\s*\n",
    re.IGNORECASE,
)


def _strip_mini_references(body: str) -> str:
    """Remove the `### References Cited in This Chapter` section (and everything after it) from a chapter body."""
    if not body:
        return body
    m = MINI_REF_HEADING_RE.search(body)
    if m:
        return body[: m.start()].rstrip() + "\n"
    return body


def _extract_mini_refs_from_body(body: str) -> list:
    """Fallback extractor when the LLM omits the `references` JSON key but includes the mini-list in the body."""
    if not body:
        return []
    m = MINI_REF_HEADING_RE.search(body)
    if not m:
        return []
    tail = body[m.end():].strip()
    # Split entries on blank lines, bullets, or numbered markers
    entries = []
    for chunk in re.split(r"\n\s*\n", tail):
        line = re.sub(r"^\s*(?:[-*+]|\d+\.)\s*", "", chunk.strip())
        if line and len(line) > 15:
            entries.append(line)
    return entries


async def _compile_references(assignment: dict, chapter_refs_lists: list) -> str:
    """chapter_refs_lists: list[list[str]] — one mini-list per chapter."""
    # Deterministic dedup before calling LLM: identical strings collapse
    seen = set()
    flat_entries = []
    for i, chapter_refs in enumerate(chapter_refs_lists, start=1):
        for entry in chapter_refs:
            key = re.sub(r"\s+", " ", entry.lower()).strip()
            if key not in seen:
                seen.add(key)
                flat_entries.append((i, entry))

    if not flat_entries:
        return f"## References\n\n_[No sources were cited in this document.]_\n"

    grouped_by_chapter = {}
    for ch_idx, entry in flat_entries:
        grouped_by_chapter.setdefault(ch_idx, []).append(entry)

    mini_lists_text = "\n\n".join(
        f"CHAPTER {ch}:\n" + "\n".join(f"- {e}" for e in entries)
        for ch, entries in sorted(grouped_by_chapter.items())
    )

    user_prompt = f"""Target Citation Style: {assignment.get('citation_style', 'apa').upper()} (default: APA 7)
Subject: {assignment['subject']}
Title: {assignment['title']}

Merge these per-chapter mini-reference lists into ONE master References section.
- Deduplicate entries that describe the same source
- Alphabetize by first author's surname (or number in citation order for IEEE)
- Convert entries to the target citation style if it differs from APA 7
- Return ONLY the final markdown References section

MINI-LISTS COLLECTED FROM EACH CHAPTER:
{mini_lists_text[:20000]}"""

    raw = await _llm_call(assignment, REFERENCES_SYSTEM, user_prompt, "refs")
    text = (raw or "").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    if not text.lstrip().startswith("#"):
        heading = {
            "mla": "## Works Cited",
            "chicago": "## Bibliography",
        }.get((assignment.get("citation_style") or "apa").lower(), "## References")
        text = f"{heading}\n\n{text}"
    return text


async def _write_tips(assignment: dict, outline_md: str, seed: str, chapter_summaries: list) -> str:
    summaries_block = "\n".join(f"- Ch {i+1}: {s}" for i, s in enumerate(chapter_summaries[:12]))
    user_prompt = f"""Assignment: {assignment['title']}
Subject: {assignment['subject']}
Format: {assignment.get('assignment_format', 'general')}
Citation Style: {assignment.get('citation_style', 'apa').upper()}

Outline (compact):
{outline_md[:4000]}

Chapter recaps:
{summaries_block}

Planner's seed advice: {seed}

Write the final writing tips section."""
    raw = await _llm_call(assignment, TIPS_SYSTEM, user_prompt, "tips")
    text = (raw or "").strip()
    text = re.sub(r"^```(?:markdown|md)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    return text


async def _set_progress(assignment_id: str, step: str = None, pct: int = None,
                        total_chapters: int = None, chapters_completed: int = None,
                        gen_status: str = None, err=""):
    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if step is not None:
        update["generation_step"] = step
    if pct is not None:
        update["generation_progress"] = max(0, min(100, int(pct)))
    if total_chapters is not None:
        update["total_chapters"] = int(total_chapters)
    if chapters_completed is not None:
        update["chapters_completed"] = int(chapters_completed)
    if gen_status is not None:
        update["generation_status"] = gen_status
    if err == "" and gen_status is None:
        pass
    elif err is None:
        update["generation_error"] = None
    await db.assignments.update_one({"id": assignment_id}, {"$set": update})


def _plan_to_markdown(chapters: list) -> str:
    lines = ["## Document Outline\n"]
    for c in chapters:
        lines.append(f"### Chapter {c.get('id')}: {c.get('title')}  \n_Target: {c.get('target_words')} words_")
        for kp in (c.get("key_points") or []):
            lines.append(f"- {kp}")
        lines.append("")
    return "\n".join(lines)


def _make_cover_page(assignment: dict, title: str) -> str:
    return (
        f"# {title}\n\n"
        f"**Student:** [Your Name]  \n"
        f"**Course:** [Course Code – Course Name]  \n"
        f"**Instructor:** [Instructor Name]  \n"
        f"**Date:** [Submission Date]  \n"
        f"**Word count target:** {assignment.get('word_count', 0):,} words  \n"
        f"**Citation style:** {assignment.get('citation_style', 'apa').upper()}\n\n"
        f"---\n"
    )


def _make_toc(chapters: list) -> str:
    lines = ["## Table of Contents\n"]
    for c in chapters:
        lines.append(f"{c.get('id')}. {c.get('title')} — _p. X_")
    lines.append("- References — _p. X_")
    lines.append("- Appendix A — _p. X_\n")
    return "\n".join(lines)


def _make_appendix(assignment: dict) -> str:
    subject = assignment.get("subject", "your topic")
    fmt = assignment.get("assignment_format", "general")
    hint = {
        "lab_report": "raw data tables, calibration curves, or reagent lists",
        "case_study": "interview transcripts, org charts, or supplementary evidence",
        "literature_review": "search-string logs, PRISMA diagram, or excluded-paper table",
        "concert_report": "program notes, ticket stub scan, or listening chronology",
        "masters_thesis": "interview schedules, consent forms, or coding frames",
        "dissertation": "interview schedules, ethics approval, or full-length data tables",
    }.get(fmt, f"supplementary material relevant to {subject}")
    return (
        "## Appendix A\n\n"
        f"_[Placeholder — insert {hint} here. Customize based on your specific work.]_\n"
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
        from core import resolve_model
        provider, model_name = resolve_model(assignment.get("ai_model"))
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        chat = LlmChat(
            api_key=api_key,
            session_id=f"regen-{assignment_id}-{section}-{uuid.uuid4().hex[:6]}",
            system_message=regen_system,
        ).with_model(provider, model_name)
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
