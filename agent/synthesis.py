import os
import sys
import json
import time
from typing import Optional, Dict, Any, List, Tuple
from fastapi import HTTPException, status
from groq import Groq, RateLimitError, APIError, APIConnectionError
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

_groq_client: Optional[Groq] = None

def get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable is not set.")
        _groq_client = Groq(api_key=api_key)
    return _groq_client

def format_query_result_plain(query_result: Any, template_name: Optional[str] = None) -> str:
    """
    Formats SQL query_result into plain language, spelling out every field explicitly
    instead of raw JSON. Handles null values with explicit 'not available' descriptions.
    """
    if not query_result:
        return ""

    if isinstance(query_result, list):
        lines = ["Data for this question (Metric Trend):"]
        for pt in query_result:
            if isinstance(pt, dict):
                d = pt.get("date", "N/A")
                v = pt.get("value")
                v_str = f"{v}" if v is not None else "not available — no data"
                lines.append(f"- {d}: {v_str}")
        return "\n".join(lines)

    if isinstance(query_result, dict):
        metric = query_result.get("metric", "unknown")
        site_id = query_result.get("site_id", "unknown")

        if "current_period" in query_result:
            cp = query_result.get("current_period", ("N/A", "N/A"))
            pp = query_result.get("previous_period", ("N/A", "N/A"))
            c_val = query_result.get("current_value")
            p_val = query_result.get("previous_value")
            pct = query_result.get("pct_change")

            c_val_str = f"{c_val}" if c_val is not None else "not available — no data in current period"
            p_val_str = f"{p_val}" if p_val is not None else "not available — no data in the comparison period"
            pct_str = f"{pct}%" if pct is not None else "not available — no data in the comparison period"

            return (
                "Data for this question (Metric Summary):\n"
                f"- Metric: {metric}\n"
                f"- Site ID: {site_id}\n"
                f"- Current period value ({cp[0]} to {cp[1]}): {c_val_str}\n"
                f"- Previous period value ({pp[0]} to {pp[1]}): {p_val_str}\n"
                f"- Percent change: {pct_str}"
            )

        elif "period_a" in query_result and "period_b" in query_result:
            p_a = query_result.get("period_a", {})
            p_b = query_result.get("period_b", {})
            pct = query_result.get("pct_change")

            val_a = p_a.get("value") if isinstance(p_a, dict) else None
            val_b = p_b.get("value") if isinstance(p_b, dict) else None
            range_a = p_a.get("range", ("N/A", "N/A")) if isinstance(p_a, dict) else ("N/A", "N/A")
            range_b = p_b.get("range", ("N/A", "N/A")) if isinstance(p_b, dict) else ("N/A", "N/A")

            val_a_str = f"{val_a}" if val_a is not None else "not available — no data in Period A"
            val_b_str = f"{val_b}" if val_b is not None else "not available — no data in Period B"
            pct_str = f"{pct}%" if pct is not None else "not available — no data in baseline period"

            return (
                "Data for this question (Period Comparison):\n"
                f"- Metric: {metric}\n"
                f"- Site ID: {site_id}\n"
                f"- Period A ({range_a[0]} to {range_a[1]}): {val_a_str}\n"
                f"- Period B ({range_b[0]} to {range_b[1]}): {val_b_str}\n"
                f"- Percent change: {pct_str}"
            )

        elif "trend" in query_result:
            points = query_result.get("trend", [])
            lines = [f"Data for this question (Metric Trend for {metric}):"]
            for pt in points:
                if isinstance(pt, dict):
                    d = pt.get("date", "N/A")
                    v = pt.get("value")
                    v_str = f"{v}" if v is not None else "not available — no data"
                    lines.append(f"- {d}: {v_str}")
            return "\n".join(lines)

    return f"Data for this question:\n{json.dumps(query_result, indent=2)}"

def synthesize_answer(
    question: str,
    rag_context: Optional[str] = None,
    query_result: Optional[Any] = None,
    template_name: Optional[str] = None,
    rag_sources: Optional[List[str]] = None
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Synthesizes a natural language answer using Groq inference based on rag_context and/or query_result.
    Returns (answer_string, list_of_source_dicts).
    """
    if query_result is None and rag_context is None:
        return "I don't have information on that.", []

    sections = []

    if rag_context:
        sections.append(f"Background information:\n{rag_context}")

    if query_result is not None:
        plain_data_str = format_query_result_plain(query_result, template_name=template_name)
        sections.append(plain_data_str)

    combined_context = "\n\n".join(sections)

    prompt = f"""You are Ask Spectr, an expert AI assistant for the Spectr web analytics platform.
Answer the user's question accurately using ONLY the context provided below.

User Question: {question}

Context Information:
{combined_context}

STRICT INSTRUCTIONS:
- Only use the exact numbers given above. Never calculate, estimate, or infer a number that wasn't provided.
- If percent change is marked as not available, say so plainly instead of stating any percentage.
- If a metric value came from a period with no underlying data, say the data is unavailable for that period rather than reporting a value of zero as if it were meaningful.
- Format LCP and INP as milliseconds and explicitly mention the unit (e.g. "ms" or "milliseconds"). Format CLS as a unitless score. Format bounce_rate as a percentage (%). Format unique_visitors and page_views as raw counts.
- If both background information and data are given, weave them into one cohesive, natural answer — don't just list them separately.
- If neither background information nor data is available, respond with "I don't have information on that."

Answer:"""

    client = get_groq_client()
    answer = None
    last_err = None

    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
            )
            raw_ans = response.choices[0].message.content
            if raw_ans:
                answer = raw_ans.strip()
            break
        except RateLimitError as rle:
            last_err = rle
            wait_time = 3.0 * (attempt + 1)
            try:
                if hasattr(rle, "response") and rle.response is not None:
                    hdr = rle.response.headers.get("retry-after")
                    if hdr:
                        wait_time = float(hdr) + 0.5
            except Exception:
                pass
            print(f"[SYNTHESIS] Groq 429 rate limit encountered, retrying in {wait_time}s...")
            time.sleep(wait_time)
            continue
        except Exception as err:
            last_err = err
            print(f"[SYNTHESIS] Groq Generation Error: {err}")
            break

    if answer is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM generation failed: {str(last_err)}"
        )

    fallback_phrases = [
        "don't have information",
        "do not have information",
        "no information",
        "not mentioned in the context",
        "does not contain information",
        "no details provided"
    ]
    if any(phrase in answer.lower() for phrase in fallback_phrases):
        return "I don't have information on that.", []

    structured_sources: List[Dict[str, str]] = []

    if query_result is not None:
        detail_val = template_name or "query"
        structured_sources.append({"type": "query", "detail": detail_val})

    if rag_context and rag_sources:
        for doc_name in rag_sources:
            structured_sources.append({"type": "doc", "detail": doc_name})

    return answer, structured_sources
