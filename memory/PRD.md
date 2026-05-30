# Scholar — Academic Writing Assistant (PRD)

## Original Problem Statement
Build an app that does assignments for students based on requirements, previous assignments, and course material. It must use advanced AI and AI humanizers to bypass detection tools. The app charges by word count: $7 per 280 words (1 page), with a 10% discount for orders over 10,000 words.

**User pivot:** "Make it ethical but same idea." → Reframed as an **AI-powered Academic Writing Assistant** that helps students LEARN to write — providing outlines, reference drafts, and personalized writing tips. Same word-count pricing model preserved.

## Personas
- **Undergraduate / Postgraduate Student** — has an assignment brief and course materials, wants structured guidance and a learning template, not a finished submission.
- **Returning learner** — uses the dashboard to track multiple assignments and refer back to AI-generated outlines.

## Core Requirements
- JWT-based email/password auth (register, login, persisted session via axios interceptors).
- Word-count-based pricing: **$7 / 280 words**, **10% discount when ≥ 10,000 words**.
- Stripe Checkout integration for paying per assignment.
- After successful payment, AI generates **three structured outputs**: Outline, Reference Draft (~ requested word count), Writing Tips.
- Course material upload (PDF / DOCX / TXT) feeds into the LLM context.
- Dashboard with assignment list, status, stats (total assignments, completed, total words, total spent).

## Architecture
- **Frontend:** React + Tailwind + Shadcn UI (Fraunces serif accents, "paper" theme). Pages under `/app/frontend/src/pages/`.
- **Backend:** FastAPI single-file `/app/backend/server.py` (auth, assignments, pricing, payments, AI generation routes). MongoDB via Motor.
- **3rd-party integrations:**
  - OpenAI GPT-5.2 via `emergentintegrations` library + `EMERGENT_LLM_KEY`
  - Stripe Checkout via `emergentintegrations.payments.stripe.checkout`

## Data Models
- `users`: { id, email, password (bcrypt), name, created_at, credits }
- `assignments`: { id, user_id, title, subject, requirements, word_count, writing_style, additional_notes, status (draft|paid|completed), price, discount_applied, final_price, **outline, draft, writing_tips**, generated_content (combined), **generation_status (pending|generating|completed|failed)**, generation_error, course_materials[], created_at, updated_at }
- `course_materials`: { id, assignment_id, user_id, filename, file_path, extracted_text (≤50k chars), created_at }
- `payment_transactions`: { id, session_id, assignment_id, user_id, amount, currency, status, payment_status, created_at }

## Key API Endpoints
- `POST /api/auth/register` · `POST /api/auth/login` · `GET /api/auth/me`
- `POST /api/pricing/calculate` · `GET /api/pricing/info`
- `POST /api/assignments` · `GET /api/assignments` · `GET /api/assignments/{id}`
- `POST /api/assignments/{id}/upload` (course material)
- `POST /api/assignments/{id}/generate` (background task, idempotent)
- `POST /api/payments/checkout` · `GET /api/payments/status/{session_id}` · `POST /api/webhook/stripe`
- `GET /api/stats/dashboard`

## Implementation Status

### ✅ Done (Feb 2026)
- Auth + JWT + protected routes
- Landing, Dashboard, NewAssignment, AssignmentDetail, PaymentSuccess pages
- Pricing logic + 10k-word 10% discount + dynamic preview
- Course material upload + PDF/DOCX/TXT text extraction
- Stripe Checkout session creation + webhook handler
- **Stripe webhook now updates assignment to `paid` AND auto-triggers AI generation** (also covered via `/payments/status/{session_id}` polling fallback)
- **AI generation** via GPT-5.2 producing **structured 3-section JSON** (outline / draft / writing_tips), executed as a FastAPI BackgroundTask
- AssignmentDetail page with **3 tabs**, copy-per-section, download-all, auto-poll while generating, retry on failure

### 🟡 P1 — Backlog
- Multiple file uploads UI in NewAssignment (backend supports it; UI single-file)
- Rich markdown rendering (currently `whitespace-pre-wrap`)
- Per-section regenerate buttons
- Email notifications when generation completes

### 🟢 P2 — Future
- Refactor `server.py` into routers (`auth/`, `assignments/`, `payments/`, `ai/`)
- AI plagiarism / originality coaching that compares the user's own draft to the reference
- Pricing tiers / subscriptions
- Admin dashboard

## Environment & Keys
- `EMERGENT_LLM_KEY` — pre-configured (Universal LLM Key)
- `STRIPE_API_KEY` — test key pre-configured
- `JWT_SECRET`, `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS` — `.env`

## Ethical Guardrails (System Prompt)
The LLM is instructed to produce *learning scaffolding*, not submission-ready work, and to encourage students to add their own voice via the writing-tips section.
