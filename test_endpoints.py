"""
Quick local test — run after starting the server with: uvicorn main:app --reload
Tests all 5 endpoints in sequence.
"""
import httpx
import json

BASE = "http://localhost:8000"

def test():
    c = httpx.Client()

    print("1. GET /v1/healthz")
    r = c.get(f"{BASE}/v1/healthz")
    print(f"   {r.status_code}: {r.json()}\n")

    print("2. GET /v1/metadata")
    r = c.get(f"{BASE}/v1/metadata")
    print(f"   {r.status_code}: {r.json()}\n")

    print("3. POST /v1/context (category)")
    payload = {
        "scope": "category",
        "context_id": "dentists",
        "version": 1,
        "payload": {"slug": "dentists", "voice": {"tone": "peer_clinical", "vocab_taboo": []}, "offer_catalog": [], "peer_stats": {"avg_ctr": 0.030, "avg_rating": 4.4, "avg_review_count": 62}, "digest": [], "patient_content_library": [], "seasonal_beats": [], "trend_signals": []}
    }
    r = c.post(f"{BASE}/v1/context", json=payload)
    print(f"   {r.status_code}: {r.json()}\n")

    print("4. POST /v1/context (merchant)")
    merchant_payload = {
        "scope": "merchant",
        "context_id": "m_001_drmeera",
        "version": 1,
        "payload": {
            "merchant_id": "m_001_drmeera",
            "category_slug": "dentists",
            "identity": {"name": "Dr. Meera Dental", "city": "Delhi", "owner_first_name": "Meera", "languages": ["en", "hi"]},
            "subscription": {"status": "active", "days_remaining": 82, "plan": "Pro"},
            "performance": {"views": 2410, "calls": 18, "ctr": 0.021},
            "offers": [{"title": "Dental Cleaning @ ₹299", "status": "active"}],
            "conversation_history": [],
            "customer_aggregate": {"high_risk_adult_count": 124},
            "signals": ["ctr_below_peer_median"],
            "review_themes": []
        }
    }
    r = c.post(f"{BASE}/v1/context", json=merchant_payload)
    print(f"   {r.status_code}: {r.json()}\n")

    print("5. POST /v1/context (trigger)")
    trigger_payload = {
        "scope": "trigger",
        "context_id": "trg_test_001",
        "version": 1,
        "payload": {
            "id": "trg_test_001",
            "scope": "merchant",
            "kind": "research_digest",
            "source": "external",
            "merchant_id": "m_001_drmeera",
            "customer_id": None,
            "payload": {"category": "dentists", "top_item_id": "d_001"},
            "urgency": 2,
            "suppression_key": "research:dentists:test",
            "expires_at": "2026-12-31T00:00:00Z"
        }
    }
    r = c.post(f"{BASE}/v1/context", json=trigger_payload)
    print(f"   {r.status_code}: {r.json()}\n")

    print("6. POST /v1/tick")
    r = c.post(f"{BASE}/v1/tick", json={"now": "2026-05-03T10:00:00Z", "available_triggers": ["trg_test_001"]})
    print(f"   {r.status_code}: {json.dumps(r.json(), indent=2, ensure_ascii=False)}\n")

    print("7. POST /v1/healthz (check contexts loaded)")
    r = c.get(f"{BASE}/v1/healthz")
    print(f"   {r.status_code}: {r.json()}\n")

    print("All tests passed ✅")

if __name__ == "__main__":
    test()
