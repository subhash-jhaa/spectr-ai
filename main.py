import os
import sys
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import google.generativeai as genai
from rag.retriever import retrieve_chunks

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GENERATION_MODEL = "models/gemini-3.6-flash"

if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as err:
        print(f"[MAIN] Warning configuring Gemini API: {err}")

app = FastAPI(
    title="Spectr AI Service",
    description="Backend microservice for Spectr RAG assistant",
    version="0.1.0"
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

@app.post("/ask", status_code=status.HTTP_200_OK)
def ask_question(request: AskRequest):
    question = request.question.strip() if request.question else ""
    
    if not question:
        print("[ASK] Rejected empty question request.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question parameter cannot be empty."
        )

    print(f"[ASK] Incoming Question: '{question}'")

    # 1. Retrieve top 2 relevant chunks
    try:
        retrieved = retrieve_chunks(question, top_k=2)
        docs = retrieved["documents"]
        sources = retrieved["sources"]
        print(f"[ASK] Retrieved Sources: {sources}")
    except Exception as err:
        print(f"[ASK] Retrieval Error: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vector retrieval failed: {str(err)}"
        )

    # 2. Build synthesis prompt
    context_blocks = []
    for doc, src in zip(docs, sources):
        context_blocks.append(f"--- Document Source: {src} ---\n{doc}")
    
    context_text = "\n\n".join(context_blocks)

    prompt = f"""You are Ask Spectr, an expert AI assistant for the Spectr web analytics platform.
Answer the user's question accurately and ONLY using the provided documentation context below.

STRICT INSTRUCTIONS:
1. Base your answer ONLY on the provided context below.
2. If the provided context does NOT contain enough information to answer the question, respond EXACTLY with: "I don't have information on that."
3. Do NOT use outside knowledge, assumptions, or hallucinations.
4. At the end of your answer, explicitly cite which source file(s) were used.

Context Documents:
{context_text}

User Question: {question}
Answer:"""

    # 3. Generate content using Gemini LLM
    try:
        model = genai.GenerativeModel(GENERATION_MODEL)
        gen_response = model.generate_content(prompt)
        answer = gen_response.text.strip()
        print(f"[ASK] Generation Succeeded for: '{question}'")
    except Exception as err:
        print(f"[ASK] Generation Error: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM generation failed: {str(err)}"
        )

    # 4. Check for "no information" fallback response (case-insensitive & partial phrase matching)
    fallback_phrases = [
        "don't have information",
        "do not have information",
        "no information",
        "not mentioned in the context",
        "does not contain information",
        "no details provided"
    ]

    answer_lower = answer.lower()
    is_fallback = any(phrase in answer_lower for phrase in fallback_phrases)

    final_sources = [] if is_fallback else sources

    if is_fallback:
        print(f"[ASK] Fallback response detected. Returning empty sources list.")

    return {
        "answer": answer,
        "sources": final_sources,
        "question": question
    }
