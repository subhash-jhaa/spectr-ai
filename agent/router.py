import os
import sys
import json
import re
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List
import dateparser
from rapidfuzz import fuzz

ALLOWED_METRICS = {"lcp", "inp", "cls", "bounce_rate", "unique_visitors", "page_views"}
ALLOWED_GRANULARITIES = {"day", "week"}
ALLOWED_TEMPLATES = {"get_metric_summary", "get_metric_trend", "compare_periods"}

METRIC_KEYWORDS = {
    "lcp": ["largest contentful paint", "lcp"],
    "inp": ["interaction to next paint", "inp"],
    "cls": ["cumulative layout shift", "cls"],
    "bounce_rate": ["bounce rate", "bounce"],
    "unique_visitors": ["unique visitors", "unique visitor", "visitors"],
    "page_views": ["page views", "pageviews", "page view", "views"],
}

TIME_PATTERNS = [
    r"(?:the\s+)?(?:last|past)\s+\d+\s+(?:days?|weeks?|months?)",
    r"this\s+week",
    r"last\s+week",
    r"past\s+week",
    r"this\s+month",
    r"last\s+month",
    r"past\s+month",
    r"yesterday",
    r"today",
]

TIME_KEYWORDS = [
    "yesterday",
    "today",
    "this week",
    "last week",
    "past week",
    "this month",
    "last month",
    "past month",
]

FUZZY_THRESHOLD = 85.0

