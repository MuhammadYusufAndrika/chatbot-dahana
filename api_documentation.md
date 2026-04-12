# DahanaChatbot – REST API Documentation

**Base URL (local):** `http://localhost:8000`  
**Interactive Docs:** `http://localhost:8000/docs` (Swagger UI) · `http://localhost:8000/redoc` (ReDoc)

---

## Quick Start

### 1. Start the API server (in a separate terminal)
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```
The Streamlit UI can keep running in parallel on its own port (8501).

### 2. Test it's alive
```bash
curl http://localhost:8000/health
```

---

## Endpoints

### `GET /health`  ·  `GET /`
Health check. Returns API status and version.

**Response `200 OK`**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `POST /chat`
> **Main chatbot endpoint.** Send a question, get a natural-language answer.

#### Request

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `question` | `string` | ✅ | 1–1000 chars | The question (Bahasa Indonesia or English) |

```json
{
  "question": "siapakah Abdul Latip?"
}
```

#### Response `200 OK`

| Field | Type | Description |
|-------|------|-------------|
| `answer` | `string` | Natural-language answer from the chatbot |
| `source` | `"DATABASE"` \| `"WEB"` | Where the answer was retrieved from |
| `sql_query` | `string \| null` | SQL query used *(only when `source = DATABASE`)* |
| `urls` | `string[]` | Source URLs *(only when `source = WEB`)* |

**Example – answer from database**
```json
{
  "answer": "Jawaban Non-Analisis: Abdul Latip, ST menjabat sebagai Senior Manajer Pelayanan Korporasi di Departemen Sekretariat Perusahaan...\n\nSumber: (tabel karyawan_homis)",
  "source": "DATABASE",
  "sql_query": "SELECT * FROM karyawan_homis WHERE nama_karyawan ILIKE '%Abdul Latip%' LIMIT 50",
  "urls": []
}
```

**Example – answer from web (SerpAPI)**
```json
{
  "answer": "Jawaban Web: PT Dahana adalah Badan Usaha Milik Negara (BUMN) Indonesia yang bergerak di bidang industri bahan berenergi tinggi...\n\nSumber: [https://www.dahana.com/...]",
  "source": "WEB",
  "sql_query": null,
  "urls": [
    "https://www.dahana.com/about",
    "https://id.wikipedia.org/wiki/Dahana"
  ]
}
```

#### Error Responses

| Status | Meaning |
|--------|---------|
| `422 Unprocessable Entity` | `question` field missing or empty |
| `500 Internal Server Error` | LLM / database / SerpAPI error |

---

## Routing Logic

```
POST /chat  →  question
                  │
                  ▼
        Intent Classifier (LLM)
                  │
        ┌─────────┴──────────┐
        │                    │
      DATABASE              WEB
        │                    │
   Generate SQL         SerpAPI Search
   Run on DB            Extract AI Overview paragraphs
        │                (fallback: organic snippets)
   Empty result? ──YES──►     │
        │ NO                  ▼
        ▼               LLM composes answer
   LLM analyses              │
   DB result                 ▼
        │               source = "WEB"
        ▼
   source = "DATABASE"
```

---

## Code Examples

### Python (`requests`)
```python
import requests

response = requests.post(
    "http://localhost:8000/chat",
    json={"question": "siapakah Abdul Latip?"}
)
data = response.json()
print(data["answer"])
print("Source:", data["source"])
```

### JavaScript (`fetch`)
```javascript
const res = await fetch("http://localhost:8000/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question: "berapa total produksi bulan ini?" }),
});
const data = await res.json();
console.log(data.answer);
```

### cURL
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "pt dahana adalah"}'
```

### PHP (`curl`)
```php
$ch = curl_init("http://localhost:8000/chat");
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode(["question" => "siapakah Abdul Latip?"]));
curl_setopt($ch, CURLOPT_HTTPHEADER, ["Content-Type: application/json"]);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$response = json_decode(curl_exec($ch), true);
echo $response["answer"];
```

---

## Project File Structure

```
PoC_Dahanalyzer/
├── app.py              ← Streamlit UI  (run: streamlit run app.py)
├── api.py              ← FastAPI REST server  (run: uvicorn api:app ...)
├── chatbot_core.py     ← Shared chatbot brain (used by both)
├── .env                ← GROQ_API_KEY, SERP_API_KEY, database_url
└── requirements.txt
```

> [!NOTE]
> **Both servers can run at the same time.**  
> Streamlit → port 8501 · FastAPI → port 8000  
> They both import from `chatbot_core.py`.

> [!IMPORTANT]
> **For production**, restrict `allow_origins` in `api.py` CORS middleware to your specific frontend domain instead of `"*"`.
