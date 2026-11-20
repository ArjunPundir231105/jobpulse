from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_jobpulse_app():
    print(">>> 1. Testing /api/config...")
    r = client.get("/api/config")
    assert r.status_code == 200, r.text
    print("    ✓ Config OK:", r.json())

    print("\n>>> 2. Testing /api/jobs...")
    r = client.get("/api/jobs")
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["jobs"]) == 10, f"Expected 10 jobs, got {len(data['jobs'])}"
    print(f"    ✓ Successfully loaded {len(data['jobs'])} jobs from catalog.")

    print("\n>>> 3. Testing /api/search-ai with Query...")
    r = client.post("/api/search-ai", json={
        "query": "Remote Python AI systems",
        "remote_only": True
    })
    assert r.status_code == 200, r.text
    search_data = r.json()
    assert len(search_data["results"]) > 0
    top_match = search_data["results"][0]
    print(f"    ✓ Top match: {top_match['job']['title']} at {top_match['job']['company']} (Score: {top_match['match_score']}%)")
    print(f"    ✓ AI Reasoning: {top_match['ai_reasoning']}")

    print("\n>>> 4. Testing /api/generate-cover-letter...")
    job_id = top_match["job"]["id"]
    r = client.post("/api/generate-cover-letter", json={
        "job_id": job_id,
        "user_notes": "Built high-throughput LLM serving clusters at my last role."
    })
    assert r.status_code == 200, r.text
    cover_letter = r.json().get("cover_letter")
    assert cover_letter and len(cover_letter) > 50
    print("    ✓ Pitch/Cover letter generated successfully:")
    print("    " + cover_letter.replace("\n", "\n    ")[:200] + "...")

    print("\n>>> 5. Testing Static UI Root (/)...")
    r = client.get("/")
    assert r.status_code == 200
    assert "JobPulse" in r.text
    print("    ✓ Web UI HTML served cleanly.")

    print("\n==============================================")
    print("  ALL TESTS PASSED! SIMPLE JOB SEARCH IS READY")
    print("==============================================")

if __name__ == "__main__":
    test_jobpulse_app()
