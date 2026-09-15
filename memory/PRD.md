# AIScholar — AI-Powered Academic Writing Assistant (PRD)

## Original Problem Statement
Build an app that does assignments for students. Pivoted by user to ethical: AI-powered Academic Writing Assistant that helps students LEARN. Same pricing model preserved.

Later rebranded to **AIScholar** for SEO.

## Personas
- Undergraduate / Postgraduate student (essays, lab reports, lit reviews, case studies)
- **Master's / Doctoral candidate** (thesis chapters & proposals — explicitly emphasized)
- Returning learner

## Core Requirements
- JWT auth · word-count pricing ($7 / 280 words · 10% discount ≥10k) · Stripe Checkout · GPT-5.2 generation
- Categorized doc uploads · Real-time Rewrite Workspace · Manual AI Check ordering
- Reviewer Dashboard · Order History · Per-section regenerate (2 free + $5)
- 8 Assignment Formats: General, Concert Report, Lab Report, Literature Review, Case Study, **Master's Thesis (chapter)**, **Master's Thesis Proposal**, **Doctoral Dissertation (chapter)**

## Architecture
- React 18 + Tailwind + Shadcn UI · react-markdown for tab content
- FastAPI single-file (`/app/backend/server.py`, ~1300 lines) + MongoDB (Motor)
- emergentintegrations: GPT-5.2 + Stripe Checkout
- Resend (PyPI) for transactional email with attachments

## Data Models
- `users`: id, email, password (bcrypt), name, created_at, credits
- `assignments`: id, user_id, title, subject, requirements, word_count, writing_style, additional_notes, status, price, discount_applied, final_price, **assignment_format**, **concert_structure**, **has_conductor**, outline, draft, writing_tips, generated_content, generation_status, generation_error, **{section}_regens**, **{section}_regenerated_at**, **{section}_previous**, course_materials[], created_at, updated_at
- `course_materials`: id, assignment_id, user_id, filename, file_path, category (course_material | previous_assignment | requirements), extracted_text, created_at
- `payment_transactions`: standard
- `ai_check_orders`: id, user_id, student_name, student_email, assignment_id, assignment_title, tier, amount, word_count, text_to_check, status, session_id, email_status, report_filename, report_path, completion_notes, completed_at, created_at
- `regen_orders`: id, session_id, user_id, assignment_id, section, amount, status, created_at

## Key API Endpoints
- Auth/Pricing/Assignments — as before
- `POST /api/assignments/{id}/upload` (form: file, category)
- `GET /api/assignments/{id}/materials`
- `POST /api/assignments/{id}/generate`
- `POST /api/assignments/{id}/regenerate/{section}` (2 free, then $5 Stripe)
- `GET /api/assignments/{id}/regen-status/{session_id}`
- `POST /api/rewrite-coach/analyze` (no real word cap; 200k chars max)
- `POST /api/ai-check/order` · `GET /api/ai-check/status/{sid}` · `GET /api/ai-check/orders/{aid}` · `GET /api/ai-check/orders/{oid}/report`
- `POST /api/admin/ai-check/orders/{oid}/complete` (admin) · `POST /api/admin/ai-check/orders/{oid}/mark-in-progress` · `GET /api/admin/ai-check/orders` · `GET /api/auth/me-admin`
- `POST /api/payments/checkout` · `GET /api/payments/status/{sid}` · `POST /api/webhook/stripe`

## Implementation Status

### ✅ Done (Sep 2026)
- BUG FIX — Target Word Count no longer clamped to 280; accepts any integer ≥1
- UX — AssignmentDetail generating-card now adaptive: "Long assignment (~X words) — 2–4 minutes" for ≥3000 words, "20–60 seconds" otherwise
- Citation Style selector on NewAssignment (APA / MLA / Harvard / Chicago / IEEE / none) — persisted, passed to LLM
- LLM system prompt MANDATES Cover Page + Table of Contents + in-text citations in chosen style + References + Appendix on every DRAFT
- **Suggested Public References** panel on AssignmentDetail — CrossRef API integration (free, no auth). Returns title, authors, year, DOI, URL, venue, abstract excerpt for 8 relevant papers per assignment
- **Free public AI Detector** at `/ai-checker` — no signup, 4000 char limit, 5 checks/IP/day rate-limited. Prominent CTAs in landing nav + hero. Full SEO copy on the page.
- Landing hero: two CTAs — Start Writing (primary) + FREE Try the AI Detector (secondary, accent color)
- Brand pivot to **AIScholar** across all UI + SEO (title, meta description, OpenGraph, Twitter, JSON-LD WebApplication schema, robots.txt, sitemap.xml)
- Landing-page SEO copy: hero subtitle now mentions essays / lab reports / lit reviews / case studies / Master's thesis chapters + GPT-5.2 + "built to help you learn, not cheat"
- 8 Assignment Formats with branch-specific prompts:
  - lab_report → IMRaD (Abstract / Intro / Methods / Results / Discussion / Conclusion / References)
  - literature_review → Thematic synthesis (NOT one-paragraph-per-paper)
  - case_study → SWOT / Porter / PESTEL-style framework analysis
  - masters_thesis → Full Ch1–Ch6 outline + one sampled chapter draft + supervisor-meeting / viva tips
  - masters_thesis_proposal → Aim/Objectives/RQs/Methodology/Timeline/References
  - dissertation → Doctoral-level depth on the same chapter structure
- Per-section regenerate now persists `{section}_regenerated_at` + `{section}_previous`
- AssignmentDetail: shows "Last regenerated Xm ago · regen #N" + **"View previous version" toggle** that renders the prior version in an amber-highlighted panel above the current

### 🟡 P1 — Backlog
- ⚠️ **Stripe live key**: app currently uses the test key `STRIPE_API_KEY` (pre-configured). User must swap to their live key from https://dashboard.stripe.com/apikeys to receive real payouts. Step: edit `/app/backend/.env`, change `STRIPE_API_KEY=sk_live_xxx`, restart backend.
- ⚠️ **Resend domain verification** still needed for the "report ready" email to students.
- Format-aware per-section regenerate (keep format prompt during regen — already done; verify)

### 🟢 P2 — Future
- Refactor `server.py` into routers (deferred per user)
- Inline character-level diff highlighting between current and previous version
- "Pro Pass" subscription ($19/mo unlimited regens + priority AI check)
- Markdown rendering inside Rewrite Workspace too

## SEO Configuration
- Title: `AIScholar — AI Essay Writer, Thesis Outline & Academic Writing Assistant`
- Meta description: includes "GPT-5.2", "Master's thesis", "essays, lab reports, literature reviews, case studies"
- Keywords: AI essay writer, AI academic writing assistant, thesis outline generator, dissertation help AI, AI study tool, GPT essay outline, AIScholar, masters thesis AI, literature review AI, lab report assistant, concert report AI, college writing help
- Canonical: https://aischolar.app/
- robots.txt: indexes /, /login, /register; disallows authenticated routes
- sitemap.xml: lists 3 public URLs
- JSON-LD WebApplication schema with $7 base offer

## Environment & Keys
- `EMERGENT_LLM_KEY` — pre-configured
- `STRIPE_API_KEY` — currently test key; replace with user's live key from dashboard.stripe.com
- `RESEND_API_KEY` — `re_G4se9ug1_...` (real)
- `SENDER_EMAIL=onboarding@resend.dev` (test mode — only sends TO ryannazha@gmail.com until domain verified)
- `OWNER_EMAIL=ryannazha@gmail.com`
