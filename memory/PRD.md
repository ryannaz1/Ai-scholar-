# AIScholar — Product Requirements

## Original problem statement
Build an app that does assignments for students. $7/280 words, 10% off ≥10k words. Ethical pivot → **AIScholar**, AI-powered academic writing assistant.

## What's implemented (Feb 2026)

### Chained AI Generation (NEW — replaces single-shot)
Multi-step pipeline scales to 10,000+ words by decomposing the LLM work:
1. **Plan** — 1 API call → returns chapter list `[{id, title, target_words, key_points}]` + outline markdown + writing-tips seed
2. **Write chapters** — 1 API call per chapter, injecting previous chapter summaries for narrative cohesion
3. **Compile references** — 1 API call over the full compiled body, styled per the assignment's citation style
4. **Finalize tips** — 1 API call synthesising the outline + chapter recaps
5. **Assemble** — deterministic markdown: Cover page + TOC + Chapters + References + Appendix
6. **Notify** — Resend "your assignment is ready" email (idempotent via `ready_email_sent`)

Progress fields (`generation_progress` 0-100, `generation_step`, `total_chapters`, `chapters_completed`) power a live progress bar on the assignment page (polling every 4s).

### Everything else already shipped
- Auth (JWT + referral_code), 8 assignment formats, categorized uploads, dynamic Stripe pricing with 10% bulk discount, retry-payment UI, credits application, **duplicate assignment**, **referral bonuses** ($5 both sides), AI model picker (GPT-5.2 / GPT-5.4 Mini / Claude Sonnet 4.6), per-section regenerate (2 free + $5), Rewrite Workspace, manual AI checks (Originality $10 / Turnitin $15), admin reviewer inbox, order-confirmation + report-ready + assignment-ready emails, Settings page with **test-send** button, free public AI check.

## Architecture
```
/app/backend/
├── core.py                 # config, db, models (progress fields), auth, pricing, storage, credits, referrals, AI_MODELS
├── server.py               # thin FastAPI bootstrap
└── routers/
    ├── auth.py             # /api/auth/* (referral_code aware)
    ├── pricing.py
    ├── assignments.py      # CRUD, upload, regenerate, duplicate
    ├── generation.py       # CHAINED PIPELINE: plan → chapters → refs → tips → assemble → email
    ├── payments.py         # checkout, webhook, confirmation + ready emails
    ├── ai_check.py
    ├── references.py
    ├── stats.py
    ├── settings.py         # sender email + test-send
    └── user.py             # /api/user/referral
```

## Backlog / Roadmap
### P1
- Resend domain verification (manual step in resend.com; test-send button lets user validate DNS in 1s)
- Frontend: show AI model badge on assignment detail
- Frontend: show completed chapters as expanded accordion during generation (currently only progress bar)

### P2
- Regression tests under `/app/backend/tests/`
- Celery/Redis worker if we ever need to survive backend restarts mid-generation (current: FastAPI BackgroundTasks — task dies if pod restarts)

## Third-party integrations
- **OpenAI GPT-5.2, GPT-5.4 Mini** + **Claude Sonnet 4.6** via Emergent LLM Key
- **Stripe** (test key preloaded)
- **Resend** (API key + configurable sender)
- **Emergent Object Storage**
- **CrossRef**

## Key endpoints
- `POST /api/auth/register` (accepts `referral_code`)
- `POST /api/assignments/{id}/duplicate`
- `GET  /api/user/referral`
- `GET|PUT /api/settings/resend` + `POST /api/settings/resend/test`
- `GET  /api/payments/attempts/{id}`
- `POST /api/assignments/{id}/generate` triggers chained pipeline

## Notes for future agents
- Chained pipeline lives entirely in `routers/generation.py` — helpers prefixed `_` (`_plan_document`, `_write_chapter`, `_compile_references`, `_write_tips`, `_llm_call`, `_set_progress`, `_make_cover_page`, `_make_toc`, `_make_appendix`)
- To change how the doc is chunked, edit `PLANNER_SYSTEM` in `generation.py`
- Chapter context injection uses `chapter_summaries[-8:]` — expand if you need longer memory
- Ready email requires `APP_PUBLIC_URL` env var for the deep link; falls back to Order ID text otherwise
- `test_credentials.md` has admin creds
