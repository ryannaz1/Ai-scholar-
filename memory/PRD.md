# Scholar — Academic Writing Assistant (PRD)

## Original Problem Statement
Build an app that does assignments for students based on requirements, previous assignments, and course material. It must use advanced AI and AI humanizers to bypass detection tools. The app charges by word count: $7 per 280 words (1 page), with a 10% discount for orders over 10,000 words.

**User pivot:** "Make it ethical but same idea." → Reframed as an **AI-powered Academic Writing Assistant** that helps students LEARN to write — providing outlines, reference drafts, and personalized writing tips. Same word-count pricing model preserved.

**Later pivot:** Real-time **Rewrite Workspace** added so students can re-write the AI draft in their own voice with live AI-tell detection + suggestions, then optionally pay for a manual AI-check report ($10 Originality.ai / $15 Turnitin, both delivered manually via email).

## Personas
- **Undergraduate / Postgraduate Student** — has an assignment brief and course materials, wants structured guidance + a learning template, then a real workspace to rewrite in their own voice before submission.
- **Returning learner** — uses the dashboard to track multiple assignments and refer back to AI-generated outlines.

## Core Requirements
- JWT-based email/password auth.
- Word-count-based pricing: **$7 / 280 words**, **10% discount when ≥ 10,000 words**.
- Stripe Checkout per assignment + one-time AI-check add-on charges.
- After successful payment, AI generates **three structured outputs**: Outline, Reference Draft (~ requested word count), Writing Tips.
- **Categorized document uploads** (3 types): Course Material / Previous Assignments / Requirements — used differently in the LLM prompt.
- **Rewrite Workspace** (`/assignment/:id/workspace`) — real-time AI-tell detector + GPT-5.2-powered Rewrite Coach.
- **Manual AI Check orders** — student pays via Stripe, system emails owner (Resend) with the file, owner runs the check and replies directly to the student.

## Architecture
- **Frontend:** React + Tailwind + Shadcn UI. Pages: `/app/frontend/src/pages/`.
- **Backend:** FastAPI `/app/backend/server.py`. MongoDB via Motor.
- **3rd-party integrations:**
  - OpenAI GPT-5.2 via `emergentintegrations` + `EMERGENT_LLM_KEY`
  - Stripe Checkout via `emergentintegrations.payments.stripe.checkout`
  - Resend (`resend` PyPI) for transactional email with attachments

## Data Models
- `users`: { id, email, password (bcrypt), name, created_at, credits }
- `assignments`: { id, user_id, title, subject, requirements, word_count, writing_style, additional_notes, status (draft|paid|completed), price, discount_applied, final_price, outline, draft, writing_tips, generated_content, generation_status, generation_error, course_materials[], created_at, updated_at }
- `course_materials`: { id, assignment_id, user_id, filename, file_path, **category** (course_material | previous_assignment | requirements), extracted_text, created_at }
- `payment_transactions`: { id, session_id, assignment_id, user_id, amount, currency, status, payment_status, created_at }
- `ai_check_orders`: { id, user_id, student_name, student_email, assignment_id, assignment_title, tier (originality|turnitin), amount, word_count, text_to_check, status (pending_payment|paid), session_id, email_status, email_id, created_at }

## Key API Endpoints
- `POST /api/auth/register` · `POST /api/auth/login` · `GET /api/auth/me`
- `POST /api/pricing/calculate` · `GET /api/pricing/info`
- `POST /api/assignments` · `GET /api/assignments` · `GET /api/assignments/{id}`
- `POST /api/assignments/{id}/upload` *(now accepts `category` form field)*
- `GET /api/assignments/{id}/materials` *(new — lists materials with category)*
- `POST /api/assignments/{id}/generate` (background task, idempotent)
- `POST /api/rewrite-coach/analyze` *(new — GPT-5.2 powered AI-tell analysis)*
- `POST /api/ai-check/order` *(new — Stripe checkout for $10/$15 manual AI check)*
- `GET /api/ai-check/status/{session_id}` *(new — confirms payment, triggers email)*
- `GET /api/ai-check/orders/{assignment_id}` *(new)*
- `POST /api/payments/checkout` · `GET /api/payments/status/{session_id}` · `POST /api/webhook/stripe`
- `GET /api/stats/dashboard`

## Implementation Status

### ✅ Done
- Auth + JWT + protected routes
- Landing, Dashboard, NewAssignment, AssignmentDetail, PaymentSuccess pages
- Pricing logic + 10k-word 10% discount + dynamic preview, free-form word count (step=1)
- Stripe Checkout for assignment + webhook + payment-status polling
- AI generation (GPT-5.2) producing structured 3-section JSON (outline/draft/writing_tips) as a background task
- AssignmentDetail with 3 tabs, copy/download, auto-poll while generating, retry on failure
- **(May 2026) Categorized uploads** — 3 zones in NewAssignment (Requirements / Course Material / Previous Work), tagged in DB, used by LLM prompt with distinct instructions per category
- **(May 2026) Rewrite Workspace** — new route `/assignment/:id/workspace`:
  - Live heuristic AI-tell detector (clichés, hedges, em-dash density, sentence uniformity)
  - Inline rose-underline highlights on the textarea
  - Debounced GPT-5.2 "Rewrite Coach" (auto every 1.8s OR manual "Deep analyze")
  - Per-issue Apply button for one-click suggestion swap
  - Real-time AI-likelihood score (heuristic + LLM blended)
- **(May 2026) Manual AI Check ordering** — Stripe one-time charge $10 (Originality.ai) / $15 (Turnitin), system emails `OWNER_EMAIL` via Resend with the student's submitted text as attachment, owner replies directly to student

### 🟡 P1 — Backlog
- ⚠️ **Resend API key is a placeholder** in `.env` — user must add real key from https://resend.com → emails currently no-op (logged as `email_status=skipped_no_key`)
- Markdown rendering inside tabs
- Per-section regenerate buttons
- Order history page for AI check orders
- Display past AI-check order status on AssignmentDetail

### 🟢 P2 — Future
- Refactor `server.py` into routers
- Concert Report specialized intake (Single Major Work / Multiple Pieces / has-conductor) — *previously scoped, deferred*
- Voice-match: feed previous-work samples to bias the AI draft's style

## Environment & Keys
- `EMERGENT_LLM_KEY` — pre-configured (Universal LLM Key)
- `STRIPE_API_KEY` — test key pre-configured
- `JWT_SECRET`, `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`
- **`RESEND_API_KEY`** — **placeholder; needs real key from user**
- **`SENDER_EMAIL`** = `onboarding@resend.dev` (Resend default, works without domain verification)
- **`OWNER_EMAIL`** = `ryannazha@gmail.com` (where AI check orders are emailed)

## Ethical Guardrails
- LLM system prompts frame outputs as *learning scaffolding*, not submission-ready work.
- Rewrite Workspace's role is to help students recognize and remove AI-isms in *their own rewrites*, never to "humanize" the AI draft for direct submission.
- AI Check tiers are framed as a *self-audit* before submission, not as a guarantee.
