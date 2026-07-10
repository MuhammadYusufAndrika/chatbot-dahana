# 🔬 Dahanalyzer

> **AI-powered analytics & chatbot platform for PT Dahana**  
> Combines a live company database, LLM reasoning, and Google Search into a single intelligent assistant.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📊 **Dashboard** | Real-time employee attendance chart + production forecast (Prophet) |
| 🤖 **SuperBrain Chatbot** | Ask anything in natural language — answered from DB, AI knowledge, or the web |
| 🔍 **Smart Intent Routing** | LLM classifier routes to **RAG**, **DATABASE**, or **GENERAL** automatically |
| 🗄️ **SQL Agent** | Generates & runs PostgreSQL queries on the fly |
| 🌐 **Google Fallback** | Uses SerpAPI (AI Overview) for general questions not related to company data |
| 🔌 **REST API** | FastAPI backend so any app can call the chatbot |

---

## 🏗️ Architecture

```
┌─────────────────────┐     ┌──────────────────────┐
│   Streamlit UI      │     │   FastAPI REST API   │
│   app.py (:8501)    │     │   api.py  (:8000)    │
└────────┬────────────┘     └──────────┬───────────┘
         │                             │
         └────────────┬────────────────┘
                      ▼
             chatbot_core.py
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
    Groq LLM    PostgreSQL    SerpAPI
  (llama-3.1)    (Supabase)   (Google)
```

### Chatbot routing logic

```
User question
      │
      ▼
Intent Classifier (LLM)
      │
      ├── RAG ──────► LLM answers using Dahana persona & general knowledge
      │
      ├── DATABASE ──► Generate SQL ──► Run on DB ──► LLM analysis
      │                                      │
      │                               Empty / Error?
      │                                      │ YES
      │                                      ▼
      │                              AI Knowledge fallback
      │                              (LLM answers from general knowledge)
      │
      └── GENERAL ──► SerpAPI Search
                      (AI Overview paragraphs → organic snippets fallback)
                            │
                            ▼
                       LLM composes answer
```

**Intent categories:**
| Intent | When used |
|---|---|
| `RAG` | Greetings, chatbot identity, general info about PT Dahana |
| `DATABASE` | Questions requiring internal company data (employees, attendance, production) |
| `GENERAL` | General knowledge questions not related to company data |

---

## 📁 Project Structure

```
PoC_Dahanalyzer/
├── app.py              # Streamlit UI (Dashboard + Chatbot page)
├── api.py              # FastAPI REST server
├── chatbot_core.py     # Shared chatbot brain (LLM + DB + SerpAPI)
├── requirements.txt    # Python dependencies
├── .env                # Secret keys (not committed to git)
└── .gitignore
```

---

## ⚙️ Prerequisites

