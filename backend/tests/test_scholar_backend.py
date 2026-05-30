"""Scholar Academic Writing Assistant - Backend regression tests."""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://study-outline-hub.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="session")
def auth():
    email = f"tester_{uuid.uuid4().hex[:10]}@example.com"
    password = "Test1234!"
    name = "Scholar Tester"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": name}, timeout=30)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and data["user"]["email"] == email
    return {"email": email, "password": password, "token": data["token"], "user_id": data["user"]["id"]}


@pytest.fixture(scope="session")
def headers(auth):
    return {"Authorization": f"Bearer {auth['token']}"}


# ---------------- Auth ----------------
class TestAuth:
    def test_login_valid(self, auth):
        r = requests.post(f"{API}/auth/login", json={"email": auth["email"], "password": auth["password"]}, timeout=30)
        assert r.status_code == 200
        assert "token" in r.json()

    def test_login_invalid(self):
        r = requests.post(f"{API}/auth/login", json={"email": "nouser@example.com", "password": "wrongpass"}, timeout=30)
        assert r.status_code == 401

    def test_me(self, headers, auth):
        r = requests.get(f"{API}/auth/me", headers=headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["email"] == auth["email"]

    def test_me_unauthorized(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401


# ---------------- Pricing ----------------
class TestPricing:
    def test_price_small(self):
        r = requests.post(f"{API}/pricing/calculate", json={"word_count": 280}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["base_price"] == 7.0
        assert d["discount_percent"] == 0
        assert d["final_price"] == 7.0
        assert d["pages"] == 1.0

    def test_price_5000_no_discount(self):
        r = requests.post(f"{API}/pricing/calculate", json={"word_count": 5000}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["discount_percent"] == 0
        # 5000/280 * 7 = 125
        assert round(d["base_price"], 2) == 125.0
        assert round(d["final_price"], 2) == 125.0

    def test_price_10000_discount(self):
        r = requests.post(f"{API}/pricing/calculate", json={"word_count": 10000}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["discount_percent"] == 10
        assert round(d["base_price"], 2) == 250.0
        assert round(d["final_price"], 2) == 225.0

    def test_price_invalid(self):
        r = requests.post(f"{API}/pricing/calculate", json={"word_count": 0}, timeout=30)
        assert r.status_code == 400


# ---------------- Assignments ----------------
class TestAssignments:
    def test_create_assignment(self, headers):
        payload = {
            "title": "TEST_Climate Essay",
            "subject": "Environmental Science",
            "requirements": "Analyze the impact of climate change on polar ecosystems.",
            "word_count": 500,
            "writing_style": "academic",
            "additional_notes": "Focus on biodiversity."
        }
        r = requests.post(f"{API}/assignments", json=payload, headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["title"] == payload["title"]
        assert d["status"] == "draft"
        assert d["outline"] is None
        assert d["draft"] is None
        assert d["writing_tips"] is None
        assert d["generation_status"] == "pending"
        assert d["generation_error"] is None
        pytest.assignment_id = d["id"]

    def test_list_assignments(self, headers):
        r = requests.get(f"{API}/assignments", headers=headers, timeout=30)
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        first = items[0]
        for key in ["outline", "draft", "writing_tips", "generation_status", "generation_error"]:
            assert key in first

    def test_get_assignment(self, headers):
        aid = pytest.assignment_id
        r = requests.get(f"{API}/assignments/{aid}", headers=headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == aid
        assert d["generation_status"] == "pending"

    def test_generate_rejects_unpaid(self, headers):
        aid = pytest.assignment_id
        r = requests.post(f"{API}/assignments/{aid}/generate", headers=headers, timeout=30)
        assert r.status_code == 400
        assert "paid" in r.json().get("detail", "").lower()

    def test_upload_txt(self, headers):
        aid = pytest.assignment_id
        files = {"file": ("notes.txt", b"Sample course notes for climate science.", "text/plain")}
        r = requests.post(f"{API}/assignments/{aid}/upload", headers=headers, files=files, timeout=30)
        assert r.status_code == 200
        # verify length increased
        r2 = requests.get(f"{API}/assignments/{aid}", headers=headers, timeout=30)
        assert len(r2.json()["course_materials"]) >= 1


# ---------------- Payment checkout ----------------
class TestPayments:
    def test_checkout_creates_session(self, headers):
        aid = pytest.assignment_id
        r = requests.post(
            f"{API}/payments/checkout",
            json={"assignment_id": aid, "origin_url": BASE_URL},
            headers=headers,
            timeout=60,
        )
        # may succeed (200) with url/session_id, or fail (500) if stripe test key rejects
        if r.status_code == 200:
            d = r.json()
            assert "url" in d and "session_id" in d
            pytest.session_id = d["session_id"]
        else:
            # still record reason
            pytest.skip(f"Checkout returned {r.status_code}: {r.text[:200]}")

    def test_checkout_rejects_when_paid(self, headers, mongo_db):
        # mark a new assignment as paid, then attempt checkout
        payload = {"title": "TEST_PaidAlready", "subject": "X", "requirements": "x", "word_count": 300}
        r = requests.post(f"{API}/assignments", json=payload, headers=headers, timeout=30)
        assert r.status_code == 200
        aid = r.json()["id"]
        mongo_db.assignments.update_one({"id": aid}, {"$set": {"status": "paid"}})
        r2 = requests.post(
            f"{API}/payments/checkout",
            json={"assignment_id": aid, "origin_url": BASE_URL},
            headers=headers,
            timeout=30,
        )
        assert r2.status_code == 400


# ---------------- AI Generation (bypass payment) ----------------
class TestAIGeneration:
    def test_generation_bypass_flow(self, headers, mongo_db):
        # create fresh assignment
        payload = {
            "title": "TEST_GenEssay",
            "subject": "Environmental Science",
            "requirements": "Brief overview of renewable energy benefits.",
            "word_count": 400,
            "writing_style": "academic",
        }
        r = requests.post(f"{API}/assignments", json=payload, headers=headers, timeout=30)
        assert r.status_code == 200
        aid = r.json()["id"]

        # bypass payment
        res = mongo_db.assignments.update_one({"id": aid}, {"$set": {"status": "paid"}})
        assert res.modified_count == 1

        # trigger generation
        r = requests.post(f"{API}/assignments/{aid}/generate", headers=headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "generating"

        # idempotent call while generating
        r2 = requests.post(f"{API}/assignments/{aid}/generate", headers=headers, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "generating"

        # poll up to ~120s
        completed = False
        final = None
        deadline = time.time() + 130
        while time.time() < deadline:
            time.sleep(6)
            g = requests.get(f"{API}/assignments/{aid}", headers=headers, timeout=30)
            assert g.status_code == 200
            final = g.json()
            gs = final["generation_status"]
            if gs == "completed":
                completed = True
                break
            if gs == "failed":
                break

        assert completed, f"Generation did not complete. Final: status={final.get('status')}, generation_status={final.get('generation_status')}, error={final.get('generation_error')}"
        assert final["status"] == "completed"
        assert isinstance(final["outline"], str) and len(final["outline"]) > 50
        assert isinstance(final["draft"], str) and len(final["draft"]) > 50
        assert isinstance(final["writing_tips"], str) and len(final["writing_tips"]) > 50
        assert isinstance(final["generated_content"], str) and len(final["generated_content"]) > 100


# ---------------- Stats ----------------
class TestStats:
    def test_dashboard_stats(self, headers):
        r = requests.get(f"{API}/stats/dashboard", headers=headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for key in ["total_assignments", "completed_assignments", "paid_assignments", "total_words", "total_spent"]:
            assert key in d
