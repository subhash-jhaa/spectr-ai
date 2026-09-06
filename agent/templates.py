import os
import sys
from datetime import date, datetime, time, timedelta
from typing import Tuple, List, Dict, Any, Optional
from sqlalchemy import text

# Ensure root spectr-ai directory is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from agent.db import get_engine

ALLOWED_METRICS = {
    "lcp": "webvital",
    "inp": "webvital",
    "cls": "webvital",
    "bounce_rate": "event",
    "unique_visitors": "event",
    "page_views": "event"
}

ALLOWED_GRANULARITIES = {"day", "week"}

def _validate_inputs(metric: str, granularity: Optional[str] = None):
    if metric not in ALLOWED_METRICS:
        raise ValueError(f"Invalid metric '{metric}'. Must be one of: {sorted(list(ALLOWED_METRICS.keys()))}")
    if granularity is not None and granularity not in ALLOWED_GRANULARITIES:
        raise ValueError(f"Invalid granularity '{granularity}'. Must be one of: {sorted(list(ALLOWED_GRANULARITIES))}")

def _get_time_boundaries(date_range: Tuple[date, date]) -> Tuple[datetime, datetime]:
    start_d, end_d = date_range
    start_dt = datetime.combine(start_d, time.min)
    end_dt = datetime.combine(end_d, time.max)
    return start_dt, end_dt

def _fetch_single_metric_value(site_id: str, metric: str, date_range: Tuple[date, date]) -> float:
    _validate_inputs(metric)
    start_dt, end_dt = _get_time_boundaries(date_range)
    engine = get_engine()

    params = {"site_id": site_id, "start_time": start_dt, "end_time": end_dt}

    if metric in ("lcp", "inp", "cls"):
        if metric == "lcp":
            sql = text("""
                SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY "lcp") AS val
                FROM public."WebVital"
                WHERE "projectId" = :site_id AND "createdAt" >= :start_time AND "createdAt" <= :end_time
            """)
        elif metric == "inp":
            sql = text("""
                SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY "inp") AS val
                FROM public."WebVital"
                WHERE "projectId" = :site_id AND "createdAt" >= :start_time AND "createdAt" <= :end_time
            """)
        else:
            sql = text("""
                SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY "cls") AS val
                FROM public."WebVital"
                WHERE "projectId" = :site_id AND "createdAt" >= :start_time AND "createdAt" <= :end_time
            """)
    elif metric == "page_views":
        sql = text("""
            SELECT COUNT(*)::float AS val
            FROM public."Event"
            WHERE "projectId" = :site_id AND "timestamp" >= :start_time AND "timestamp" <= :end_time
        """)
    elif metric == "unique_visitors":
        sql = text("""
            SELECT COUNT(DISTINCT COALESCE("sessionId", "ip"))::float AS val
            FROM public."Event"
            WHERE "projectId" = :site_id AND "timestamp" >= :start_time AND "timestamp" <= :end_time
        """)
    elif metric == "bounce_rate":
        sql = text("""
            WITH session_counts AS (
                SELECT COALESCE("sessionId", "ip") AS session_id, COUNT(*) AS event_count
                FROM public."Event"
                WHERE "projectId" = :site_id AND "timestamp" >= :start_time AND "timestamp" <= :end_time
                GROUP BY COALESCE("sessionId", "ip")
            )
            SELECT 
                CASE 
                    WHEN COUNT(*) = 0 THEN NULL
                    ELSE (COUNT(*) FILTER (WHERE event_count = 1)::float / COUNT(*)::float) * 100.0
                END AS val
            FROM session_counts
        """)

    with engine.connect() as conn:
        res = conn.execute(sql, params).fetchone()
        if not res or res[0] is None:
            if metric == "bounce_rate" or metric in ("lcp", "inp", "cls"):
                return None
            return 0.0
        return float(res[0])

