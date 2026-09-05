import os
import sys
import chromadb
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION_NAME = "spectr_metrics"
EMBEDDING_MODEL = "models/gemini-embedding-001"

if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as err:
        print(f"[RETRIEVER] Error configuring Gemini API client: {err}")

def get_query_embedding(query_text: str) -> list:
    try:
        response = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=query_text,
            task_type="retrieval_query",
            output_dimensionality=768
        )
        return response["embedding"]
    except Exception as e:
        print(f"[RETRIEVER] Error generating query embedding: {e}")
        raise e

def retrieve_chunks(question: str, top_k: int = 2) -> dict:
    """
    Retrieves the top_k most relevant chunks from Chroma DB for the given question.
    Returns a dictionary containing 'documents', 'sources', and 'distances'.
    """
    chroma_path = os.path.abspath(CHROMA_PERSIST_DIR)
    chroma_client = chromadb.PersistentClient(path=chroma_path)

    try:
        collection = chroma_client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        raise RuntimeError(f"Chroma collection '{COLLECTION_NAME}' not found. Run rag/ingest.py first. Details: {e}")

    if collection.count() == 0:
        raise RuntimeError(f"Chroma collection '{COLLECTION_NAME}' is empty. Run rag/ingest.py to insert docs.")

    query_emb = get_query_embedding(question)

    results = collection.query(
        query_embeddings=[query_emb],
        n_results=top_k
    )

    docs = results["documents"][0] if results.get("documents") else []
    metadatas = results["metadatas"][0] if results.get("metadatas") else []
    distances = results["distances"][0] if results.get("distances") else []

    sources = []
    for meta in metadatas:
        src = meta.get("source", "unknown")
        if not src.endswith(".md"):
            src = f"{src}.md"
        sources.append(src)

    return {
        "documents": docs,
        "sources": sources,
        "distances": distances
    }
