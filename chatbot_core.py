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

# Normalise the URL so SQLAlchemy has the correct driver.
# MySQL:  mysql://… → mysql+pymysql://…
# PgSQL:  postgresql://… → postgresql+psycopg2://…
def _normalize_db_url(url: str) -> str:
    if url.startswith("mysql://") and "+pymysql" not in url:
        return url.replace("mysql://", "mysql+pymysql://", 1)
    if url.startswith("postgresql://") and "+" not in url.split("://")[0]:
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


_db_url = _normalize_db_url(DATABASE_URL)

# Dialect detection (used to pick the right SQL typo/style rules)
_IS_MYSQL = _db_url.startswith("mysql")
_IS_POSTGRES = _db_url.startswith("postgresql")

# ===============================
# Init LLM
# ===============================
llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
    temperature=0,
)

# ===============================
# Lazy DB Init (connect only when needed)
# ===============================
_db = None
_table_info = None
_engine = None


def _get_db():
    """Lazily initialize SQLDatabase connection."""
    global _db, _table_info
    if _db is None:
        _db = SQLDatabase.from_uri(_db_url)
        _table_info = _db.get_table_info()
    return _db, _table_info


def _get_engine():
    """Lazily initialize SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(_db_url)
    return _engine


# ===============================
# Prompts
# ===============================

# --- 1. Intent classification ---
intent_prompt = ChatPromptTemplate.from_template("""
Kamu adalah classifier yang sangat akurat. Tugasmu adalah mengklasifikasikan pertanyaan user ke dalam salah satu kategori berikut:

- RAG      : Pertanyaan non-teknis seperti salam, identitas AI, pertanyaan tentang chatbot ini, atau pertanyaan tentang PT Dahana secara umum (sejarah, profil, bisnis, dll). Contoh: "halo", "siapa kamu", "apa itu PT Dahana", "kamu bisa apa".
- DATABASE : Pertanyaan yang membutuhkan data dari database internal (data karyawan, absensi, produksi, produk/katalog, knowledge produk, dll). Contoh: "berapa karyawan yang hadir minggu ini", "siapa yang tidak masuk hari ini", "total produksi bulan lalu", "produk apa saja yang tersedia", "berapa harga produk AR Headset", "apa yang kamu ketahui tentang AR Headset Pro", "modern office chair adalah".
- PENTING — Jika pertanyaan menyebutkan NAMA PRODUK atau katalog (mis. "kursi kantor", "smart home speaker", "AR Headset"), maka PASTIKAN masuk kategori DATABASE, bukan RAG/GENERAL.
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
- Menjelaskan produk/katalog yang ditampilkan di katalog AR.
- Memberikan insight berbasis data untuk mendukung pengambilan keputusan.

Jawab pertanyaan berikut dengan ramah, profesional, dan informatif dalam bahasa Indonesia:

Pertanyaan: {question}

Jawaban:
""")

# --- 2b. RAG grounded with web search (factual Dahana questions) ---
rag_web_prompt = ChatPromptTemplate.from_template("""
Kamu adalah **DahanaBot SuperBrain**, asisten AI cerdas milik **PT DAHANA (Persero)**.

Profil dasar PT DAHANA (boleh dipakai bila web tidak lengkap):
- PT DAHANA (Persero) adalah perusahaan BUMN Indonesia yang bergerak di bidang bahan peledak (handak) dan solusi pertahanan.
- Berdiri sejak 1966 (Proyek Angkatan Udara RI di Tasikmalaya), menjadi Perum 1973, menjadi PT (Persero) 1991.
- Kantor pusat / Energetic Material Center di Subang, Jawa Barat.
- Melayani sektor pertambangan, migas, konstruksi, dan pertahanan nasional.

