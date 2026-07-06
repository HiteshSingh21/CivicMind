# CivicMind

> *"CivicMind doesn't just answer questions about your city — it watches, predicts, explains, and acts."*

CivicMind is a hackathon-winning, multi-agent civic intelligence platform. It moves beyond standard Q&A chatbots by ingesting structured data, unstructured documents, and photo evidence to generate data-backed answers, forecast trends, and autonomously draft actionable work orders with human-in-the-loop approval.

---

## 🏗️ Architecture

CivicMind uses a **Supervisor-Specialist Multi-Agent Architecture** inspired by the Google Agent Development Kit (ADK). 

### The Agents
1. **Supervisor Agent**: The orchestrator. Uses Gemini 2.0 to classify user intent in real-time and routes the query to the correct specialist.
2. **Data Agent (NL-to-SQL)**: Queries structured civic databases (e.g., complaint counts, neighborhood stats, AQI). *Local fallback: SQLite (Swap-in ready for BigQuery).*
3. **RAG Agent (Grounded Search)**: Searches through unstructured citizen reports and meeting minutes to answer qualitative questions. *Local fallback: ChromaDB (Swap-in ready for Vertex AI Search).*
4. **Forecasting Agent (Predictive)**: Analyzes historical time-series data to predict future trends with 95% confidence bands. *Local fallback: `statsmodels` (Swap-in ready for BigQuery ML).*
5. **Vision Agent (Multimodal)**: Analyzes uploaded photos (e.g., potholes, overflowing bins) using Gemini Vision to classify issues, estimate repair times, and assign severity.
6. **Action Agent (Automation)**: A human-in-the-loop agent that drafts automated work orders for the Department of Transportation or Sanitation based on agent findings, awaiting human approval before dispatch.

### The Stack
* **Backend**: FastAPI (Python) with a robust Server-Sent Events (SSE) streaming layer.
* **Frontend**: Premium, dependency-free Vanilla HTML/JS/CSS Single Page Application (SPA). Features dynamic layout routing, glassmorphism, native Canvas charting, and micro-animations.
* **LLM**: Google Gemini 2.0 Flash.

---

## 🚀 Features

* **Graceful Degradation**: If an agent fails (e.g., hallucinated SQL), the SSE stream emits a recoverable error, showing a clean fallback UI rather than crashing the application.
* **Responsible AI Implementation**:
  * Visual **Source Citations** for all RAG and Data answers.
  * **PII Redaction** on all unstructured documents.
  * Explicit **Human Approval Gates** for the Action Agent.
  * **Confidence Bands** displayed on all predictive charts.

---

## 💻 Getting Started (Local Development)

### Prerequisites
* Python 3.12+
* Google Gemini API Key

### Installation

1. **Clone and setup the environment:**
   ```bash
   git clone <your-repo>
   cd CivicMind
   python -m venv .venv
   
   # Windows:
   .\.venv\Scripts\activate
   
   # Mac/Linux:
   source .venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment:**
   Copy the example environment file and add your Google API key:
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` and paste your API key.*

4. **Generate Synthetic Data:**
   Run the master seed script to generate the synthetic SQLite database, ChromaDB vector embeddings, and sample photos.
   ```bash
   python data/seed.py
   ```

5. **Run the Server:**
   ```bash
   python -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
   ```

6. **View the App:**
   Open `http://localhost:8080` in your web browser.

---

## ☁️ Deployment (Google Cloud Run)

A `Dockerfile` and `docker-compose.yml` are included for easy containerization.

```bash
# 1. Build the image via Google Cloud Build
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/civicmind

# 2. Deploy to Cloud Run
gcloud run deploy civicmind \
  --image gcr.io/YOUR_PROJECT_ID/civicmind \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_API_KEY=your_key_here"
```

---
*Built for the 2026 AI Hackathon.*
