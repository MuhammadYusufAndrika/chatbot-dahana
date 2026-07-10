# DahanaChatbot – REST API Documentation

> **Version:** 1.0.0  
> **Maintained by:** PT Dahana – IT Team

---

## Table of Contents

1. [Overview](#overview)
2. [Base URL & Interactive Docs](#base-url--interactive-docs)
3. [Authentication](#authentication)
4. [Endpoints](#endpoints)
   - [GET / — Health Check](#get--health-check)
   - [GET /health — Health Check (Alias)](#get-health--health-check-alias)
   - [POST /chat — Ask a Question](#post-chat--ask-a-question)
5. [Response Source Types](#response-source-types)
6. [Routing Logic](#routing-logic)
7. [Error Reference](#error-reference)
8. [Integration Examples](#integration-examples)
   - [cURL](#curl)
   - [Python (requests)](#python-requests)
   - [JavaScript / Node.js (fetch)](#javascript--nodejs-fetch)
   - [PHP (cURL)](#php-curl)
   - [Postman](#postman)
   - [n8n (Workflow Automation)](#n8n-workflow-automation)
9. [CORS Policy](#cors-policy)
10. [Running the Server](#running-the-server)
11. [Project Structure](#project-structure)

---

## Overview

**DahanaChatbot SuperBrain** is an AI-powered question-answering API for **PT DAHANA (Persero)**.

When you send a question via `POST /chat`, the API automatically:
1. **Classifies the intent** using an LLM (Groq / LLaMA)
2. **Routes** the question to the most appropriate data source:
   - 🗄️ **DATABASE** — queries the company PostgreSQL database (employee, attendance, production data, etc.)
   - 🌐 **WEB** — searches Google via SerpAPI for general or public information
   - 🤖 **RAG** — answers directly from the AI persona (greetings, chatbot identity, general Dahana profile)
3. **Returns** a natural-language answer in Bahasa Indonesia (or English)

> This API is designed to be integrated with third-party platforms such as chatbot builders, automation tools, mobile apps, ERPs, and more. The only endpoint you need for chat integration is **`POST /chat`**.

---

## Base URL & Interactive Docs

| Environment | Base URL |
|---|---|
| **Local (development)** | `http://localhost:8000` |
| **Server / Production** | `http://<your-server-ip>:8000` |

| Documentation UI | URL |
|---|---|
| Swagger UI (interactive) | `http://localhost:8000/docs` |
| ReDoc (readable) | `http://localhost:8000/redoc` |

---

## Authentication

The API supports **optional API key authentication** via a custom HTTP header.

| Header | Value | Required |
|---|---|---|
| `X-API-Key` | Your API key string | ✅ If `API_KEY` is set in `.env` |

- If the server's `API_KEY` environment variable is **empty or not set**, authentication is **disabled** and all requests are accepted.
- If `API_KEY` is configured (e.g. `abc123rahasia`), every request **must** include the `X-API-Key` header.
- A missing or wrong key returns **HTTP 401 Unauthorized**.

**Example with API key:**
```http
POST /chat HTTP/1.1
Host: localhost:8000
Content-Type: application/json
X-API-Key: abc123rahasia

{
  "question": "siapakah Abdul Latip?"
}
```

---

## Endpoints

---

### `GET /` — Health Check

Verify the server is running.

**Request:**
```http
GET / HTTP/1.1
Host: localhost:8000
```

**Response `200 OK`:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `GET /health` — Health Check (Alias)

Same as `GET /`. Use whichever you prefer for monitoring.

**Response `200 OK`:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `POST /chat` — Ask a Question

> ⚡ **This is the main integration endpoint.**

Send a natural-language question and receive an AI-generated answer.

#### Request

**URL:** `POST /chat`  
**Content-Type:** `application/json`

**Request Body:**

| Field | Type | Required | Min | Max | Description |
|---|---|---|---|---|---|
| `question` | `string` | ✅ Yes | 1 char | 1000 chars | The question to ask (Bahasa Indonesia or English) |

**Example Request Body:**
```json
{
  "question": "siapakah Abdul Latip?"
}
```

---

#### Response

**Status:** `200 OK`  
**Content-Type:** `application/json`

| Field | Type | Always Present | Description |
|---|---|---|---|
| `answer` | `string` | ✅ | Natural-language answer from the chatbot |
| `source` | `string` | ✅ | Data source used: `"DATABASE"`, `"WEB"`, `"RAG"`, or `"AI_KNOWLEDGE"` |
| `sql_query` | `string \| null` | ✅ | SQL query executed — only filled when `source = "DATABASE"` |
| `urls` | `string[]` | ✅ | Reference URLs — only filled when `source = "WEB"` |

---

#### Example Responses

**✅ Example 1 — Answer from Database (employee query)**
```json
{
  "answer": "Jawaban Non-Analisis: Abdul Latip, ST adalah Senior Manajer Pelayanan Korporasi di Departemen Sekretariat Perusahaan PT DAHANA (Persero). Beliau lahir pada 6 Maret 1979 dan telah bergabung dengan perusahaan sejak lama.\n\nSumber: (tabel karyawan_hcmis)",
  "source": "DATABASE",
  "sql_query": "SELECT * FROM karyawan_hcmis WHERE ckey ILIKE '%Abdul Latip%' LIMIT 50",
  "urls": []
}
```

**✅ Example 2 — Answer from Web Search**
```json
{
  "answer": "Jawaban Web: PT Dahana adalah Badan Usaha Milik Negara (BUMN) Indonesia yang bergerak di bidang industri bahan berenergi tinggi (handak) dan solusi pertahanan. Perusahaan ini berdiri sejak tahun 1966 dan berlokasi di Subang, Jawa Barat.\n\nSumber: [https://www.dahana.com/about, https://id.wikipedia.org/wiki/Dahana]",
  "source": "WEB",
  "sql_query": null,
  "urls": [
    "https://www.dahana.com/about",
    "https://id.wikipedia.org/wiki/Dahana"
  ]
}
```

**✅ Example 3 — Answer from AI Persona (RAG — greeting / chatbot identity)**
```json
{
  "answer": "Halo! Saya DahanaBot SuperBrain, asisten AI cerdas milik PT DAHANA (Persero). Saya siap membantu Anda menjawab pertanyaan seputar data karyawan, absensi, produksi, dan informasi umum tentang PT Dahana. Ada yang bisa saya bantu?",
  "source": "RAG",
  "sql_query": null,
  "urls": []
}
```

**✅ Example 4 — AI Fallback (Database returned empty result)**
```json
{
  "answer": "Jawaban AI: Maaf, data yang Anda cari tidak tersedia di database internal PT Dahana saat ini. Berdasarkan pengetahuan umum saya, ...",
  "source": "AI_KNOWLEDGE",
  "sql_query": "SELECT * FROM karyawan_hcmis WHERE ckey ILIKE '%John Doe%' LIMIT 50",
  "urls": []
}
```

---

## Response Source Types

| `source` Value | Meaning | `sql_query` | `urls` |
|---|---|---|---|
| `DATABASE` | Answer from company PostgreSQL database | Filled | `[]` |
| `WEB` | Answer from Google search (SerpAPI) | `null` | Filled |
| `RAG` | Answer from AI persona (Dahana profile / greetings) | `null` | `[]` |
| `AI_KNOWLEDGE` | Database query ran but returned no data; AI answered from general knowledge | May be filled | `[]` |

---

## Routing Logic

```
POST /chat  →  { "question": "..." }
                        │
                        ▼
          ┌─────────────────────────┐
          │  Intent Classifier LLM  │
          └─────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
        RAG          DATABASE       GENERAL
          │             │             │
   AI Persona      Generate SQL   SerpAPI Search
   answers         Run on DB      Extract results
   directly        │                  │
                   ▼                  ▼
            Data found?          LLM composes
            YES → Analyse         web answer
            NO  → AI fallback         │
                   │              source = "WEB"
                   ▼
            source = "DATABASE"
            or "AI_KNOWLEDGE"
```

**Intent categories:**

| Intent | Description | Example Questions |
|---|---|---|
| `RAG` | Greetings, chatbot identity, general PT Dahana profile | `"halo"`, `"siapa kamu"`, `"apa itu PT Dahana"` |
| `DATABASE` | Requires internal data (employee, attendance, production) | `"siapakah Abdul Latip?"`, `"berapa karyawan hadir minggu ini?"` |
| `GENERAL` | General knowledge not related to internal data | `"apa itu machine learning"`, `"siapa presiden Indonesia"` |

---

## Error Reference

| HTTP Status | Error | Cause | Solution |
|---|---|---|---|
| `200 OK` | — | Success | — |
| `401 Unauthorized` | `"Invalid or missing API key"` | `X-API-Key` header missing or wrong | Include the correct `X-API-Key` header |
| `422 Unprocessable Entity` | Validation error | `question` field missing, empty, or exceeds 1000 chars | Check the request body format |
| `500 Internal Server Error` | Internal error | LLM API failure, database error, or SerpAPI issue | Check server logs |

**Example 401 Response:**
```json
{
  "detail": "Invalid or missing API key"
}
```

**Example 422 Response:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "question"],
      "msg": "Field required"
    }
  ]
}
```

---

## Integration Examples

### cURL

**Basic request (no API key):**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "siapakah Abdul Latip?"}'
```

**With API key:**
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: abc123rahasia" \
  -d '{"question": "berapa total produksi bulan ini?"}'
```

**Health check:**
```bash
curl http://localhost:8000/health
```

---

### Python (requests)

```python
import requests

BASE_URL = "http://localhost:8000"
API_KEY = "abc123rahasia"  # Set to "" if no key is configured

def ask_chatbot(question: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }
    payload = {"question": question}

    response = requests.post(f"{BASE_URL}/chat", json=payload, headers=headers)
    response.raise_for_status()  # Raises HTTPError on 4xx/5xx
    return response.json()


# Example usage
result = ask_chatbot("siapakah Abdul Latip?")
print("Answer :", result["answer"])
print("Source :", result["source"])
print("SQL    :", result.get("sql_query"))
print("URLs   :", result.get("urls"))
```

---

### JavaScript / Node.js (fetch)

**Browser or Node.js 18+:**
```javascript
const BASE_URL = "http://localhost:8000";
const API_KEY = "abc123rahasia"; // Set to "" if no key configured

async function askChatbot(question) {
  const response = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: JSON.stringify({ question }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(`API Error ${response.status}: ${JSON.stringify(error)}`);
  }

  return await response.json();
}

// Example usage
askChatbot("berapa karyawan yang hadir hari ini?")
  .then((data) => {
    console.log("Answer:", data.answer);
    console.log("Source:", data.source);
  })
  .catch(console.error);
```

**Node.js with axios:**
```javascript
const axios = require("axios");

const client = axios.create({
  baseURL: "http://localhost:8000",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": "abc123rahasia",
  },
});

async function askChatbot(question) {
  const { data } = await client.post("/chat", { question });
  return data;
}

askChatbot("apa itu PT Dahana?").then(console.log);
```

---

### PHP (cURL)

```php
<?php

function askChatbot(string $question, string $apiKey = ""): array {
    $ch = curl_init("http://localhost:8000/chat");

    $headers = ["Content-Type: application/json"];
    if ($apiKey) {
        $headers[] = "X-API-Key: " . $apiKey;
    }

    curl_setopt_array($ch, [
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => json_encode(["question" => $question]),
        CURLOPT_HTTPHEADER     => $headers,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 60,
    ]);

    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($httpCode !== 200) {
        throw new RuntimeException("API Error HTTP $httpCode: $response");
    }

    return json_decode($response, true);
}

// Example usage
$result = askChatbot("siapakah Abdul Latip?", "abc123rahasia");
echo "Answer: " . $result["answer"] . PHP_EOL;
echo "Source: " . $result["source"] . PHP_EOL;
```

---

### Postman

1. Open Postman and create a new **POST** request
2. Set the URL to: `http://localhost:8000/chat`
3. Go to **Headers** tab, add:
   - Key: `Content-Type` → Value: `application/json`
   - Key: `X-API-Key` → Value: `abc123rahasia` *(skip if no API key set)*
4. Go to **Body** tab → select **raw** → select **JSON**
5. Enter:
   ```json
   {
     "question": "siapakah Abdul Latip?"
   }
   ```
6. Click **Send**

---

### n8n (Workflow Automation)

Use the **HTTP Request** node in n8n:

| Setting | Value |
|---|---|
| Method | `POST` |
| URL | `http://localhost:8000/chat` |
| Authentication | None *(or Header Auth with `X-API-Key`)* |
| Body Content Type | `JSON` |
| Body Parameters | `question` = `{{ $json.userMessage }}` (or hardcoded text) |

**To read the response in n8n:**
- `{{ $json.answer }}` → the chatbot's answer text
- `{{ $json.source }}` → `DATABASE`, `WEB`, `RAG`, or `AI_KNOWLEDGE`
- `{{ $json.urls }}` → array of URLs (when source is WEB)

---

## CORS Policy

The API is currently configured to **allow all origins**:

```python
allow_origins=["*"]
allow_methods=["*"]
allow_headers=["*"]
```

> [!IMPORTANT]
> **For production deployments**, restrict `allow_origins` in `api.py` to only your specific platform domain(s). Example:
> ```python
> allow_origins=["https://your-platform.com", "https://app.your-platform.com"]
> ```

---

## Running the Server

### Prerequisites

Install dependencies:
```bash
pip install -r requirements.txt
```

### Environment Variables (`.env`)

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
SERP_API_KEY=your_serpapi_key_here
database_url=postgresql://user:password@host:5432/dbname
API_KEY=your_secret_api_key_here   # Optional. Leave empty to disable auth.
```

### Start the API Server

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

The server starts at `http://localhost:8000`.

### Run Alongside Streamlit UI

Both can run simultaneously on separate ports:

| Service | Command | Default Port |
|---|---|---|
| FastAPI REST API | `uvicorn api:app --host 0.0.0.0 --port 8000 --reload` | 8000 |
| Streamlit UI | `streamlit run app.py` | 8501 |

---

## Project Structure

```
PoC_Dahanalyzer/
├── api.py                  ← FastAPI REST server (this API)
├── app.py                  ← Streamlit web UI (separate, optional)
├── chatbot_core.py         ← Core AI logic shared by api.py and app.py
├── .env                    ← Secret keys and DB connection string
├── requirements.txt        ← Python dependencies
└── API_DOCUMENTATION.md   ← This file
```

> [!NOTE]
> `chatbot_core.py` is the shared brain. Both the REST API (`api.py`) and the Streamlit UI (`app.py`) import and call the same `core.ask()` function, ensuring consistent behavior across all interfaces.

---

## Quick Reference Card

```
┌──────────────────────────────────────────────────────────┐
│              DahanaChatbot API – Quick Reference         │
├──────────────────┬───────────────────────────────────────┤
│ Base URL         │ http://localhost:8000                 │
│ Main Endpoint    │ POST /chat                            │
│ Content-Type     │ application/json                      │
│ Auth Header      │ X-API-Key: <your-key>                 │
│ Request Body     │ { "question": "your question here" }  │
│ Response Fields  │ answer, source, sql_query, urls       │
│ Swagger Docs     │ http://localhost:8000/docs            │
└──────────────────┴───────────────────────────────────────┘
```
