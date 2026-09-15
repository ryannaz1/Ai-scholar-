"""Tests for the newly added features in AIScholar:
- citation_style on assignments
- suggested-references (CrossRef)
- free-ai-check public endpoint (rate limited, char limit)
- rewrite-coach 200k char cap (no 400 on >20k)
- mandatory academic components in draft (Cover/TOC/Refs/Appendix)
"""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

def _load_backend_url():
    v = os.environ.get('REACT_APP_BACKEND_URL')
    if not v:
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    return (v or "").rstrip('/')

BASE_URL = _load_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


@pytest.fixture(scope="module")
def mongo_db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def auth():
    email = f"tester_{uuid.uuid4().hex[:10]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Test1234!", "name": "New Feat Tester"},
                      timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def headers(auth):
    return {"Authorization": f"Bearer {auth['token']}"}


# ---------------- Citation Style ----------------
class TestCitationStyle:
    def test_default_apa(self, headers):
        r = requests.post(f"{API}/assignments", headers=headers, timeout=30, json={
            "title": "TEST_default_style", "subject": "History",
            "requirements": "WWII overview", "word_count": 300,
        })
        assert r.status_code == 200, r.text
        assert r.json().get("citation_style") == "apa"

    def test_mla_persists(self, headers):
        r = requests.post(f"{API}/assignments", headers=headers, timeout=30, json={
            "title": "TEST_mla_style", "subject": "Literature",
            "requirements": "Hamlet analysis", "word_count": 300,
            "citation_style": "mla",
        })
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        assert r.json().get("citation_style") == "mla"
        g = requests.get(f"{API}/assignments/{aid}", headers=headers, timeout=30)
        assert g.json().get("citation_style") == "mla"


# ---------------- Suggested References (CrossRef) ----------------
class TestSuggestedReferences:
    def test_returns_refs(self, headers):
        r = requests.post(f"{API}/assignments", headers=headers, timeout=30, json={
            "title": "Climate change effects on coastal communities",
            "subject": "Environmental Science",
            "requirements": "Sea-level rise, adaptation, vulnerability of coastal populations.",
            "word_count": 500,
        })
        aid = r.json()["id"]
        rr = requests.get(f"{API}/assignments/{aid}/suggested-references", headers=headers, timeout=30)
        assert rr.status_code == 200, rr.text
        data = rr.json()
        assert "references" in data
        if data.get("error"):
            pytest.skip(f"CrossRef unavailable: {data['error']}")
        assert isinstance(data["references"], list)
        assert len(data["references"]) > 0, "Expected some references for climate topic"
        first = data["references"][0]
        for k in ["title", "authors", "year"]:
            assert k in first
        assert "doi" in first or "url" in first

    def test_404_wrong_assignment(self, headers):
        rr = requests.get(f"{API}/assignments/nonexistent-id/suggested-references",
                          headers=headers, timeout=15)
        assert rr.status_code == 404


# ---------------- Free AI Check (public, no auth) ----------------
class TestFreeAICheck:
    def test_valid_short(self):
        text = "In today's world it is important to note that we must delve into the multifaceted implications of technology."
        r = requests.post(f"{API}/free-ai-check", json={"text": text}, timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "ai_likelihood" in d
        assert "issues" in d
        assert "remaining_today" in d
        assert isinstance(d["issues"], list)

    def test_over_limit_400(self):
        text = "a " * 2100  # 4200 chars > 4000
        r = requests.post(f"{API}/free-ai-check", json={"text": text}, timeout=30)
        assert r.status_code == 400
        assert "Free tier limit" in r.json().get("detail", "") or "4000" in r.json().get("detail", "")

    def test_empty_400(self):
        r = requests.post(f"{API}/free-ai-check", json={"text": "   "}, timeout=30)
        assert r.status_code == 400


# ---------------- Rewrite Coach 200k cap ----------------
class TestRewriteCoachCap:
    def test_accepts_30k(self, headers):
        text = ("The quick brown fox jumps over the lazy dog. " * 700)  # ~30k chars
        assert len(text) > 20000
        r = requests.post(f"{API}/rewrite-coach/analyze",
                          headers=headers,
                          json={"text": text},
                          timeout=180)
        assert r.status_code != 400, f"Expected non-400 for 30k text, got: {r.status_code} {r.text[:200]}"
        assert r.status_code == 200, r.text


# ---------------- Mandatory academic components ----------------
class TestMandatoryComponents:
    def test_draft_has_cover_toc_refs_appendix(self, headers, mongo_db):
        r = requests.post(f"{API}/assignments", headers=headers, timeout=30, json={
            "title": "TEST_MandatoryComps",
            "subject": "Sociology",
            "requirements": "Short overview of urbanization impacts.",
            "word_count": 300,
            "citation_style": "apa",
        })
        aid = r.json()["id"]
        mongo_db.assignments.update_one({"id": aid}, {"$set": {"status": "paid"}})
        g = requests.post(f"{API}/assignments/{aid}/generate", headers=headers, timeout=30)
        assert g.status_code == 200

        deadline = time.time() + 180
        final = None
        while time.time() < deadline:
            time.sleep(8)
            gg = requests.get(f"{API}/assignments/{aid}", headers=headers, timeout=30)
            final = gg.json()
            if final.get("generation_status") in ("completed", "failed"):
                break

        assert final and final.get("generation_status") == "completed", \
            f"Generation status={final.get('generation_status') if final else None}, err={final.get('generation_error') if final else None}"
        draft = (final.get("draft") or "").lower()
        assert draft, "draft must be non-empty"

        # Case-insensitive substring checks (with variants)
        assert any(s in draft for s in ["cover page", "title page", "course"]), "Missing cover/course block"
        assert any(s in draft for s in ["table of contents", "contents\n", "toc"]), "Missing TOC"
        assert any(s in draft for s in ["references", "works cited", "bibliography"]), "Missing refs"
        assert "appendix" in draft, "Missing appendix"
