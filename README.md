# 🔬 Dahanalyzer

> **AI-powered analytics & chatbot platform for PT Dahana**  
> Combines a live company database, LLM reasoning, and Google Search into a single intelligent assistant.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📊 **Dashboard** | Real-time employee attendance chart + production forecast (Prophet) |
| 🤖 **SuperBrain Chatbot** | Ask anything in natural language — answered from DB or the web |
| 🔍 **Smart Intent Routing** | LLM classifier decides DB vs. web automatically |
| 🗄️ **SQL Agent** | Generates & runs PostgreSQL queries on the fly |
| 🌐 **Google Fallback** | Uses SerpAPI (AI Overview) when data isn't in the database |
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
      ├── DATABASE ──► Generate SQL ──► Run on DB ──► LLM analysis
      │                                      │
      │                               Empty result?
      │                                      │ YES
      └── WEB ◄────────────────────────────-┘
            │
            ▼
       SerpAPI Search
       (AI Overview paragraphs → organic snippets fallback)
            │
            ▼
       LLM composes answer
```

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
```
http://localhost:8000
```

### Endpoints

#### `GET /health`
Check that the API server is running.

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok", "version": "1.0.0" }
```

---

#### `POST /chat`
Send a question, get a natural-language answer.

**Request body**
```json
{
  "question": "siapakah Abdul Latip?"
}
```

**Response — answered from database**
```json
{
  "answer": "Jawaban Non-Analisis: Abdul Latip, ST menjabat sebagai Senior Manajer...",
  "source": "DATABASE",
  "sql_query": "SELECT * FROM karyawan_homis WHERE nama_karyawan ILIKE '%Abdul Latip%' LIMIT 50",
  "urls": []
}
```

**Response — answered from web**
```json
{
  "answer": "Jawaban Web: PT Dahana adalah Badan Usaha Milik Negara (BUMN)...",
  "source": "WEB",
  "sql_query": null,
  "urls": ["https://www.dahana.com/about"]
}
```

**Response fields**

| Field | Type | Description |
|---|---|---|
| `answer` | `string` | Natural-language answer |
| `source` | `"DATABASE"` \| `"WEB"` | Where the answer came from |
| `sql_query` | `string \| null` | SQL used (only for DATABASE answers) |
| `urls` | `string[]` | Source links (only for WEB answers) |

### Code examples

**Python**
```python
import requests

resp = requests.post(
    "http://localhost:8000/chat",
    json={"question": "berapa total produksi bulan ini?"}
)
print(resp.json()["answer"])
```

**JavaScript**
```javascript
const res = await fetch("http://localhost:8000/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question: "siapa karyawan departemen keuangan?" }),
});
const data = await res.json();
console.log(data.answer);
```

**cURL**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "pt dahana adalah"}'
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
- Consider adding API key authentication to the `/chat` endpoint before exposing it publicly.

---

## 📄 License

Internal use only — PT Dahana © 2026