Instruksi:
- Jawab pertanyaan user dengan ramah, profesional, dan informatif dalam bahasa Indonesia.
- UTAMAKAN bagian "[AI Overview Google]" dari hasil pencarian di bawah — itu ringkasan resmi Google.
- Bila AI Overview menjawab pertanyaan, sampaikan jawabannya dengan bahasa yang rapi (jangan copy-paste mentah).
- Bila web tidak lengkap, lengkapi dengan Profil dasar di atas.
- Jangan menolak menjawab bila AI Overview / profil dasar sudah cukup.
- Jangan menyebutkan bahwa kamu melakukan pencarian web; cukup jawab seolah itu pengetahuan DahanaBot.
- Selalu akhiri jawaban dengan daftar sumber: "Sumber: [url1, url2, ...]" memakai URL dari hasil pencarian.

Pertanyaan: {question}

Hasil pencarian web:
{web_results}

Jawaban:
""")

# --- 3. SQL generation ---
sql_prompt = ChatPromptTemplate.from_template("""
Kamu adalah seorang **Data Analyst senior** sekaligus **Database Administrator berpengalaman**.
Kamu sangat memahami struktur, relasi, serta isi database.

Tugasmu:
- Hasilkan query MySQL yang valid, efisien, dan optimal untuk menjawab pertanyaan user.
- Jangan gunakan format kode atau pembungkus Markdown. Berikan hanya query SQL dalam bentuk teks biasa.
- Gunakan best practice SQL. BATASI dengan LIMIT 50.
- PENTING — Dialek database adalah MySQL. Gunakan `LIKE` (bukan `ILIKE`, karena ILIKE hanya ada di PostgreSQL) untuk pencarian teks/nama yang toleran terhadap besar kecil huruf. MySQL kolasi default (mis. utf8mb4_general_ci) sudah case-insensitive.
- Nama kolom yang berada di MySQL bisa langsung dipakai tanpa double-quote. Jika ada nama kolom yang bentrok dengan kata kunci MySQL, bungkus dengan backtick (`), mis. `metadata`.
- Untuk pertanyaan tentang produk/katalog (website GLB-AR), gunakan tabel `products` (kolom: product_id, product_name, description, model_url, poster_url, category, metadata, view_count, ar_activation_count, is_active).
- Untuk pertanyaan tentang pengetahuan/info tambahan produk yang diisi admin (knowledge base), gunakan tabel `product_knowledge` (kolom: id, product_id, title, content, is_active). `product_id` menghubungkan ke tabel `products` (NULL = knowledge umum). Gabungkan dengan tabel `products` via product_id bila perlu, mis. untuk memfilter knowledge milik produk tertentu.
- Untuk pencarian nama orang di tabel karyawan_hcmis, gunakan kolom `ckey` dengan LIKE. Kolom `ckey` berisi gabungan nama dan tanggal lahir, contoh format: 'Abdul Latip, ST1979-03-06 00:00:00'. Jika user menyebut nama, cukup `ckey LIKE '%nama%'`.
- Jangan berikan jawaban naratif, hanya query MySQL murni.

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

# --- 4b. Product info answer (product mentioned in question) ---
product_info_prompt = ChatPromptTemplate.from_template("""
Kamu adalah asisten virtual situs GLB-AR. User bertanya tentang produk yang ada di katalog.

Pertanyaan user: {question}

Informasi produk dari database:
{product_info}

Instruksi:
- Jawab dengan bahasa Indonesia yang jelas, informatif, dan ramah.
- Sampaikan **deskripsi produk** secara rapi dan ringkas sebagai jawaban utamanya.
- Jika ada spesifikasi/metadata tambahan, sebutkan.
- Jika ada pengetahuan tambahan dari admin, gunakan untuk memperkaya jawaban.
- Jangan menambahkan informasi produk yang tidak tercantum di data yang diberikan.
- Awali jawaban dengan "Jawaban Produk:".
- Akhiri dengan "Sumber: Katalog produk GLB-AR".

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

Informasi yang ditemukan dari web (bagian [AI Overview Google] adalah ringkasan resmi Google — utamakan itu):
{web_results}

Instruksi:
- Jawab pertanyaan user secara jelas dan informatif berdasarkan informasi yang ditemukan, utamakan AI Overview.
- Awali jawaban dengan "Jawaban Web:"
- Selalu sertakan sumber URL di akhir dengan format "Sumber: [url1, url2, ...]"
- Jika informasi tidak cukup, katakan bahwa informasi tidak tersedia.

Jawaban:
""")


# ===============================
# Helpers
# ===============================


# Kapitalized column names in dm_produksi were previously double-quoted
# for PostgreSQL. MySQL is case-insensitive for column names, so this
# safety-net is only applied when the target dialect is PostgreSQL.
_CAPITALIZED_COLS = ["Realisasi", "Tanggal", "Pabrik", "Produk", "Rencana"]


def _fix_column_quoting(sql: str) -> str:
    """
    Safety net (PostgreSQL only): wrap unquoted capitalized column names from
    dm_produksi in double-quotes so PostgreSQL doesn't lowercase them.
    Skips tokens already inside double-quotes or single-quotes.
    For MySQL this is intentionally a no-op (double quotes are string literals).
    """
    if not _IS_POSTGRES:
        return sql
    for col in _CAPITALIZED_COLS:
        # Match the column name only when it is NOT already wrapped in double-quotes
        # and is a word boundary (not part of a larger identifier)
        pattern = r'(?<!")(\b' + re.escape(col) + r'\b)(?!")'
        sql = re.sub(pattern, f'"{col}"', sql)
    return sql


# Phrases that are pure smalltalk / chatbot identity — no web search needed.
_SMALLTALK_PATTERNS = (
    "halo", "hallo", "hai", "hi", "hello", "selamat pagi", "selamat siang",
    "selamat sore", "selamat malam", "apa kabar", "siapa kamu", "siapa anda",
    "kamu bisa apa", "kamu bisa bantu", "terima kasih", "makasih", "thanks",
    "thank you", "bye", "dadah", "sampai jumpa",
)


def _is_smalltalk(question: str) -> bool:
    """True for greetings / chatbot-identity questions that don't need web search."""
    q = question.lower().strip()
    if q in _SMALLTALK_PATTERNS:
        return True
    # Containment for longer phrasing (e.g. "halo bot", "siapa namamu")
    if any(p in q for p in ("siapa kamu", "siapa anda", "kamu bisa apa", "kamu adalah", "namamu")):
        return True
    return False


def classify_intent(question: str) -> str:
    """Return 'RAG', 'DATABASE', or 'GENERAL'."""
    raw = llm.invoke(intent_prompt.format(question=question))
    result = raw.content.strip().upper()
    # Extract only the keyword in case LLM adds extra text
    for keyword in ("RAG", "DATABASE", "GENERAL"):
        if keyword in result:
            return keyword
    return "GENERAL"


def _match_product_name(question: str) -> str | None:
    """
    Find a product whose name is mentioned in the question, using tolerant
    word-token matching (handles minor typos like "Chairr" vs "Chair").
    Returns the exact product_name stored in the database, or None.
    """
    q_words = set(re.findall(r"[a-z0-9]+", question.lower()))
    try:
        with _get_engine().connect() as conn:
            rows = conn.execute(
                text("SELECT product_name FROM products WHERE is_active = 1")
            ).fetchall()
    except Exception:
        return None

    best = None
    best_score = 0
    for (name,) in rows:
        if not name:
            continue
        name_words = [
            w for w in re.findall(r"[a-z0-9]+", name.lower()) if len(w) > 2
        ]
        if not name_words:
            continue
        score = sum(1 for w in name_words if w in q_words)
        # Require a majority of the product's significant words to be present
        if score > best_score and score >= max(1, (len(name_words) + 1) // 2):
            best_score = score
            best = name
    return best


def _mentions_known_product(question: str) -> bool:
    """
    Check if the question mentions a known product (product_name or a
    knowledge entry title). Used as a safety net so questions about catalog
    products are always routed to the DATABASE path, even if the LLM
    classifier mislabels them as RAG/GENERAL.
    """
    if _match_product_name(question):
        return True
    try:
        q = question.lower().strip()
        with _get_engine().connect() as conn:
            rows = conn.execute(
                text("SELECT title FROM product_knowledge WHERE is_active = 1")
            ).fetchall()
        for (title,) in rows:
            if title and title.lower() in q:
                return True
        return False
    except Exception:
        return False


def _is_definitional(question: str) -> bool:
    """True for 'what/how/why' definitional questions (apa itu, pengertian, ...)."""
    import re as _re
    q = question.lower()
    patterns = (
        r"\bapa itu\b", r"\bapa\b", r"\bpengertian\b", r"\bdefinisi\b",
        r"\bsiapa\b", r"\bbagaimana\b", r"\bmengapa\b", r"\bkenapa\b",
        r"\bjelaskan\b", r"\bmaksud\b", r"\bperbedaan\b",
        r"\bkapan\b", r"\btahun berapa\b", r"\bberapa\b",
        r"\bberdiri\b", r"\bsejarah\b", r"\bdimana\b", r"\bdi mana\b",
    )
    return any(_re.search(p, q) for p in patterns)


def _resolve_intent(question: str) -> str:
    """Classify intent, with a database lookup safety net for product names."""
    intent = classify_intent(question)

    # Product explicitly mentioned in catalog → always DATABASE (SQL / product info).
    if intent in ("RAG", "GENERAL") and _mentions_known_product(question):
        return "DATABASE"

    # Definitional question about Dahana (e.g. "apa itu bulk emulsi") that does
    # NOT match a known catalog product → route to web-grounded RAG instead of
    # running SQL against the catalog. Otherwise the SQL agent returns irrelevant
    # rows (e.g. a random product) and the analysis step gets confused.
    if intent == "DATABASE" and not _mentions_known_product(question) and _is_definitional(question):
        return "RAG"

    return intent


def _find_product_in_question(question: str) -> str | None:
    """Return the product_name from the `products` table that appears in the question."""
    return _match_product_name(question)


def _fetch_product_info(product_name: str) -> dict | None:
    """Fetch the product row (id, name, description, category, metadata)."""
    try:
        with _get_engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT product_id, product_name, description, category, metadata "
                    "FROM products WHERE product_name = :name AND is_active = 1 LIMIT 1"
                ),
                {"name": product_name},
            ).mappings().first()
        return dict(row) if row else None
    except Exception:
        return None


def _fetch_product_knowledge(product_name: str) -> list[dict]:
    """Fetch admin-provided knowledge entries linked to a product."""
    try:
        with _get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT pk.title, pk.content "
                    "FROM product_knowledge pk "
                    "JOIN products p ON p.product_id = pk.product_id "
                    "WHERE p.product_name LIKE :name AND pk.is_active = 1"
                ),
                {"name": f"%{product_name}%"},
            ).fetchall()
        return [{"title": r[0], "content": r[1]} for r in rows]
    except Exception:
        return []


# Words that indicate a numeric/analytics question about a product.
# For these, the chatbot should NOT answer from the static product info,
# but let the SQL agent compute the answer instead.
_ANALYTICS_WORDS = (
    "berapa",
    "jumlah",
    "total",
    "hitung",
    "statistik",
    "count",
    "persen",
    "rata-rata",
    "terbanyak",
    "tertinggi",
    "terendah",
    "view",
    "dilihat",
    "aktivasi",
    "sering",
)


def _format_product_info(info: dict, knowledge: list[dict]) -> str:
    """Format product data + knowledge into a readable text for the LLM."""
    lines = [f"Nama Produk: {info.get('product_name') or '-'}"]
    lines.append(f"Deskripsi: {info.get('description') or '-'}")
    if info.get("category"):
        lines.append(f"Kategori: {info['category']}")
    if info.get("metadata"):
        lines.append(f"Spesifikasi: {info['metadata']}")
    if knowledge:
        knowledge_text = " ".join(k["content"] for k in knowledge)
        lines.append(f"Pengetahuan tambahan (dari admin): {knowledge_text}")
    return "\n".join(lines)


def format_result_as_table(sql_query: str, max_rows: int = 50) -> str:
    """Run SQL via pandas and return result as Markdown table, or '' if empty."""
    with _get_engine().connect() as conn:
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


def _format_ai_overview_blocks(text_blocks: list) -> str:
    """Format SerpAPI ai_overview.text_blocks (paragraph/heading/list) jadi teks rapi.

    Contoh struktur per dokumentasi SerpAPI:
      {"type": "paragraph", "snippet": "...", ...}
      {"type": "heading", "snippet": "..."}
      {"type": "list", "list": [{"title": "...", "snippet": "..."}, ...]}
    """
    parts: list[str] = []
    for block in text_blocks or []:
        btype = block.get("type")
        if btype == "paragraph":
            s = (block.get("snippet") or "").strip()
            if s:
                parts.append(s)
        elif btype == "heading":
            s = (block.get("snippet") or "").strip()
            if s:
                parts.append(f"\n## {s}")
        elif btype == "list":
            for item in block.get("list") or []:
                title = (item.get("title") or "").strip()
                snippet = (item.get("snippet") or "").strip()
                if title and snippet:
                    parts.append(f"- {title} {snippet}".strip())
                elif snippet:
                    parts.append(f"- {snippet}")
                elif title:
                    parts.append(f"- {title}")
    return "\n\n".join(parts).strip()


def _fetch_ai_overview(question: str, page_token: str) -> tuple[str, list[str]]:
    """Fetch expanded Google AI Overview via engine=google_ai_overview.

    Returns (formatted_text, reference_urls). Empty string bila gagal.
    """
    if not page_token:
        return "", []
    try:
        client = serpapi.Client(api_key=SERP_API_KEY)
        expanded = client.search(
            {"engine": "google_ai_overview", "page_token": page_token}
        )
        aio = expanded.get("ai_overview", {}) or {}
        text = _format_ai_overview_blocks(aio.get("text_blocks", []))
        urls: list[str] = []
        for ref in aio.get("references", []) or []:
            link = (ref.get("link") or "").strip()
            if link and link not in urls:
                urls.append(link)
        return text, urls
    except Exception as e:
        print(f"[DEBUG] AI Overview fetch failed: {e}")
        return "", []


def search_serp_and_extract(question: str) -> tuple[str, list[str]]:
    """Search via SerpAPI (Google + Google AI Overview), return (combined, urls).

    Alur sesuai dokumentasi SerpAPI:
      1. GET search.json engine=google -> ambil ai_overview.page_token + organic.
      2. GET engine=google_ai_overview page_token -> ambil
         ai_overview.text_blocks (paragraph/heading/list) + references.
      3. Gabung: [AI Overview Google] + [Hasil Organik] + answer_box/knowledge_graph.
    """
    # NOTE: jangan pakai "location":"Indonesia" — parameter itu membuat
    # engine google_ai_overview mengembalikan text_blocks=None (kosong).
    # Cukup hl/gl untuk hasil Indonesia.
    # Perkaya query Dahana agar AI Overview muncul konsisten.
    q = question.strip()
    if "dahana" in q.lower() and "pt dahana" not in q.lower():
        q = q + " PT DAHANA Persero"
    client = serpapi.Client(api_key=SERP_API_KEY)
    results = client.search(
        {
            "engine": "google",
            "q": q,
            "hl": "id",
            "gl": "id",
            "num": 5,
        }
    )

    sections: list[str] = []
    urls: list[str] = []

    # ── 1. Google AI Overview (2-step: page_token -> expanded) ──
    ai_text, ai_urls = "", []
    try:
        page_token = (results.get("ai_overview", {}) or {}).get("page_token", "")
        if page_token:
            ai_text, ai_urls = _fetch_ai_overview(question, page_token)
    except Exception as e:
        print(f"[DEBUG] AI Overview step failed: {e}")
    if ai_text:
        sections.append("[AI Overview Google]\n" + ai_text)
        for u in ai_urls:
            if u not in urls:
                urls.append(u)

    # ── 2. Answer box / Knowledge graph (bila ada, sering akurat utk fakta) ──
    for key in ("answer_box", "knowledge_graph"):
        box = results.get(key, {}) or {}
        if isinstance(box, dict):
            for field in ("answer", "snippet", "description", "title"):
                val = (box.get(field) or "")
                if isinstance(val, str) and val.strip():
                    sections.append(f"[{key}]\n{val.strip()}")
                    break

    # ── 3. Organic results (pelengkap + sumber) ──
    organic_lines: list[str] = []
    for item in results.get("organic_results", [])[:5]:
        s = (item.get("snippet") or "").strip()
        link = (item.get("link") or "").strip()
        title = (item.get("title") or "").strip()
        if s:
            organic_lines.append(f"- {title} [{link}]\n  {s}" if link else f"- {s}")
        if link and link not in urls:
            urls.append(link)
    if organic_lines:
        sections.append("[Hasil Organik]\n" + "\n".join(organic_lines))

    combined = (
        "\n\n".join(sections) if sections else "Tidak ada informasi yang ditemukan."
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
        "source":    "RAG" | "DATABASE" | "PRODUCT" | "AI_KNOWLEDGE" | "WEB",
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

    intent = _resolve_intent(question)

    # ── RAG: non-technical / identity / about Dahana ──────────────
    if intent == "RAG":
        # Pure smalltalk / chatbot identity → answer from persona only.
        # Skipping web search here saves SERP API quota and latency.
        if _is_smalltalk(question):
            jawaban = llm.invoke(rag_prompt.format(question=question))
            return {
                "answer": jawaban.content,
                "source": "RAG",
                "sql_query": None,
                "urls": [],
                "intent": intent,
            }

        # Factual Dahana question → ground the answer with SERP API so it is
        # based on real web sources instead of the LLM's own (hallucinated) memory.
        try:
            web_results, urls = search_serp_and_extract(question)
            jawaban = llm.invoke(
                rag_web_prompt.format(question=question, web_results=web_results)
            )
            return {
                "answer": jawaban.content,
                "source": "WEB",
                "sql_query": None,
                "urls": urls,
                "intent": intent,
            }
        except Exception as e:
            print(f"[DEBUG] RAG web search failed, falling back to persona: {e}")
            # Fallback to persona-only answer if SERP is unavailable / errors.
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
        # Product-based questions: answer directly from the product info
        # (description + admin knowledge) when a catalog product is mentioned,
        # unless the question is asking for numbers/analytics.
        matched_product = _find_product_in_question(question)
        if matched_product and not any(w in question.lower() for w in _ANALYTICS_WORDS):
            info = _fetch_product_info(matched_product)
            if info:
                knowledge = _fetch_product_knowledge(matched_product)
                product_info = _format_product_info(info, knowledge)
                print(f"[DEBUG] Product answer for: {matched_product}")
                jawaban = llm.invoke(
                    product_info_prompt.format(
                        question=question, product_info=product_info
                    )
                )
                return {
                    "answer": jawaban.content,
                    "source": "PRODUCT",
                    "sql_query": None,
                    "urls": [],
                    "intent": intent,
                }

        sql_query = None
        sql_error = None
        try:
            _, table_info = _get_db()
            raw_sql = llm.invoke(
                sql_prompt.format(table_info=table_info, question=question)
            )
            # Extract SQL after "SQLQuery:" marker if present, else take full content
            raw_content = raw_sql.content.strip()
            if "SQLQuery:" in raw_content:
                sql_query = raw_content.split("SQLQuery:")[-1].strip()
            else:
                sql_query = raw_content
            # Strip any accidental markdown fences
            sql_query = re.sub(r"```[a-z]*\n?", "", sql_query).strip("`").strip()

            print(f"[DEBUG] Intent   : {intent}")
            print(f"[DEBUG] SQL query: {sql_query}")

            if not sql_query:
                raise ValueError("LLM menghasilkan SQL kosong")

            # Auto-quote unquoted capitalized column names for dm_produksi
            sql_query = _fix_column_quoting(sql_query)
            print(f"[DEBUG] SQL fixed : {sql_query}")

            result = format_result_as_table(sql_query)
            print(f"[DEBUG] Result empty: {not bool(result)}")

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
        except Exception as e:
            sql_error = str(e)
            print(f"[DEBUG] SQL error : {sql_error}")

        # DB returned empty or failed → answer from AI knowledge
        jawaban = llm.invoke(ai_knowledge_prompt.format(question=question))
        return {
            "answer": jawaban.content,
            "source": "AI_KNOWLEDGE",
            "sql_query": sql_query,
            "sql_error": sql_error,
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
