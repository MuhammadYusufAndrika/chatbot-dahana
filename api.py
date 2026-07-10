"""
api.py
------
FastAPI REST server for DahanaChatbot.

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

Interactive docs (auto-generated):
    http://localhost:8000/docs      ← Swagger UI
    http://localhost:8000/redoc     ← ReDoc UI
"""

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import chatbot_core as core
import os

API_KEY = os.getenv("API_KEY", "")

# ===============================
# App
# ===============================
app = FastAPI(
    title="DahanaChatbot API",
    version="1.0.0",
    description=(
        "REST API for DahanaChatbot SuperBrain. "
        "Answers questions by routing to the company database (SQL) "
        "or Google via SerpAPI when the data is not in the database."
    ),
    contact={
        "name": "PT Dahana – IT Team",
    },
)

# Allow all origins (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===============================
# Schemas
# ===============================
class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        examples=["siapakah Abdul Latip?"],
        description="The question to ask the chatbot (Bahasa Indonesia or English).",
    )


class ChatResponse(BaseModel):
    answer: str = Field(description="The chatbot's answer in natural language.")
    source: str = Field(
        description="Where the answer was retrieved from. Either 'DATABASE' or 'WEB'."
    )
    sql_query: Optional[str] = Field(
        default=None,
        description="The SQL query used (only present when source='DATABASE').",
    )
    urls: list[str] = Field(
        default=[],
        description="Reference URLs from the web (only present when source='WEB').",
    )


class HealthResponse(BaseModel):
    status: str
    version: str


def verify_api_key(x_api_key: str = Header(default="", alias="X-API-Key")):
    if not API_KEY:
        return
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


# ===============================
# Routes
# ===============================
@app.get(
    "/",
    response_model=HealthResponse,
    summary="Health Check",
    tags=["Utility"],
)
def root():
    """Returns API status and version. Use this to verify the server is running."""
    return {"status": "ok", "version": app.version}


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    tags=["Utility"],
)
def health():
    """Alias for the root health-check endpoint."""
    return {"status": "ok", "version": app.version}


@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask a Question",
    tags=["Chatbot"],
    responses={
        401: {"description": "Unauthorized – missing or invalid API key"},
        200: {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "examples": {
                        "database_answer": {
                            "summary": "Answer from database",
                            "value": {
                                "answer": "Jawaban Non-Analisis: Abdul Latip, ST adalah Senior Manajer...",
                                "source": "DATABASE",
                                "sql_query": "SELECT * FROM karyawan_homis WHERE nama_karyawan ILIKE '%Abdul Latip%' LIMIT 50",
                                "urls": [],
                            },
                        },
                        "web_answer": {
                            "summary": "Answer from web (SerpAPI)",
                            "value": {
                                "answer": "Jawaban Web: PT Dahana adalah Badan Usaha Milik Negara...",
                                "source": "WEB",
                                "sql_query": None,
                                "urls": ["https://www.dahana.com/..."],
                            },
                        },
                    }
                }
            },
        },
        422: {"description": "Validation error – question field missing or empty"},
        500: {"description": "Internal server error"},
    },
)
def chat(request: ChatRequest, _: None = Depends(verify_api_key)):
    """
    **Main chatbot endpoint.**

    ### Routing logic
    1. **Intent classification** – the LLM decides if the question can be answered
       from the company database or needs a web search.
    2. **DATABASE path** – generates a PostgreSQL query, runs it, and asks the LLM
       to analyse/summarise the result.
       - If the query returns empty, automatically falls back to WEB.
    3. **WEB path** – calls SerpAPI (Google), extracts AI Overview paragraphs
       (or organic result snippets as fallback), and asks the LLM to compose an answer.

    ### Response field `source`
    | Value | Meaning |
    |-------|---------|
    | `DATABASE` | Answer was built from the company PostgreSQL database |
    | `WEB` | Answer was built from Google search results via SerpAPI |
    """
    try:
        result = core.ask(request.question)
        return ChatResponse(**result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