- Python **3.10+**
- PostgreSQL database (Supabase or self-hosted)
- [Groq API key](https://console.groq.com/) (free tier available)
- [SerpAPI key](https://serpapi.com/) (100 free searches/month)

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd PoC_Dahanalyzer
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY  = your_groq_api_key_here
SERP_API_KEY  = your_serpapi_key_here
database_url  = postgresql://user:password@host:5432/dbname
```

### 4. Run the Streamlit UI

```bash
streamlit run app.py
```
Open → `http://localhost:8501`

### 5. Run the REST API *(optional, separate terminal)*

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```
Open → `http://localhost:8000/docs` for interactive Swagger UI

> Both servers can run **simultaneously** — they share the same `chatbot_core.py`.

---

## 🔌 REST API

### Base URL
```text
http://localhost:8000
```

### Authentication
API ini memakai header `X-API-Key`.

Contoh:
```http
X-API-Key: your-secret-api-key
```

Set environment variable di server:
```env
API_KEY=your-secret-api-key
```

### Headers
```http
Content-Type: application/json
X-API-Key: your-secret-api-key
```

### Endpoint

#### `GET /health`
Cek apakah server API aktif.

**Auth:** tidak perlu

**Contoh respons**
```json
{ "status": "ok", "version": "1.0.0" }
```

#### `POST /chat`
Mengirim pertanyaan ke chatbot dan menerima jawaban natural language.

**Auth:** wajib `X-API-Key`

**Request body**
```json
{
  "question": "siapakah Abdul Latip?"
}
```

**Field request**

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | `string` | Ya | Pertanyaan untuk chatbot, Bahasa Indonesia atau Inggris |

**Contoh respons — dari database**
```json
{
  "answer": "Jawaban Non-Analisis: Abdul Latip, ST menjabat sebagai Senior Manajer...",
  "source": "DATABASE",
  "sql_query": "SELECT * FROM karyawan_homis WHERE nama_karyawan ILIKE '%Abdul Latip%' LIMIT 50",
  "urls": []
}
```

**Contoh respons — dari web**
```json
{
  "answer": "Jawaban Web: PT Dahana adalah Badan Usaha Milik Negara (BUMN)...",
  "source": "WEB",
  "sql_query": null,
  "urls": ["https://www.dahana.com/about"]
}
```

**Field respons**

| Field | Type | Description |
|---|---|---|
| `answer` | `string` | Jawaban utama chatbot |
| `source` | `"DATABASE"` \| `"WEB"` \| `"RAG"` \| `"AI_KNOWLEDGE"` | Sumber jawaban |
| `sql_query` | `string \| null` | Query SQL yang dipakai, hanya untuk `DATABASE` / `AI_KNOWLEDGE` |
| `urls` | `string[]` | Daftar URL referensi, hanya untuk `WEB` |

**Nilai `source`:**
| Value | Arti |
|---|---|
| `DATABASE` | Jawaban dibangun dari hasil query ke database internal |
| `RAG` | Jawaban dibangun dari pengetahuan chatbot tentang PT Dahana |
| `AI_KNOWLEDGE` | Jawaban dari pengetahuan umum LLM (DB tidak menemukan data) |
| `WEB` | Jawaban dibangun dari hasil pencarian Google via SerpAPI |

### Cara pakai dari website lain

**JavaScript / Frontend**
```javascript
async function askChatbot(question) {
  const res = await fetch("http://localhost:8000/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": "your-secret-api-key",
    },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    throw new Error("Gagal mengambil jawaban dari chatbot");
  }

  return await res.json();
}

const result = await askChatbot("berapa total produksi bulan ini?");
console.log(result.answer);
```

**Python**
```python
import requests

resp = requests.post(
    "http://localhost:8000/chat",
    headers={"X-API-Key": "your-secret-api-key"},
    json={"question": "berapa total produksi bulan ini?"}
)
print(resp.json()["answer"])
```

**cURL**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{"question": "pt dahana adalah"}'
```

### Catatan integrasi frontend
- Jika website lain berbeda domain, pastikan CORS di `api.py` mengizinkan domain tersebut.
- Endpoint yang paling penting untuk ditampilkan di website lain adalah `POST /chat`.
- Jika ingin hanya menampilkan jawaban chatbot, gunakan field `answer`.
- Jika ingin menampilkan sumber, gunakan `source` dan `urls`.

### Example flow
1. Frontend mengirim `question` ke `POST /chat`
2. API mengembalikan `answer`, `source`, dan metadata tambahan
3. Frontend menampilkan `answer` ke user
4. Jika `source = WEB`, frontend bisa menampilkan daftar `urls`

### Health check
```bash
curl http://localhost:8000/health
``` 

---

### Minimal response shape
```json
{
  "answer": "...",
  "source": "DATABASE",
  "sql_query": null,
  "urls": []
}
``` 

---

## 🧠 Tech Stack

| Layer | Technology |
|---|---|
| UI | [Streamlit](https://streamlit.io/) |
| REST API | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| LLM | [Groq](https://groq.com/) — `llama-3.1-8b-instant` |
| LLM Framework | [LangChain](https://www.langchain.com/) |
| Database | PostgreSQL via [SQLAlchemy](https://www.sqlalchemy.org/) + psycopg2 |
| Web Search | [SerpAPI](https://serpapi.com/) (Google) |
| Forecasting | [Prophet](https://facebook.github.io/prophet/) |
| Charts | [Plotly](https://plotly.com/python/) |

---

## 🔒 Security Notes

- **Never commit `.env`** to git — it contains secret keys. Add it to `.gitignore`.
- In production, restrict CORS in `api.py` to your specific frontend domain:
  ```python
  allow_origins=["https://your-app.com"]
  ```
- API key authentication via `X-API-Key` header is **already implemented** on the `/chat` endpoint. Set `API_KEY` in `.env` to enable it. If `API_KEY` is empty, authentication is bypassed (useful for local development).
- Consider using HTTPS in production to protect API keys in transit.

---

## 📄 License

Internal use only — PT Dahana © 2026
