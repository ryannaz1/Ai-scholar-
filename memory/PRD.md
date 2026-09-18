# AIScholar — Product Requirements

## Original problem statement
Build an app that does assignments for students. $7/280 words, 10% off ≥10k words.
User pivoted → "ethical but same idea". Delivered as **AIScholar** — AI-powered academic writing assistant that produces outlines, reference drafts, and writing tips (NOT submission-ready work).

## What's implemented (Feb 2026)

### Core
- **Auth**: JWT register/login (with optional referral_code), admin flag by OWNER_EMAIL
- **Assignment flow**: 8 formats, citation styles (APA/MLA/Harvard/Chicago/IEEE/none), categorized uploads via Emergent Object Storage
- **AI generation**: Async pipeline, choice of GPT-5.2 / GPT-5.4 Mini / Claude Sonnet 4.6, enforced Cover Page / TOC / References / Appendix
- **Regeneration**: 2 free per section, then $5 Stripe paywall
- **Rewrite Workspace** + real-time AI-tells detection
- **Manual AI Check**: Originality.ai ($10) / Turnitin ($15) — routed to admin reviewer

### Payments
- Stripe checkout with dynamic pricing + 10% bulk discount
- Webhook fulfillment
- **Retry-payment** UI with prior-attempt counter
- **Credits** auto-applied at checkout (leaves $0.50 min charge, ledger recorded)

### Referrals (NEW)
- Every user gets a shareable link `/register?ref={user_id}`
- Referred user + referrer each earn $5 credit when the referred user completes their first paid order
- Dashboard shows referral card: invited count, paid conversions, credit balance, copy-link button
- Register page shows "$5 credit" banner when arriving via referral link

### Assignment Templates
- One-click **Duplicate assignment** (from Dashboard row + AssignmentDetail sidebar) — copies all fields, resets status to draft, no content/materials

### Admin
- Reviewer inbox for AI check orders
- Settings page (Resend sender email + **Send test email** button)
- Order confirmation email fires on successful payment
- Report-ready email fires when reviewer completes an AI check

### Post-payment UX
- Confetti animation + "AI is drafting, please be patient" banner on assignment page
- Order confirmation email

### Public
- Free public AI Check (5/day/IP rate-limited)

## Architecture
```
/app/backend/
├── core.py                 # config, db, models, auth, pricing, storage, credits, referrals, AI_MODELS
├── server.py               # thin FastAPI bootstrap
└── routers/
    ├── auth.py             # /api/auth/* (register accepts referral_code)
    ├── pricing.py
    ├── assignments.py      # CRUD, upload, regenerate, /duplicate
    ├── generation.py       # AI background tasks (uses assignment.ai_model)
    ├── payments.py         # checkout (credits applied), webhook, confirmation email, referral bonus
    ├── ai_check.py         # AI-check orders + admin actions
    ├── references.py       # CrossRef + free public AI check
    ├── stats.py
    ├── settings.py         # /api/settings/resend + /api/settings/resend/test
    └── user.py             # /api/user/referral
```
```
/app/frontend/src/pages/
├── LandingPage, AuthPage (referral-aware), Dashboard (referral card + duplicate), NewAssignment (model picker)
├── AssignmentDetail (retry-payment, confetti, duplicate), RewriteWorkspace, AdminDashboard
├── FreeAICheck, PaymentSuccess (confetti + patient copy)
└── Settings (Resend sender + test-send)
```

## Backlog / Roadmap

### P1
- Resend domain verification (still test mode → student emails restricted)
- Frontend model badge on assignment detail (show which model was used)

### P2
- Regression tests for credits + referrals in `/app/backend/tests/`
- Email templates: personalize sender name, unsubscribe footer

## Third-party integrations
- **OpenAI GPT-5.2 / GPT-5.4 Mini** + **Claude Sonnet 4.6** via Emergent LLM Key
- **Stripe** (test key preloaded)
- **Resend** (API key + configurable sender via Settings)
- **Emergent Object Storage**
- **CrossRef**

## Key endpoints
- `POST /api/auth/register` — accepts `referral_code`
- `POST /api/assignments/{id}/duplicate`
- `GET  /api/user/referral` — returns code, credits, referred count
- `GET|PUT /api/settings/resend`
- `POST /api/settings/resend/test`
- `GET  /api/payments/attempts/{id}`
- Assignment payload now includes `ai_model`

## Notes for future agents
- `server.py` is a **bootstrap only** — never re-add route logic there
- New model support: extend `AI_MODELS` in `core.py` (dict of id → {provider, model, label, description})
- Referral bonus is idempotent via `users.referral_bonus_paid` flag
- Credits are applied at checkout time; deducted only when payment confirms
- `test_credentials.md` has admin creds; do NOT overwrite unless auth changes