def _validate_date_str(d_str: str, today: date, clamp_future: bool = True) -> date:
    if not isinstance(d_str, str):
        raise ValueError(f"Date must be a string, got {type(d_str)}")
    try:
        parsed = datetime.strptime(d_str.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date format '{d_str}'. Must be YYYY-MM-DD")
    
    if parsed > today:
        if clamp_future:
            return today
        raise ValueError(f"Date '{d_str}' cannot be in the future relative to today ({today})")
    
    return parsed

def _validate_date_range(range_list: Any, today: date) -> list:
    if not isinstance(range_list, (list, tuple)) or len(range_list) != 2:
        raise ValueError(f"Date range must be a list of 2 date strings [start_date, end_date], got {range_list}")
    
    start_d = _validate_date_str(range_list[0], today, clamp_future=True)
    end_d = _validate_date_str(range_list[1], today, clamp_future=True)

    if start_d > end_d:
        start_d = end_d

    if (end_d - start_d).days > 365:
        raise ValueError(f"Date range from '{start_d}' to '{end_d}' spans more than 365 days")
    
    return [str(start_d), str(end_d)]

def resolve_time_phrase(phrase: str, today: date) -> Optional[List[str]]:
    if not phrase:
        return None
    p = phrase.lower().strip()
    p = re.sub(r"^(for\s+|in\s+|over\s+|during\s+|the\s+)", "", p).strip()

    if p == "yesterday":
        y = today - timedelta(days=1)
        return [str(y), str(y)]
    if p == "today":
        return [str(today), str(today)]
    if p == "this week":
        start = today - timedelta(days=today.weekday())
        return [str(start), str(today)]
    if p in ("last week", "past week"):
        start = today - timedelta(days=today.weekday() + 7)
        end = today - timedelta(days=today.weekday() + 1)
        return [str(start), str(end)]
    if p == "this month":
        start = today.replace(day=1)
        return [str(start), str(today)]
    if p in ("last month", "past month"):
        first_of_this_month = today.replace(day=1)
        last_day_prev = first_of_this_month - timedelta(days=1)
        first_day_prev = last_day_prev.replace(day=1)
        return [str(first_day_prev), str(last_day_prev)]

    m_days = re.search(r"(?:last|past)\s+(\d+)\s+days?", p)
    if m_days:
        n = int(m_days.group(1))
        start = today - timedelta(days=n)
        return [str(start), str(today)]

    m_weeks = re.search(r"(?:last|past)\s+(\d+)\s+weeks?", p)
    if m_weeks:
        n = int(m_weeks.group(1))
        start = today - timedelta(days=7 * n)
        return [str(start), str(today)]

    m_months = re.search(r"(?:last|past)\s+(\d+)\s+months?", p)
    if m_months:
        n = int(m_months.group(1))
        start = today - timedelta(days=30 * n)
        return [str(start), str(today)]

    parsed = dateparser.parse(p, settings={"RELATIVE_BASE": datetime.combine(today, datetime.min.time())})
    if parsed:
        d = parsed.date()
        if d > today:
            d = today
        return [str(d), str(d)]

    return None

def extract_metric(text: str, threshold: float = FUZZY_THRESHOLD) -> Optional[str]:
    text_lower = text.lower()
    # 1. Exact match fast first check
    for metric, phrases in METRIC_KEYWORDS.items():
        for phrase in phrases:
            if re.search(r"\b" + re.escape(phrase) + r"\b", text_lower):
                return metric

    # 2. Fuzzy match fallback
    words = re.findall(r"[a-zA-Z0-9]+", text_lower)
    if not words:
        return None

    best_score = 0.0
    best_metric = None

    for metric, phrases in METRIC_KEYWORDS.items():
        for phrase in phrases:
            phrase_words = phrase.lower().split()
            k = len(phrase_words)
            if k == 0:
                continue
            for w_len in range(max(1, k - 1), min(len(words) + 1, k + 2)):
                for i in range(len(words) - w_len + 1):
                    win = " ".join(words[i : i + w_len])
                    if len(phrase) <= 3:
                        score = 100.0 if win == phrase else 0.0
                    else:
                        score = fuzz.ratio(win, phrase.lower())

                    if score > best_score:
                        best_score = score
                        best_metric = metric

    if best_score >= threshold:
        return best_metric

    return None

def extract_time_phrases(text: str, threshold: float = FUZZY_THRESHOLD) -> List[str]:
    text_lower = text.lower()
    matches = []
    occupied_spans = []

    # 1. Exact match fast check
    for pat in TIME_PATTERNS:
        for m in re.finditer(r"\b" + pat + r"\b", text_lower):
            matches.append((m.start(), m.end(), m.group(0)))
            occupied_spans.append((m.start(), m.end()))

    def overlaps(start, end):
        return any(max(start, o_start) < min(end, o_end) for o_start, o_end in occupied_spans)

    # 2. Fuzzy match fallback for keywords
    words_with_spans = []
    for m in re.finditer(r"[a-zA-Z0-9]+", text_lower):
        words_with_spans.append((m.start(), m.end(), m.group(0)))

    fuzzy_candidates = []
    for kw in TIME_KEYWORDS:
        kw_tokens = kw.split()
        k = len(kw_tokens)
        for w_len in range(max(1, k - 1), min(len(words_with_spans) + 1, k + 2)):
            for i in range(len(words_with_spans) - w_len + 1):
                chunk_spans = words_with_spans[i : i + w_len]
                c_start = chunk_spans[0][0]
                c_end = chunk_spans[-1][1]
                if overlaps(c_start, c_end):
                    continue
                raw_chunk = text_lower[c_start:c_end]
                if len(kw) <= 3:
                    score = 100.0 if raw_chunk == kw else 0.0
                else:
                    score = fuzz.ratio(raw_chunk, kw)

                if score >= threshold:
                    fuzzy_candidates.append((score, c_start, c_end, kw))

    fuzzy_candidates.sort(key=lambda x: x[0], reverse=True)
    for score, start, end, kw in fuzzy_candidates:
        if not overlaps(start, end):
            matches.append((start, end, kw))
            occupied_spans.append((start, end))

    matches.sort(key=lambda x: x[0])
    return [m[2] for m in matches]

def is_definition_query(text: str) -> bool:
    t = text.lower().strip()
    return bool(re.search(r"\b(what\s+is|what\s+are|how\s+is|define|definition|explain|meaning\s+of)\b", t))

def route_question(question: str, today: date) -> Dict[str, Any]:
    if not question or not question.strip():
        return {"template": None, "params": {}}

    q = question.strip()
    q_lower = q.lower()

    metric = extract_metric(q)
    time_phrases = extract_time_phrases(q)

    # 1. Check compare_periods: contains 'compare', ' vs ', ' versus ', or 'between' AND has 2 distinct time phrases
    is_comparison = bool(
        re.search(r"\b(compare|versus)\b", q_lower)
        or " vs " in q_lower
        or " vs. " in q_lower
        or "between" in q_lower
    )
    if not is_comparison:
        # Fuzzy fallback for comparison keywords
        words = re.findall(r"[a-zA-Z]+", q_lower)
        for w in words:
            if len(w) >= 5:
                for kw in ["compare", "versus", "between"]:
                    if fuzz.ratio(w, kw) >= FUZZY_THRESHOLD:
                        is_comparison = True
                        break
            if is_comparison:
                break

    if is_comparison and len(time_phrases) >= 2:
        if not metric:
            return {"template": None, "error": "ambiguous"}

        phrase_a = time_phrases[0]
        phrase_b = time_phrases[1]

        range_a = resolve_time_phrase(phrase_a, today)
        range_b = resolve_time_phrase(phrase_b, today)

        if not range_a or not range_b:
            return {"template": None, "error": "ambiguous"}

        val_a = _validate_date_range(range_a, today)
        val_b = _validate_date_range(range_b, today)

        end_a = datetime.strptime(val_a[1], "%Y-%m-%d").date()
        end_b = datetime.strptime(val_b[1], "%Y-%m-%d").date()

        return {
            "template": "compare_periods",
            "params": {
                "metric": metric,
                "period_a": val_a,
                "period_b": val_b,
                "period_a_is_complete": (end_a < today),
                "period_b_is_complete": (end_b < today),
            },
        }

    # 2. Check get_metric_trend: contains 'trend', 'over time', 'daily', or 'weekly'
    is_trend = bool(re.search(r"\b(trend|trends|over\s+time|daily|weekly)\b", q_lower))
    if not is_trend:
        # Fuzzy fallback for trend keywords
        words = re.findall(r"[a-zA-Z]+", q_lower)
        for i, w in enumerate(words):
            if len(w) >= 4:
                for kw in ["trend", "trends", "daily", "weekly"]:
                    if fuzz.ratio(w, kw) >= FUZZY_THRESHOLD:
                        is_trend = True
                        break
            if is_trend:
                break
            if i + 1 < len(words):
                win = f"{w} {words[i+1]}"
                if fuzz.ratio(win, "over time") >= FUZZY_THRESHOLD:
                    is_trend = True
                    break

    if is_trend:
        if not metric:
            return {"template": None, "error": "ambiguous"}

        is_weekly_granularity = bool(re.search(r"\b(weekly|by\s+week)\b", q_lower))
        granularity = "week" if is_weekly_granularity else "day"

        if time_phrases:
            date_range = resolve_time_phrase(time_phrases[0], today)
        else:
            date_range = [str(today - timedelta(days=30)), str(today)]

        if not date_range:
            return {"template": None, "error": "ambiguous"}

        validated_range = _validate_date_range(date_range, today)
        return {
            "template": "get_metric_trend",
            "params": {
                "metric": metric,
                "date_range": validated_range,
                "granularity": granularity,
            },
        }

    # 3. Check get_metric_summary: metric keyword AND resolvable time phrase are both found
    if metric and time_phrases:
        date_range = resolve_time_phrase(time_phrases[0], today)
        if not date_range:
            return {"template": None, "error": "ambiguous"}

        validated_range = _validate_date_range(date_range, today)
        return {
            "template": "get_metric_summary",
            "params": {
                "metric": metric,
                "date_range": validated_range,
            },
        }

    # 4. If a metric keyword is found but no resolvable date phrase exists
    if metric and not time_phrases:
        if is_definition_query(q):
            return {"template": None, "params": {}}
        return {"template": None, "error": "ambiguous"}

    # If time phrase found but no metric
    if time_phrases and not metric:
        return {"template": None, "error": "ambiguous"}

    # 5. Otherwise fall through cleanly to RAG
    return {"template": None, "params": {}}

if __name__ == "__main__":
    test_today = date(2026, 9, 5)

    test_questions = [
        "what's my bounce rate this week",
        "compare LCP this month vs last month",
        "show me unique visitor trend for the last 30 days, daily",
        "what is a good LCP score",
        "how many page views did I get yesterday",
        "compare LCP this month vs last month",
        "compare bounce rate last week vs this week",
        "compare unique visitors between last month and this month",
        "asdkfjaskdjf random gibberish",
        "what's my conversion rate",
        # New typo and reordering test cases requested
        "yesderday bounce rate",
        "bounce rate yesterday",
        "boundce rate last week",
        "thsi week visitors",
        "banana rate yesterday",
    ]

    print("=" * 80)
    print(f"TESTING DETERMINISTIC INTENT ROUTER WITH FUZZY MATCHING (Reference Today: {test_today})")
    print("=" * 80, flush=True)

    for i, q in enumerate(test_questions):
        print(f"\nQuestion #{i+1}: \"{q}\"", flush=True)
        result = route_question(q, test_today)
        print(json.dumps(result, indent=2), flush=True)