def get_metric_summary(site_id: str, metric: str, date_range: Tuple[date, date]) -> Dict[str, Any]:
    """
    Returns the P75 or aggregate value for the current date range and the preceding equal period,
    along with percentage delta change.
    """
    _validate_inputs(metric)
    start_d, end_d = date_range
    duration = end_d - start_d + timedelta(days=1)
    
    prev_end_d = start_d - timedelta(days=1)
    prev_start_d = prev_end_d - duration + timedelta(days=1)

    current_val = _fetch_single_metric_value(site_id, metric, date_range)
    previous_val = _fetch_single_metric_value(site_id, metric, (prev_start_d, prev_end_d))

    if previous_val is not None and previous_val > 0 and current_val is not None:
        pct_change = round(((current_val - previous_val) / previous_val) * 100.0, 2)
    elif current_val == 0:
        pct_change = 0.0
    else:
        pct_change = None  # Baseline is 0 or None, percentage change is undefined

    return {
        "metric": metric,
        "site_id": site_id,
        "current_value": round(current_val, 2) if current_val is not None else None,
        "previous_value": round(previous_val, 2) if previous_val is not None else None,
        "pct_change": pct_change,
        "current_period": (str(start_d), str(end_d)),
        "previous_period": (str(prev_start_d), str(prev_end_d))
    }

def get_metric_trend(site_id: str, metric: str, date_range: Tuple[date, date], granularity: str = "day") -> List[Dict[str, Any]]:
    """
    Returns a list of {date, value} points across the date range at the requested granularity ('day' or 'week').
    """
    _validate_inputs(metric, granularity)
    start_dt, end_dt = _get_time_boundaries(date_range)
    engine = get_engine()

    params = {"site_id": site_id, "start_time": start_dt, "end_time": end_dt}

    if metric in ("lcp", "inp", "cls"):
        col = metric
        if granularity == "day":
            sql = text(f"""
                SELECT date_trunc('day', "createdAt")::date AS period,
                       percentile_cont(0.75) WITHIN GROUP (ORDER BY "{col}") AS val
                FROM public."WebVital"
                WHERE "projectId" = :site_id AND "createdAt" >= :start_time AND "createdAt" <= :end_time
                GROUP BY period ORDER BY period ASC
            """)
        else:
            sql = text(f"""
                SELECT date_trunc('week', "createdAt")::date AS period,
                       percentile_cont(0.75) WITHIN GROUP (ORDER BY "{col}") AS val
                FROM public."WebVital"
                WHERE "projectId" = :site_id AND "createdAt" >= :start_time AND "createdAt" <= :end_time
                GROUP BY period ORDER BY period ASC
            """)
    elif metric == "page_views":
        trunc = "day" if granularity == "day" else "week"
        sql = text(f"""
            SELECT date_trunc('{trunc}', "timestamp")::date AS period,
                   COUNT(*)::float AS val
            FROM public."Event"
            WHERE "projectId" = :site_id AND "timestamp" >= :start_time AND "timestamp" <= :end_time
            GROUP BY period ORDER BY period ASC
        """)
    elif metric == "unique_visitors":
        trunc = "day" if granularity == "day" else "week"
        sql = text(f"""
            SELECT date_trunc('{trunc}', "timestamp")::date AS period,
                   COUNT(DISTINCT COALESCE("sessionId", "ip"))::float AS val
            FROM public."Event"
            WHERE "projectId" = :site_id AND "timestamp" >= :start_time AND "timestamp" <= :end_time
            GROUP BY period ORDER BY period ASC
        """)
    elif metric == "bounce_rate":
        trunc = "day" if granularity == "day" else "week"
        sql = text(f"""
            WITH session_counts AS (
                SELECT date_trunc('{trunc}', "timestamp")::date AS period,
                       COALESCE("sessionId", "ip") AS session_id,
                       COUNT(*) AS event_count
                FROM public."Event"
                WHERE "projectId" = :site_id AND "timestamp" >= :start_time AND "timestamp" <= :end_time
                GROUP BY period, COALESCE("sessionId", "ip")
            )
            SELECT period,
                   CASE 
                       WHEN COUNT(*) = 0 THEN 0.0
                       ELSE (COUNT(*) FILTER (WHERE event_count = 1)::float / COUNT(*)::float) * 100.0
                   END AS val
            FROM session_counts
            GROUP BY period ORDER BY period ASC
        """)

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [{"date": str(row[0]), "value": round(float(row[1] or 0.0), 2)} for row in rows]

