"""
chatbot_core.py
---------------
Core chatbot logic shared between the Streamlit UI (app.py) and the REST API (api.py).

Flow:
  1. Intent classification  → RAG | DATABASE | GENERAL
  2. RAG      → answer using Dahana chatbot persona
  3. DATABASE → generate SQL → run → if data found: analyse
                                   → if empty:      answer from AI knowledge
  4. GENERAL  → SerpAPI web search fallback
"""

import os
import re

import pandas as pd
import serpapi
from dotenv import load_dotenv
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from sqlalchemy import create_engine, text

# ===============================
# Load environment
# ===============================
load_dotenv(override=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SERP_API_KEY = os.getenv("SERP_API_KEY", "")
DATABASE_URL = os.getenv("database_url", "")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY tidak ditemukan di .env")
if not SERP_API_KEY:
    raise RuntimeError("SERP_API_KEY tidak ditemukan di .env")
if not DATABASE_URL:
    raise RuntimeError("database_url tidak ditemukan di .env")

_db_url_pg = (
    DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    if DATABASE_URL.startswith("postgresql://")
    else DATABASE_URL
)

# ===============================
# Init LLM & DB
# ===============================
llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model="llama-3.1-8b-instant",
    temperature=0,
)

db = SQLDatabase.from_uri(_db_url_pg)
table_info = db.get_table_info()
engine = create_engine(DATABASE_URL)


# ===============================
# Prompts
# ===============================

# --- 1. Intent classification ---
intent_prompt = ChatPromptTemplate.from_template("""
Kamu adalah classifier yang sangat akurat. Tugasmu adalah mengklasifikasikan pertanyaan user ke dalam salah satu kategori berikut:

- RAG      : Pertanyaan non-teknis seperti salam, identitas AI, pertanyaan tentang chatbot ini, atau pertanyaan tentang PT Dahana secara umum (sejarah, profil, bisnis, dll). Contoh: "halo", "siapa kamu", "apa itu PT Dahana", "kamu bisa apa".
- DATABASE : Pertanyaan yang membutuhkan data dari database internal (data karyawan, absensi, produksi, gaji, dll). Contoh: "berapa karyawan yang hadir minggu ini", "siapa yang tidak masuk hari ini", "total produksi bulan lalu".
- GENERAL  : Pertanyaan umum yang tidak berkaitan dengan database internal maupun identitas chatbot PT Dahana. Contoh: "apa itu machine learning", "siapa presiden Indonesia", "harga saham hari ini".

Pertanyaan user:
{question}

Jawab HANYA dengan satu kata: RAG, DATABASE, atau GENERAL
""")

# --- 2. RAG / Persona (non-teknis, tentang Dahana & chatbot) ---
rag_prompt = ChatPromptTemplate.from_template("""
Kamu adalah **DahanaBot SuperBrain**, asisten AI cerdas milik **PT DAHANA (Persero)**.

Profil singkat PT DAHANA:
- PT DAHANA (Persero) adalah perusahaan BUMN Indonesia yang bergerak di bidang bahan peledak (handak) dan solusi pertahanan.
- Berdiri sejak 1966, berlokasi di Subang, Jawa Barat.
- Melayani sektor pertambangan, migas, konstruksi, dan pertahanan nasional.

Kemampuanmu:
- Menjawab pertanyaan seputar PT Dahana dan operasional perusahaan.
- Menganalisis data karyawan, absensi, dan produksi dari database internal.
- Memberikan insight berbasis data untuk mendukung pengambilan keputusan.

Jawab pertanyaan berikut dengan ramah, profesional, dan informatif dalam bahasa Indonesia:

Pertanyaan: {question}

Jawaban:
""")

# --- 3. SQL generation ---
sql_prompt = ChatPromptTemplate.from_template("""
Kamu adalah seorang **Data Analyst senior** sekaligus **Database Administrator berpengalaman**.
Kamu sangat memahami struktur, relasi, serta isi database.

Tugasmu:
- Hasilkan query PostgreSQL yang valid, efisien, dan optimal untuk menjawab pertanyaan user.
- Jangan gunakan format kode atau pembungkus Markdown. Berikan hanya query SQL dalam bentuk teks biasa.
- Gunakan best practice SQL. BATASI dengan LIMIT 50.
- Gunakan LIKE/ILIKE jika user meminta data spesifik yang mungkin typo.
- Jangan berikan jawaban naratif, hanya query PostgreSQL murni.

Informasi database:
{table_info}

Pertanyaan user:
{question}

SQLQuery:
""")

# --- 4. Analysis (DB returned data) ---
analysis_prompt = ChatPromptTemplate.from_template("""
Kamu adalah **Data Analyst Profesional** yang sangat berpengalaman dalam analisis data.

Berikut adalah informasi yang ada:
- Pertanyaan: {question}
- SQL Query yang digunakan: {sql_query}
- Hasil query dari database: {result}

Instruksi:
- Jika pertanyaan hanya meminta data tertentu, jawab langsung berdasarkan hasil query.
- Jika pertanyaan meminta analisis, berikan insight dari data tersebut.
- Awali setiap jawaban dengan "Jawaban Analisis:" atau "Jawaban Non-Analisis:" sesuai konteks.
- Berikan jawaban yang informatif, jelas, dan mudah dipahami dalam bahasa Indonesia.
- Jika data lebih bagus disajikan dalam tabel, sajikan dalam tabel Markdown.
- Selalu sertakan sumber data di akhir dengan "Sumber: (data apa saja yang digunakan)".

Jawaban:
""")

