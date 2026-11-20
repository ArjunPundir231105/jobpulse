import os
import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Try importing the official Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JobSearchApp")

app = FastAPI(title="JobPulse AI — Simple Job Search with Gemini")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Runtime key store (in addition to env)
RUNTIME_API_KEY: Optional[str] = None

def get_effective_api_key(passed_key: Optional[str] = None) -> Optional[str]:
    if passed_key and passed_key.strip():
        return passed_key.strip()
    if RUNTIME_API_KEY:
        return RUNTIME_API_KEY
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Load jobs dataset
JOBS_FILE = os.path.join(os.path.dirname(__file__), "jobs.json")
def load_jobs() -> List[Dict[str, Any]]:
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

# Request Models
class SearchRequest(BaseModel):
    query: Optional[str] = ""
    resume_text: Optional[str] = ""
    category: Optional[str] = "All"
    remote_only: Optional[bool] = False
    min_salary: Optional[int] = 0
    api_key: Optional[str] = None

class CoverLetterRequest(BaseModel):
    job_id: str
    user_notes: Optional[str] = ""
    user_name: Optional[str] = "Applicant"
    api_key: Optional[str] = None

class KeyRequest(BaseModel):
    api_key: str

# Endpoints
@app.get("/api/config")
def get_config():
    key = get_effective_api_key()
    return {
        "has_api_key": bool(key),
        "genai_sdk_available": GENAI_AVAILABLE,
        "default_model": "gemini-3.8-flash"
    }

@app.post("/api/set-key")
def set_key(req: KeyRequest):
    global RUNTIME_API_KEY
    RUNTIME_API_KEY = req.api_key.strip() if req.api_key else None
    return {"success": True, "has_api_key": bool(RUNTIME_API_KEY)}

@app.get("/api/jobs")
def get_jobs(
    q: Optional[str] = "",
    category: Optional[str] = "All",
    remote_only: Optional[bool] = False,
    min_salary: Optional[int] = 0
):
    all_jobs = load_jobs()
    filtered = []
    q_lower = q.lower().strip() if q else ""

    for job in all_jobs:
        if remote_only and not job.get("is_remote"):
            continue
        if min_salary and job.get("salary_max", 0) < min_salary:
            continue
        if category and category != "All" and job.get("category") != category:
            continue
        if q_lower:
            text = f"{job['title']} {job['company']} {job['location']} {job['summary']} {' '.join(job.get('tags', []))}".lower()
            if q_lower not in text:
                continue
        filtered.append(job)

    return {"jobs": filtered, "total": len(filtered)}