def compare_periods(site_id: str, metric: str, period_a: Tuple[date, date], period_b: Tuple[date, date]) -> Dict[str, Any]:
    """
    Compares metric values between two custom periods (period_a vs period_b) and returns pct_change.
    """
    _validate_inputs(metric)
    val_a = _fetch_single_metric_value(site_id, metric, period_a)
    val_b = _fetch_single_metric_value(site_id, metric, period_b)

    if val_a is not None and val_a > 0 and val_b is not None:
        pct_change = round(((val_b - val_a) / val_a) * 100.0, 2)
    elif val_b == 0:
        pct_change = 0.0
    else:
        pct_change = None  # Baseline is 0 or None, percentage change is undefined

    return {
        "metric": metric,
        "site_id": site_id,
        "period_a": {
            "range": (str(period_a[0]), str(period_a[1])),
            "value": round(val_a, 2) if val_a is not None else None
        },
        "period_b": {
            "range": (str(period_b[0]), str(period_b[1])),
            "value": round(val_b, 2) if val_b is not None else None
        },
        "pct_change": pct_change
    }

if __name__ == "__main__":
    import json

    print("=" * 80)
    print("TESTING SPECTR AI TEXT-TO-SQL QUERY TEMPLATES")
    print("=" * 80)

    engine = get_engine()
    sample_site_id = None

    try:
        with engine.connect() as conn:
            res = conn.execute(text('SELECT p."id", p."name" FROM public."Project" p LEFT JOIN public."Event" e ON e."projectId" = p."id" GROUP BY p."id", p."name" ORDER BY COUNT(e."id") DESC LIMIT 1')).fetchone()
            if res:
                sample_site_id = res[0]
                print(f"Using database site_id: '{sample_site_id}' (Project Name: '{res[1]}')")
    except Exception as e:
        print(f"Error querying database for site_id: {e}")

    if not sample_site_id:
        sample_site_id = "sample-site-id-placeholder"
        print(f"No active project found in DB. Using fallback site_id: '{sample_site_id}'")

    today = date.today()
    start_30d = today - timedelta(days=30)
    start_7d = today - timedelta(days=7)
    prev_7d_start = start_7d - timedelta(days=7)
    prev_7d_end = start_7d - timedelta(days=1)

    print("\n--- 1. get_metric_summary ('lcp', last 30 days) ---")
    try:
        summary = get_metric_summary(sample_site_id, "lcp", (start_30d, today))
        print(json.dumps(summary, indent=2))
    except Exception as e:
        print("Error:", e)

    print("\n--- 2. get_metric_summary ('page_views', last 30 days) ---")
    try:
        summary = get_metric_summary(sample_site_id, "page_views", (start_30d, today))
        print(json.dumps(summary, indent=2))
    except Exception as e:
        print("Error:", e)

    print("\n--- 3. get_metric_trend ('unique_visitors', last 7 days, daily) ---")
    try:
        trend = get_metric_trend(sample_site_id, "unique_visitors", (start_7d, today), granularity="day")
        print(json.dumps(trend, indent=2))
    except Exception as e:
        print("Error:", e)

    print("\n--- 4. compare_periods ('bounce_rate', last 7d vs preceding 7d) ---")
    try:
        comp = compare_periods(sample_site_id, "bounce_rate", (prev_7d_start, prev_7d_end), (start_7d, today))
        print(json.dumps(comp, indent=2))
    except Exception as e:
        print("Error:", e)
