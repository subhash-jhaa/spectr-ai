import os
import sys
from pathlib import Path
import chromadb
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION_NAME = "spectr_metrics"
EMBEDDING_MODEL = "models/gemini-embedding-001"

if not GEMINI_API_KEY or GEMINI_API_KEY == "your_gemini_api_key_here":
    print("ERROR: GEMINI_API_KEY is missing or invalid in .env file.")
    print("Please set a valid GEMINI_API_KEY in spectr-ai/.env before running ingestion.")
    sys.exit(1)

try:
    genai.configure(api_key=GEMINI_API_KEY)
except Exception as err:
    print(f"ERROR configuring Gemini API client: {err}")
    sys.exit(1)

def get_embedding(text: str) -> list:
    try:
        response = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text,
            task_type="retrieval_document",
            output_dimensionality=768
        )
        return response["embedding"]
    except Exception as e:
        print(f"ERROR: Failed to generate embedding from Gemini API for model '{EMBEDDING_MODEL}'. Details: {e}")
        raise e

def main():
    current_dir = Path(__file__).parent.resolve()
    docs_dir = current_dir / "docs"

    if not docs_dir.exists():
        print(f"ERROR: Docs directory not found at {docs_dir}")
        sys.exit(1)

    md_files = sorted(list(docs_dir.glob("*.md")))
    print(f"Found {len(md_files)} markdown document(s) in '{docs_dir.name}/'")

    documents = []
    metadatas = []
    ids = []
    embeddings = []

    for file_path in md_files:
        source_name = file_path.stem
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                print(f"Skipping empty file: {file_path.name}")
                continue

            print(f"Generating embedding for '{source_name}' ({len(content.split())} words)...")
            embedding = get_embedding(content)

            documents.append(content)
            metadatas.append({"source": source_name})
            ids.append(f"doc_{source_name}")
            embeddings.append(embedding)

        except Exception as e:
            print(f"ERROR processing file '{file_path.name}': {e}")
            sys.exit(1)

    print(f"Successfully generated embeddings for {len(documents)} chunk(s).")

    chroma_path = os.path.abspath(CHROMA_PERSIST_DIR)
    print(f"Connecting to persistent Chroma DB at '{chroma_path}'...")
    chroma_client = chromadb.PersistentClient(path=chroma_path)

    try:
        chroma_client.delete_collection(name=COLLECTION_NAME)
        print(f"Cleared existing Chroma collection '{COLLECTION_NAME}'.")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    if documents:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    final_count = collection.count()
    print("=" * 60)
    print("INGESTION COMPLETE!")
    print(f"Chroma Collection : '{COLLECTION_NAME}'")
    print(f"Items Stored      : {final_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()
