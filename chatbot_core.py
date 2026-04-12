"""
chatbot_core.py
---------------
Core chatbot logic shared between the Streamlit UI (app.py) and the REST API (api.py).
Handles: intent classification → SQL path / SerpAPI fallback.
"""

import os
import serpapi
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_community.utilities import SQLDatabase
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import create_engine

# ===============================
# Load environment
# ===============================
load_dotenv(override=True)

GROQ_API_KEY  = os.getenv("GROQ_API_KEY",  "")
SERP_API_KEY  = os.getenv("SERP_API_KEY",  "")
DATABASE_URL  = os.getenv("database_url",   "")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY tidak ditemukan di .env")
if not SERP_API_KEY:
    raise RuntimeError("SERP_API_KEY tidak ditemukan di .env")
if not DATABASE_URL:
    raise RuntimeError("database_url tidak ditemukan di .env")

# Normalise to psycopg2 driver
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

db         = SQLDatabase.from_uri(_db_url_pg)
table_info = db.get_table_info()
engine     = create_engine(DATABASE_URL)


# ===============================
# Prompts
# ===============================
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

analysis_prompt = ChatPromptTemplate.from_template("""
Kamu adalah **Data Analyst Profesional** yang sangat berpengalaman dalam analisis data.

Berikut adalah informasi yang ada:
- Pertanyaan: {question}
- SQL Query yang digunakan: {sql_query}
- Hasil query dari database: {result}

Instruksi:
- Jika pertanyaan hanya meminta data tertentu, jawab langsung berdasarkan hasil query.
- Jika pertanyaan meminta analisis, berikan insight dari data tersebut.
- Awali setiap jawaban dengan "Jawaban Analisis:" atau "Jawaban Non-Analisis:".
- Berikan jawaban yang informatif, jelas, dan mudah dipahami.
- Jika data lebih bagus disajikan dalam tabel, sajikan dalam tabel Markdown.
- Selalu sertakan sumber data di akhir dengan "Sumber: (data apa saja yang digunakan)".

Jawaban:
""")

intent_classifier_prompt = ChatPromptTemplate.from_template("""
Kamu adalah router cerdas untuk sistem chatbot perusahaan PT Dahana.

Database perusahaan berisi tabel-tabel berikut:
{table_info}

Tugasmu: Tentukan apakah pertanyaan user BISA dijawab dari database perusahaan di atas,
atau harus dicari dari internet.

ATURAN PENTING - Gunakan DATABASE jika:
- Pertanyaan menyebut nama orang (bisa jadi nama karyawan perusahaan)
- Pertanyaan tentang karyawan, jabatan, departemen, divisi, unit
- Pertanyaan tentang absensi, kehadiran, status karyawan
- Pertanyaan tentang produksi, rencana, realisasi
- Pertanyaan tentang data internal perusahaan apapun
- Pertanyaan yang MUNGKIN bisa dijawab dari database (jika ragu pilih DATABASE)

Gunakan WEB hanya jika pertanyaan JELAS tidak mungkin ada di database:
- Definisi atau penjelasan konsep umum
- Sejarah atau profil umum perusahaan
- Berita, kejadian eksternal, atau pengetahuan publik umum
- Pertanyaan yang sama sekali tidak berhubungan dengan data karyawan/produksi/absensi

Contoh:
- "siapakah abdul latip?" -> DATABASE
- "siapa saja karyawan departemen tambang?" -> DATABASE
- "berapa total produksi bulan ini?" -> DATABASE
- "pt dahana adalah" -> WEB
- "apa itu bahan peledak?" -> WEB
- "kapan dahana didirikan?" -> WEB
- "siapa presiden indonesia?" -> WEB

Jika ragu, pilih DATABASE.

Pertanyaan user: {question}

Jawaban (DATABASE/WEB):
""")

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
# SerpAPI helper
# ===============================
def search_serp_and_extract(question: str) -> tuple[str, list[str]]:
    """Search via SerpAPI, return (combined_snippets, list_of_urls)."""
    client  = serpapi.Client(api_key=SERP_API_KEY)
    results = client.search({
        "engine":   "google",
        "q":        question,
        "location": "Indonesia",
        "hl":       "id",
        "gl":       "id",
        "num":      5,
    })

    snippets: list[str] = []
    urls:     list[str] = []

    # Priority 1 – AI Overview paragraphs
    ai_overview = results.get("ai_overview", {})
    for block in ai_overview.get("text_blocks", []):
        if block.get("type") == "paragraph":
            s = block.get("snippet", "").strip()
            if s:
                snippets.append(s)

    # Priority 2 – Organic results (fallback)
    if not snippets:
        for item in results.get("organic_results", [])[:5]:
            s    = item.get("snippet", "").strip()
            link = item.get("link", "")
            if s:
                snippets.append(f"[{link}]\n{s}" if link else s)
            if link:
                urls.append(link)

    combined = "\n\n".join(snippets) if snippets else "Tidak ada informasi yang ditemukan."
    return combined, urls


# ===============================
# Core ask() function
# ===============================
def ask(question: str) -> dict:
    """
    Process a question and return a structured response dict:
    {
        "answer":    str,
        "source":    "DATABASE" | "WEB",
        "sql_query": str | None,   # only when source == DATABASE
        "urls":      list[str],    # only when source == WEB
    }
    """
    use_web = False
    sql_query: str | None = None
    urls: list[str] = []

    # ── Step 1: Intent classification ────────────────────────────────────
    try:
        intent_raw = llm.invoke(
            intent_classifier_prompt.format(table_info=table_info, question=question)
        )
        if "WEB" in intent_raw.content.strip().upper():
            use_web = True
    except Exception:
        use_web = False  # default to DB on classifier error

    # ── Step 2a: DATABASE path ────────────────────────────────────────────
    if not use_web:
        try:
            raw_sql = llm.invoke(sql_prompt.format(table_info=table_info, question=question))
            sql_query = raw_sql.content.split("SQLQuery:")[-1].strip()

            result = str(db.run(sql_query))

            if not result or result.strip() in ("", "[]", "None"):
                use_web = True
            else:
                if len(result) > 3000:
                    result = result[:3000] + "... [dipotong]"
                jawaban = llm.invoke(
                    analysis_prompt.format(
                        question=question, sql_query=sql_query, result=result
                    )
                )
                return {
                    "answer":    jawaban.content,
                    "source":    "DATABASE",
                    "sql_query": sql_query,
                    "urls":      [],
                }
        except Exception:
            use_web = True

    # ── Step 2b: WEB / SerpAPI path ───────────────────────────────────────
    web_results, urls = search_serp_and_extract(question)
    jawaban_web = llm.invoke(
        web_search_prompt.format(question=question, web_results=web_results)
    )
    return {
        "answer": jawaban_web.content,
        "source": "WEB",
        "sql_query": None,
        "urls": urls,
    }
