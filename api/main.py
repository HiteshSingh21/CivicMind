"""
CivicMind -- FastAPI Application
=================================
Main API server. Single /api/analyze endpoint with SSE streaming,
plus action approval and health endpoints.

Serves the frontend as static files from the /frontend directory.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from api.stream_handler import stream_analysis
from agents.action_agent import approve_action, reject_action
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = PROJECT_ROOT / "data" / "structured" / "civic_records.db"
    chroma_dir = PROJECT_ROOT / "data" / "chromadb"
    
    if not db_path.exists() or not chroma_dir.exists():
        print("[Startup] Persistent storage missing. Running seed script...")
        try:
            from data.seed import main as seed_main
            seed_main()
            
            # Initialize vector store to build indices
            from agents.utils.vector_store import get_vector_store
            get_vector_store()
            print("[Startup] Seeding and vector indexing complete.")
        except Exception as e:
            print(f"[Startup] Error during seeding: {e}")
            
    yield


app = FastAPI(
    title="CivicMind",
    description="Multi-Agent Civic Intelligence Platform -- watches, predicts, explains, and acts.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Endpoints ----

@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "platform": "CivicMind -- Multi-Agent Civic Intelligence",
        "agents": [
            "Supervisor Agent",
            "Data Agent (NL-to-SQL)",
            "RAG Agent (Grounded Search)",
            "Forecasting Agent (Time Series)",
            "Multimodal Intake Agent (Gemini Vision)",
            "Action/Automation Agent (Human-in-the-Loop)",
        ],
        "google_stack": [
            "Google Agent Development Kit (ADK)",
            "Gemini 2.0 Flash",
            "Local SQLite (BigQuery swap-in ready)",
            "Local ChromaDB (Vertex AI Search swap-in ready)",
            "Local statsmodels (BigQuery ML swap-in ready)",
        ],
    }


@app.get("/api/demo-queries")
async def demo_queries():
    """Return the 4 scripted demo queries for the UI."""
    return {
        "queries": [
            {
                "id": "demo-1",
                "label": "Respiratory Complaints",
                "query": "Which neighborhoods had the highest respiratory complaint spike last month?",
                "agent": "data_agent",
                "icon": "database",
                "description": "Structured data query",
            },
            {
                "id": "demo-2",
                "label": "Bus Route 14 Feedback",
                "query": "What have citizens said about bus route 14 reliability?",
                "agent": "rag_agent",
                "icon": "search",
                "description": "Unstructured document search",
            },
            {
                "id": "demo-3",
                "label": "Complaint Forecast",
                "query": "Will respiratory complaints in Riverside keep rising next month?",
                "agent": "forecasting_agent",
                "icon": "trending_up",
                "description": "Predictive analysis",
            },
            {
                "id": "demo-4",
                "label": "Report a Pothole",
                "query": "Analyze this civic issue and create a work order",
                "agent": "multimodal_agent",
                "icon": "camera",
                "description": "Photo analysis + action",
                "requires_image": True,
                "sample_image": "/data/photos/pothole_01.jpg",
            },
        ]
    }


@app.post("/api/analyze")
async def analyze(request: Request):
    """Main analysis endpoint with SSE streaming.

    Accepts either JSON body or multipart form data (for image uploads).
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        query = form.get("query", "Analyze this civic issue")
        image_file = form.get("image")
        latitude = form.get("latitude")
        longitude = form.get("longitude")

        image_bytes = None
        image_mime = "image/jpeg"
        image_path = None

        if image_file and hasattr(image_file, "read"):
            image_bytes = await image_file.read()
            image_mime = getattr(image_file, "content_type", "image/jpeg") or "image/jpeg"
            image_path = getattr(image_file, "filename", None)

        lat = float(latitude) if latitude else None
        lon = float(longitude) if longitude else None

        async def event_generator():
            async for event in stream_analysis(
                question=str(query),
                image_bytes=image_bytes,
                image_mime_type=image_mime,
                image_path=image_path,
                latitude=lat,
                longitude=lon,
            ):
                if await request.is_disconnected():
                    break
                yield event

        return EventSourceResponse(event_generator())

    else:
        body = await request.json()
        query = body.get("query", "")

        if not query:
            return JSONResponse(
                status_code=400,
                content={"error": "Query is required"},
            )

        async def event_generator():
            async for event in stream_analysis(question=query):
                if await request.is_disconnected():
                    break
                yield event

        return EventSourceResponse(event_generator())


@app.post("/api/approve-action")
async def approve(request: Request):
    """Approve a pending action for dispatch."""
    body = await request.json()
    action_id = body.get("action_id", "")

    if not action_id:
        return JSONResponse(
            status_code=400,
            content={"error": "action_id is required"},
        )

    result = await approve_action(action_id)
    return JSONResponse(content=result)


@app.post("/api/reject-action")
async def reject(request: Request):
    """Reject a pending action."""
    body = await request.json()
    action_id = body.get("action_id", "")
    reason = body.get("reason", "")

    result = await reject_action(action_id, reason)
    return JSONResponse(content=result)


# ---- Static Files (Frontend) ----

FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"

if FRONTEND_DIR.exists():
    # Serve data files (for demo photo access)
    if DATA_DIR.exists():
        app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

    # Serve frontend static files
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("api.main:app", host=host, port=port, reload=True)