@app.post("/api/search-ai")
def search_ai(req: SearchRequest):
    """
    Uses Gemini API to evaluate user query or resume against jobs,
    providing semantic ranking, match percentage, and customized match reasoning.
    """
    all_jobs = load_jobs()
    api_key = get_effective_api_key(req.api_key)

    # Filter base dealbreakers first (remote, min_salary, category)
    pool = []
    for j in all_jobs:
        if req.remote_only and not j.get("is_remote"):
            continue
        if req.min_salary and j.get("salary_max", 0) < req.min_salary:
            continue
        if req.category and req.category != "All" and j.get("category") != req.category:
            continue
        pool.append(j)

    if not pool:
        return {"results": [], "used_gemini": False, "message": "No jobs match your hard filters."}

    user_context = (req.query or "").strip()
    if req.resume_text and req.resume_text.strip():
        user_context += f"\n[User Resume / Profile]:\n{req.resume_text.strip()}"

    # If no prompt context, return filtered list with default scores
    if not user_context:
        results = [
            {
                "job": j,
                "match_score": 85,
                "ai_reasoning": "Matches your selected filter criteria."
            } for j in pool
        ]
        return {"results": results, "used_gemini": False}

    # Attempt Gemini Semantic Ranking
    if api_key and GENAI_AVAILABLE:
        try:
            client = genai.Client(api_key=api_key)
            
            # Prepare simplified jobs JSON for the prompt
            jobs_summary = [
                {
                    "id": j["id"],
                    "title": j["title"],
                    "company": j["company"],
                    "summary": j["summary"],
                    "tags": j["tags"],
                    "salary": f"${j['salary_min']} - ${j['salary_max']}",
                    "is_remote": j["is_remote"]
                }
                for j in pool
            ]

            prompt = f"""You are an intelligent Job Matching AI.
Evaluate the candidate's search query or resume against these jobs.

Candidate Request / Profile:
\"\"\"
{user_context}
\"\"\"

Available Jobs:
{json.dumps(jobs_summary, indent=2)}

Task:
1. Select the top matching jobs that best fit the candidate's skills, desires, or query.
2. For each, give a match score between 50 and 100.
3. Write a concise, 1-2 sentence personalized explanation: 'Why this job matches you'.

Return pure JSON only in this exact format:
[
  {{
    "job_id": "job-id-here",
    "match_score": 95,
    "ai_reasoning": "Clear explanation of why this matches their specific query or skills."
  }}
]
"""
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2
                )
            )

            scored_items = json.loads(response.text)
            score_map = {item["job_id"]: item for item in scored_items if "job_id" in item}

            # Merge with full job objects
            results = []
            for j in pool:
                if j["id"] in score_map:
                    results.append({
                        "job": j,
                        "match_score": score_map[j["id"]].get("match_score", 80),
                        "ai_reasoning": score_map[j["id"]].get("ai_reasoning", "Relevant match based on your skills.")
                    })

            # Sort descending by match_score
            results.sort(key=lambda x: x["match_score"], reverse=True)

            return {
                "results": results,
                "used_gemini": True,
                "count": len(results)
            }
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            # Fall back to heuristic ranking below

    # Fallback heuristic ranking if no Gemini key or on error
    results = []
    keywords = [w.lower() for w in user_context.replace(",", " ").split() if len(w) > 2]
    for j in pool:
        text = f"{j['title']} {j['company']} {j['summary']} {' '.join(j['tags'])}".lower()
        matched = [k for k in keywords if k in text]
        score = min(98, 60 + len(matched) * 10) if matched else 55
        reason = (
            f"Keyword overlap with {', '.join(matched[:3])}."
            if matched else "Available in catalog matching your filter criteria."
        )
        results.append({
            "job": j,
            "match_score": score,
            "ai_reasoning": reason
        })

    results.sort(key=lambda x: x["match_score"], reverse=True)
    return {
        "results": results,
        "used_gemini": False,
        "note": "Connect your Gemini API key in the navbar to enable deep reasoning!"
    }

@app.post("/api/generate-cover-letter")
def generate_cover_letter(req: CoverLetterRequest):
    """Uses Gemini API to generate a crisp 3-paragraph tailored cover letter."""
    all_jobs = load_jobs()
    job = next((j for j in all_jobs if j["id"] == req.job_id), None)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    api_key = get_effective_api_key(req.api_key)
    if not api_key or not GENAI_AVAILABLE:
        # Fallback template
        return {
            "cover_letter": f"Dear Hiring Team at {job['company']},\n\nI am writing to express my strong enthusiasm for the {job['title']} position. With my background and passion for {', '.join(job.get('tags', ['technology'])[:3])}, I am confident in my ability to make an immediate impact on your team.\n\n{job['summary']}\n\nI would welcome the opportunity to discuss how my experience aligns with your goals. Thank you for your time and consideration.\n\nSincerely,\n{req.user_name or 'Applicant'}",
            "used_gemini": False
        }

    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""Write a professional, concise, and compelling 3-paragraph cover letter.
Candidate Name: {req.user_name or 'Applicant'}
Target Job: {job['title']} at {job['company']}
Role Summary: {job['summary']}
Role Requirements: {', '.join(job.get('requirements', []))}
Applicant's Background Notes / Pitch:
{req.user_notes or 'Passionate about this problem space and eager to contribute proven skills.'}

Tone: Confident, direct, conversational (no corporate clichés). Keep it under 250 words.
"""
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3
            )
        )
        return {"cover_letter": response.text.strip(), "used_gemini": True}
    except Exception as e:
        logger.error(f"Cover letter generation error: {e}")
        return {
            "cover_letter": f"Dear Hiring Team at {job['company']},\n\nI am thrilled to apply for the {job['title']} position. I bring relevant experience in {', '.join(job['tags'][:3])}.\n\nLooking forward to speaking with your team!\n\nBest regards,\n{req.user_name}",
            "used_gemini": False
        }

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
