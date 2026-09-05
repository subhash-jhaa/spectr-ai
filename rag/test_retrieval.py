import os
import sys

# Ensure root spectr-ai directory is in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from rag.retriever import retrieve_chunks

# Force UTF-8 encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def main():
    test_cases = [
        {
            "question": "what is a good LCP score",
            "expected_source": "lcp.md"
        },
        {
            "question": "how is bounce rate calculated",
            "expected_source": "bounce-rate.md"
        },
        {
            "question": "explain P75",
            "expected_source": "p75-aggregation.md"
        },
        {
            "question": "what does INP measure",
            "expected_source": "inp.md"
        },
        {
            "question": "difference between unique visitors and page views",
            "expected_source": "unique-visitors.md"
        }
    ]

    print("=" * 80)
    print("STARTING VECTOR RETRIEVAL EVALUATION (Shared Retriever Module)")
    print("=" * 80)

    matches_count = 0

    for idx, test in enumerate(test_cases, 1):
        question = test["question"]
        expected = test["expected_source"]

        print(f"\n--- Question #{idx}: \"{question}\" ---")
        print(f"Expected Primary Source: '{expected}'")

        try:
            res = retrieve_chunks(question, top_k=2)
            docs = res["documents"]
            sources = res["sources"]
            distances = res["distances"]

            top_source = sources[0] if sources else "unknown"

            if top_source.lower() == expected.lower():
                print(f"Status: [PASS] MATCH (Top chunk source: '{top_source}')")
                matches_count += 1
            else:
                print(f"Status: [WARNING] possible retrieval mismatch (Top chunk source: '{top_source}', Expected: '{expected}')")

            print("\nRetrieved Top Chunks:")
            for rank in range(len(docs)):
                src = sources[rank]
                dist = distances[rank]
                preview = docs[rank].split("\n")[0][:80]
                print(f"  Rank #{rank + 1} | Source: {src} | Distance: {dist:.4f}")
                print(f"    Snippet: \"{preview}...\"")

        except Exception as e:
            print(f"Status: [FAIL] Exception during retrieval: {e}")

    print("\n" + "=" * 80)
    print(f"RETRIEVAL EVALUATION SUMMARY: {matches_count}/{len(test_cases)} questions matched expected primary source.")
    print("=" * 80)

if __name__ == "__main__":
    main()
