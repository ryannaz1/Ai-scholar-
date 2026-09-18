# AIScholar — Product Requirements

## Original problem statement
Build an app that does assignments for students. $7/280 words, 10% off ≥10k words. Ethical pivot → **AIScholar**, AI-powered academic writing assistant.

## What's implemented (Feb 2026)

### Chained AI Generation with Editor-based citation compilation
Multi-step pipeline scales to 10,000+ words:
1. **Plan** — 1 API call → chapter list + outline + tips seed
2. **Write chapters** — 1 API call per chapter, injecting previous chapter summaries. Each chapter returns `{body, summary, references[]}`. Body ends with `### References Cited in This Chapter` mini-list (APA 7). References array is a JSON-typed list for clean pass-through.
3. **Editor merge** — 1 API call receives ONLY the collected mini-lists (not chapter bodies), deterministically de-duped before the call, then merges/dedupes/alphabetizes into one master References section in the target citation style
4. **Writing tips** — 1 API call
5. **Assemble** — mini-ref sections stripped from each chapter body (`_strip_mini_references`) before final concat; master References appears only at the end, before Appendix
6. **Notify** — Resend "assignment ready" email (idempotent)

Progress fields (`generation_progress` 0-100, `generation_step`, `total_chapters`, `chapters_completed`) power a live progress bar.

**Verified end-to-end (Feb 2026 test)**: 1500-word CRISPR assignment → 4 chapters, 2,451 words, 0 mini-ref headings leaked into final draft, master References at position 13688 (before Appendix at 18175), 18 alphabetized entries.

### Everything already shipped
- Auth (JWT + referral_code), 8 assignment formats, categorized uploads, dynamic Stripe pricing + 10% bulk discount, retry-payment UI, credits application, duplicate assignment, referral bonuses ($5 both sides), AI model picker (GPT-5.2 / GPT-5.4 Mini / Claude Sonnet 4.6), per-section regenerate (2 free + $5), Rewrite Workspace, manual AI checks ($10 / $15), admin reviewer inbox, order-confirmation + report-ready + assignment-ready emails, Settings page with test-send, free public AI check.

## Architecture
```
/app/backend/
├── core.py                 # config, db, models (progress fields), auth, pricing, storage, credits, referrals, AI_MODELS
├── server.py               # thin FastAPI bootstrap
└── routers/
    ├── auth.py             # /api/auth/* (referral_code aware)
    ├── pricing.py
    ├── assignments.py      # CRUD, upload, regenerate, duplicate
    ├── generation.py       # CHAINED PIPELINE + editor-style ref merger + strip_mini_references
    ├── payments.py         # checkout, webhook, confirmation + ready emails
    ├── ai_check.py
    ├── references.py
    ├── stats.py
    ├── settings.py         # sender email + test-send
    └── user.py             # /api/user/referral
```

## Backlog / Roadmap
### P1
- Resend domain verification (manual DNS step; test-send button validates in 1s)
- Frontend: AI model badge on assignment detail
- Frontend: stream completed chapters as expandable cards during generation

### P2
- Regression tests under `/app/backend/tests/` (esp. `_strip_mini_references`, `_extract_mini_refs_from_body`)
- Celery/Redis worker for pod-restart resilience

## Third-party integrations
- **OpenAI GPT-5.2, GPT-5.4 Mini** + **Claude Sonnet 4.6** via Emergent LLM Key
- **Stripe** (test key preloaded)
- **Resend** (API key + configurable sender)
- **Emergent Object Storage**
- **CrossRef**

## Notes for future agents
- Chapter writer prompt (`CHAPTER_WRITER_SYSTEM`) REQUIRES the `references` JSON array. The `_extract_mini_refs_from_body` fallback salvages from body text if the model omits it.
- Editor prompt (`REFERENCES_SYSTEM`) receives ONLY mini-lists, never chapter bodies — this fixes the "editor loses context" bug.
- `MINI_REF_HEADING_RE` matches `## / ### / #### References Cited in This Chapter` / `Chapter References` / `References` (case-insensitive) — extend if you change the heading marker.
- Deterministic dedup happens before the LLM call in `_compile_references` (identical strings, normalized whitespace).
- `test_credentials.md` has admin creds