# --- 5. AI knowledge fallback (DB returned empty) ---
ai_knowledge_prompt = ChatPromptTemplate.from_template("""
Kamu adalah asisten AI yang berpengetahuan luas, khususnya tentang data dan bisnis perusahaan.

Pertanyaan user: {question}

Data dari database tidak tersedia atau tidak ditemukan untuk menjawab pertanyaan ini.
Jawablah berdasarkan pengetahuan umummu tentang topik ini dengan jelas dan informatif.
Jika memang tidak ada informasi yang bisa diberikan, sampaikan dengan sopan.

Awali jawaban dengan "Jawaban AI:" dan jelaskan bahwa data tidak tersedia di database.

Jawaban:
""")

# --- 6. Web search (GENERAL) ---
web_search_prompt = ChatPromptTemplate.from_template("""
Kamu adalah asisten AI yang membantu menjawab pertanyaan berdasarkan informasi dari internet.

Pertanyaan user:
{question}

Informasi yang ditemukan dari web:
{web_results}

Instruksi:
- Jawab pertanyaan user secara jelas dan informatif berdasarkan informasi yang ditemukan.
- Awali jawaban dengan "Jawaban Web:"
- Selalu sertakan sumber URL di akhir dengan format "Sumber: [url1, url2, ...]"
- Jika informasi tidak cukup, katakan bahwa informasi tidak tersedia.

Jawaban:
""")


# ===============================
# Helpers
# ===============================


def classify_intent(question: str) -> str:
    """Return 'RAG', 'DATABASE', or 'GENERAL'."""
    raw = llm.invoke(intent_prompt.format(question=question))
    result = raw.content.strip().upper()
    # Extract only the keyword in case LLM adds extra text
    for keyword in ("RAG", "DATABASE", "GENERAL"):
        if keyword in result:
            return keyword
    return "GENERAL"


def format_result_as_table(sql_query: str, max_rows: int = 50) -> str:
    """Run SQL via pandas and return result as Markdown table, or '' if empty."""
    with engine.connect() as conn:
        df = pd.read_sql(text(sql_query), conn)

    if df.empty:
        return ""

    if len(df) > max_rows:
        df = df.head(max_rows)

    for col in df.select_dtypes(
        include=["datetime64[ns]", "datetime64[ns, UTC]"]
    ).columns:
        df[col] = df[col].dt.strftime("%Y-%m-%d")

    df = df.fillna("-")
    return df.to_markdown(index=False)


def search_serp_and_extract(question: str) -> tuple[str, list[str]]:
    """Search via SerpAPI, return (combined_snippets, list_of_urls)."""
    client = serpapi.Client(api_key=SERP_API_KEY)
    results = client.search(
        {
            "engine": "google",
            "q": question,
            "location": "Indonesia",
            "hl": "id",
            "gl": "id",
            "num": 5,
        }
    )

    snippets: list[str] = []
    urls: list[str] = []

    ai_overview = results.get("ai_overview", {})
    for block in ai_overview.get("text_blocks", []):
        if block.get("type") == "paragraph":
            s = block.get("snippet", "").strip()
            if s:
                snippets.append(s)

    if not snippets:
        for item in results.get("organic_results", [])[:5]:
            s = item.get("snippet", "").strip()
            link = item.get("link", "")
            if s:
                snippets.append(f"[{link}]\n{s}" if link else s)
            if link:
                urls.append(link)

    combined = (
        "\n\n".join(snippets) if snippets else "Tidak ada informasi yang ditemukan."
    )
    return combined, urls


# ===============================
# Core ask() function
# ===============================
def ask(question: str) -> dict:
    """
    Process a question and return:
    {
        "answer":    str,
        "source":    "RAG" | "DATABASE" | "AI_KNOWLEDGE" | "WEB",
        "sql_query": str | None,
        "urls":      list[str],
        "intent":    str,
    }

    Workflow:
        RAG      → Persona / Dahana knowledge answer
        DATABASE → SQL → data found → analyse
                       → data empty → AI general knowledge
        GENERAL  → SerpAPI web search
    """

    intent = classify_intent(question)

    # ── RAG: non-technical / identity / about Dahana ──────────────
    if intent == "RAG":
        jawaban = llm.invoke(rag_prompt.format(question=question))
        return {
            "answer": jawaban.content,
            "source": "RAG",
            "sql_query": None,
            "urls": [],
            "intent": intent,
        }

    # ── DATABASE: try SQL first ────────────────────────────────────
    if intent == "DATABASE":
        try:
            raw_sql = llm.invoke(
                sql_prompt.format(table_info=table_info, question=question)
            )
            sql_query = raw_sql.content.split("SQLQuery:")[-1].strip()
            # Strip any accidental markdown fences
            sql_query = re.sub(r"```[a-z]*\n?", "", sql_query).strip("`").strip()

            result = format_result_as_table(sql_query)

            if result:
                jawaban = llm.invoke(
                    analysis_prompt.format(
                        question=question, sql_query=sql_query, result=result
                    )
                )
                return {
                    "answer": jawaban.content,
                    "source": "DATABASE",
                    "sql_query": sql_query,
                    "urls": [],
                    "intent": intent,
                }
        except Exception:
            sql_query = None

        # DB returned empty or failed → answer from AI knowledge
        jawaban = llm.invoke(ai_knowledge_prompt.format(question=question))
        return {
            "answer": jawaban.content,
            "source": "AI_KNOWLEDGE",
            "sql_query": sql_query if "sql_query" in dir() else None,
            "urls": [],
            "intent": intent,
        }

    # ── GENERAL: SerpAPI web search ────────────────────────────────
    web_results, urls = search_serp_and_extract(question)
    jawaban_web = llm.invoke(
        web_search_prompt.format(question=question, web_results=web_results)
    )
    return {
        "answer": jawaban_web.content,
        "source": "WEB",
        "sql_query": None,
        "urls": urls,
        "intent": intent,
    }
