import os
import sys
from datetime import date, datetime
from typing import Optional, Dict, Any, List, Tuple
import hmac
from fastapi import FastAPI, HTTPException, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Ensure root spectr-ai directory is in sys.path
root_dir = os.path.abspath(os.path.dirname(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from rag.retriever import retrieve_chunks
from agent.router import route_question
from agent.templates import (
    get_metric_summary,
    get_metric_trend,
    compare_periods
)
from agent.synthesis import synthesize_answer

load_dotenv()

RAG_SIMILARITY_THRESHOLD = 0.40  # Max distance threshold for relevant Chroma RAG matches

TEMPLATE_MAP = {
    "get_metric_summary": get_metric_summary,
    "get_metric_trend": get_metric_trend,
    "compare_periods": compare_periods,
}

app = FastAPI(
    title="Spectr AI Service",
    description="Backend microservice for Spectr RAG assistant",
    version="0.2.0"
)

allowed_origin = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000")
origins = [origin.strip() for origin in allowed_origin.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str = Field(..., description="User query question")

@app.get("/")
def read_root():
    return {
        "service": "Spectr AI Service",
        "status": "running",
        "health_check": "/health",
        "ask_endpoint": "/ask",
        "documentation": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

def verify_internal_secret(
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret")
):
    expected_secret = os.getenv("INTERNAL_SHARED_SECRET")
    if not expected_secret or not x_internal_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or missing internal secret header."
        )

    if not hmac.compare_digest(x_internal_secret.strip().encode("utf-8"), expected_secret.strip().encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid internal secret."
        )

def _parse_date_tuple(d_list: Any) -> Tuple[date, date]:
    if isinstance(d_list, (list, tuple)) and len(d_list) == 2:
        return (
            datetime.strptime(str(d_list[0]).strip(), "%Y-%m-%d").date(),
            datetime.strptime(str(d_list[1]).strip(), "%Y-%m-%d").date()
        )
    raise ValueError(f"Invalid date range list: {d_list}")

@app.post("/ask", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_internal_secret)])
def ask_question(
    request: AskRequest,
    x_site_id: Optional[str] = Header(None, alias="X-Site-ID"),
    authorization: Optional[str] = Header(None)
):
    # 1. Get site_id from authenticated session/request context ONLY
    site_id = (x_site_id or authorization or "").strip()
    if not site_id:
        print("[ASK] 401 Rejected: Missing X-Site-ID or Authorization header.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing site_id session header (X-Site-ID or Authorization)."
        )

    question = request.question.strip() if request.question else ""
    if not question:
        print("[ASK] Rejected empty question request.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question parameter cannot be empty."
        )

    print(f"[ASK] Request for site_id='{site_id}' | Question: '{question}'")

    # 2. Call route_question(question, today=date.today())
    query_result = None
    template_name = None
    try:
        route_res = route_question(question, today=date.today())
        template = route_res.get("template")
        params = route_res.get("params", {})
        error = route_res.get("error")

        # 3. Look up in TEMPLATE_MAP and execute with authenticated site_id
        if template and not error and template in TEMPLATE_MAP:
            template_name = template
            metric = params.get("metric")
            template_func = TEMPLATE_MAP[template]

            if template == "get_metric_summary":
                dr = _parse_date_tuple(params.get("date_range"))
                query_result = template_func(site_id, metric, dr)
            elif template == "get_metric_trend":
                dr = _parse_date_tuple(params.get("date_range"))
                gran = params.get("granularity", "day")
                query_result = template_func(site_id, metric, dr, granularity=gran)
            elif template == "compare_periods":
                pa = _parse_date_tuple(params.get("period_a"))
                pb = _parse_date_tuple(params.get("period_b"))
                query_result = template_func(site_id, metric, pa, pb)
    except Exception as err:
        print(f"[ASK] Template Execution Error (fallback to None): {err}")
        query_result = None
        template_name = None

    # 4. Always separately run RAG retriever (vector similarity search)
    rag_context = None
    rag_sources = []
    try:
        retrieved = retrieve_chunks(question, top_k=2)
        docs = retrieved.get("documents", [])
        sources = retrieved.get("sources", [])
        distances = retrieved.get("distances", [])

        min_dist = min(distances) if distances else 999.0

        if min_dist <= RAG_SIMILARITY_THRESHOLD and docs:
            context_blocks = []
            for doc, src in zip(docs, sources):
                context_blocks.append(f"--- Document Source: {src} ---\n{doc}")
            rag_context = "\n\n".join(context_blocks)
            rag_sources = sources
            print(f"[ASK] RAG Match Found (min distance: {min_dist:.4f} <= threshold {RAG_SIMILARITY_THRESHOLD})")
        else:
            print(f"[ASK] RAG Match Exceeded Threshold (min distance: {min_dist:.4f} > threshold {RAG_SIMILARITY_THRESHOLD})")
    except Exception as err:
        print(f"[ASK] RAG Retrieval Error: {err}")
        rag_context = None
        rag_sources = []

    # 8. Determine path category: 'rag_only' | 'query_only' | 'both' | 'neither'
    if query_result is not None and rag_context is not None:
        path_category = "both"
    elif query_result is not None:
        path_category = "query_only"
    elif rag_context is not None:
        path_category = "rag_only"
    else:
        path_category = "neither"

    print(f"[ASK] Path taken: {path_category}")

    # 5. If query_result is None AND rag_context is None -> fast fallback
    if path_category == "neither":
        return {
            "answer": "I don't have information on that.",
            "sources": [],
            "path_taken": path_category,
            "template_used": None
        }

    # 6. Call synthesis function from agent/synthesis.py
    answer, final_sources = synthesize_answer(
        question,
        rag_context=rag_context,
        query_result=query_result,
        template_name=template_name,
        rag_sources=rag_sources
    )

    # 7. Return {"answer": <text>, "sources": [...], "path_taken": ..., "template_used": ...}
    return {
        "answer": answer,
        "sources": final_sources,
        "path_taken": path_category,
        "template_used": template_name
    }
