import os
import sys
import json
import time
import requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k not in os.environ:
                        os.environ[k] = v

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_URL = os.getenv("SPECTR_AI_URL", "http://127.0.0.1:8000")
if BASE_URL.endswith("/ask"):
    BASE_URL = BASE_URL[:-4]

SHARED_SECRET = os.getenv("INTERNAL_SHARED_SECRET", "uMu3O1z9bNUIagYLjZO5W5nRCg95A_S9TVlrUztBDN0")
SITE_ID = os.getenv("TEST_SITE_ID", "0d565d46-0721-489e-a89e-f96cb4e891ab")

test_cases = [
    {
        "id": 1,
        "name": "Pure definition question (RAG-only path)",
        "headers": {
            "Content-Type": "application/json",
            "X-Site-ID": SITE_ID,
            "X-Internal-Secret": SHARED_SECRET,
        },
        "payload": {"question": "what is a good LCP score"},
        "expected_status": 200,
    },
    {
        "id": 2,
        "name": "Data question (get_metric_summary path)",
        "headers": {
            "Content-Type": "application/json",
            "X-Site-ID": SITE_ID,
            "X-Internal-Secret": SHARED_SECRET,
        },
        "payload": {"question": "how many page views did I get in the last 30 days"},
        "expected_status": 200,
    },
    {
        "id": 3,
        "name": "Data question (get_metric_trend path)",
        "headers": {
            "Content-Type": "application/json",
            "X-Site-ID": SITE_ID,
            "X-Internal-Secret": SHARED_SECRET,
        },
        "payload": {"question": "show me unique visitor trend for the last 7 days"},
        "expected_status": 200,
    },
    {
        "id": 4,
        "name": "compare_periods (mention-order check)",
        "headers": {
            "Content-Type": "application/json",
            "X-Site-ID": SITE_ID,
            "X-Internal-Secret": SHARED_SECRET,
        },
        "payload": {"question": "compare LCP this month vs last month"},
        "expected_status": 200,
    },
    {
        "id": 5,
        "name": "Nonsense / unrelated question (Fast fallback path)",
        "headers": {
            "Content-Type": "application/json",
            "X-Site-ID": SITE_ID,
            "X-Internal-Secret": SHARED_SECRET,
        },
        "payload": {"question": "what is the capital of France"},
        "expected_status": 200,
    },
    {
        "id": 6,
        "name": "Wrong secret (403 Forbidden security check)",
        "headers": {
            "Content-Type": "application/json",
            "X-Site-ID": SITE_ID,
            "X-Internal-Secret": "wrong-secret-on-purpose",
        },
        "payload": {"question": "what is a good LCP score"},
        "expected_status": 403,
    },
    {
        "id": 7,
        "name": "Missing X-Site-ID (401 Unauthorized check)",
        "headers": {
            "Content-Type": "application/json",
            "X-Internal-Secret": SHARED_SECRET,
        },
        "payload": {"question": "what is a good LCP score"},
        "expected_status": 401,
    },
]

def run_tests():
    print("=" * 80)
    print(f"SPECTR-AI ENDPOINT TEST SUITE ({BASE_URL}/ask)")
    print(f"Target Site ID: {SITE_ID}")
    print("=" * 80)

    try:
        health_res = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Health Check (/health): {health_res.status_code} -> {health_res.json()}\n")
    except Exception as e:
        print(f"Failed to connect to {BASE_URL}/health. Is uvicorn running? Error: {e}\n")
        return

    passed = 0
    total = len(test_cases)

    for case in test_cases:
        cid = case["id"]
        cname = case["name"]
        headers = case["headers"]
        payload = case["payload"]
        exp = case["expected_status"]

        print(f"[{cid}/{total}] Testing: {cname}", flush=True)
        print(f"  Question : {payload.get('question')}", flush=True)
        start = time.time()
        try:
            res = requests.post(f"{BASE_URL}/ask", headers=headers, json=payload, timeout=120)
            elapsed = round(time.time() - start, 2)
            is_ok = (res.status_code == exp)
            status_tag = "PASS" if is_ok else f"FAIL (expected {exp})"

            if is_ok:
                passed += 1

            print(f"  Result   : [{status_tag}] HTTP {res.status_code} in {elapsed}s", flush=True)

            try:
                data = res.json()
                if "answer" in data:
                    ans_preview = data["answer"].replace("\n", " ")[:120]
                    print(f"  Answer   : {ans_preview}...", flush=True)
                    print(f"  Sources  : {data.get('sources', [])}", flush=True)
                elif "detail" in data:
                    print(f"  Detail   : {data.get('detail')}", flush=True)
                else:
                    print(f"  Body     : {data}", flush=True)
            except Exception:
                print(f"  Body     : {res.text[:120]}", flush=True)

        except Exception as err:
            print(f"  Result   : [ERROR] {err}", flush=True)

        print("-" * 80, flush=True)

    print(f"\nTest Summary: {passed}/{total} tests passed.", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    run_tests()
