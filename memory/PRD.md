# AIScholar — Product Requirements

## Original problem statement
Build an app that does assignments for students. $7/280 words, 10% off ≥10k words.
User pivoted → "ethical but same idea". Delivered as **AIScholar** — AI-powered academic writing assistant that produces outlines, reference drafts, and writing tips (NOT submission-ready work).

## What's implemented (Feb 2026)
- **Auth**: JWT register/login, admin flag by OWNER_EMAIL
- **Assignment flow**: 8 formats (general, concert_report, lab_report, literature_review, case_study, masters_thesis, dissertation, masters_thesis_proposal), citation styles (APA/MLA/Harvard/Chicago/IEEE/none), categorized uploads (course_material, previous_assignment, requirements) via Emergent Object Storage
- **Payments**: Stripe checkout with dynamic pricing + 10% bulk discount, webhook fulfillment, **retry-payment** UI, prior-attempt counter
- **AI generation**: Async GPT-5.2 pipeline (outline + draft + writing tips), Cover Page / TOC / References / Appendix enforced
- **Regeneration**: 2 free per section, then $5 Stripe paywall (per-section)
- **Rewrite Workspace**: real-time AI-tells detection & rewrite suggestions
- **Manual AI Check**: Originality.ai ($10) / Turnitin ($15) — routed to admin reviewer via Resend
- **Admin dashboard**: reviewer inbox for AI check orders
- **Free public AI Check**: 5/day/IP rate-limited detector
- **Order confirmation email** on payment success (Resend)
- **Settings page**: Admin-only Resend sender email configuration
- **Post-payment UX**: confetti animation + "AI is drafting, please be patient" banner on assignment page

## Architecture (post-refactor Feb 2026)
```
/app/backend/
├── core.py                 # config, db, models, auth, pricing, storage, extraction
├── server.py               # thin FastAPI bootstrap
└── routers/
    ├── __init__.py
    ├── auth.py             # /api/auth/*
    ├── pricing.py          # /api/pricing/*
    ├── assignments.py      # /api/assignments/*, uploads, regenerate
    ├── generation.py       # AI background tasks (not exposed)
    ├── payments.py         # /api/payments/*, /api/webhook/stripe, confirmation email
    ├── ai_check.py         # /api/ai-check/*, /api/rewrite-coach/*, /api/admin/ai-check/*
    ├── references.py       # /api/assignments/{id}/suggested-references, /api/free-ai-check
    ├── stats.py            # /api/stats/dashboard, /api/
    └── settings.py         # /api/settings/resend (admin)
```
```
/app/frontend/src/pages/
├── LandingPage, AuthPage, Dashboard, NewAssignment, AssignmentDetail
├── RewriteWorkspace, AdminDashboard, FreeAICheck, PaymentSuccess
└── Settings.js              # NEW — Resend domain configuration
```

## Backlog / Roadmap
### P1
- ChatGPT model picker (per-assignment model selection) — user requested but got sidetracked
- Verify domain in Resend so student confirmation emails actually deliver (currently blocked in test mode → onboarding@resend.dev)

### P2
- More tests around new payments/attempts endpoint
- Email templates: personalize sender name, add unsubscribe footer

## Third-party integrations
- **OpenAI GPT-5.2** via Emergent LLM Key
- **Stripe** (test key preloaded)
- **Resend** (API key configured; sender configurable via Settings page)
- **Emergent Object Storage** (uploads/reports)
- **CrossRef** (public references)

## Key endpoints
- `POST /api/payments/checkout`
- `GET /api/payments/attempts/{assignment_id}` — powers retry-payment UI
- `POST /api/webhook/stripe` — triggers generation + confirmation email
- `GET|PUT /api/settings/resend` — admin only
- `GET /api/auth/me-admin`

## Notes for future agents
- `server.py` is a **bootstrap only** — do NOT re-add route logic there
- Router files each import shared code from `core.py` and, when needed, from `routers.generation`
- Confetti uses `canvas-confetti@1.9.4`; fires on `?paid=1` query param and on PaymentSuccess page
- `test_credentials.md` has the admin creds; do NOT overwrite unless auth changes
