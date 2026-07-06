"""
CivicMind -- SSE Stream Handler
=================================
Wraps agent execution and emits SSE events for real-time UI updates.

CRITICAL DESIGN CHOICE: Graceful error handling.
If any agent fails (e.g., bad NL-to-SQL query, vector store error),
the stream emits an 'error' event that the UI renders as a
"re-calculating" state rather than crashing the whole UI.

Yields dicts with 'event' and 'data' keys for sse-starlette.
"""

import json
import asyncio
import traceback
from typing import AsyncGenerator, Optional


AGENT_DESCRIPTIONS = {
    "structured": {
        "name": "Data Agent",
        "icon": "database",
        "color": "#4FC3F7",
        "description": "Querying structured civic databases...",
    },
    "unstructured": {
        "name": "RAG Agent",
        "icon": "search",
        "color": "#81C784",
        "description": "Searching citizen reports and documents...",
    },
    "predictive": {
        "name": "Forecasting Agent",
        "icon": "trending_up",
        "color": "#FFB74D",
        "description": "Analyzing trends and generating predictions...",
    },
    "multimodal": {
        "name": "Multimodal Intake Agent",
        "icon": "camera",
        "color": "#CE93D8",
        "description": "Analyzing uploaded image...",
    },
    "action": {
        "name": "Action Agent",
        "icon": "gavel",
        "color": "#EF5350",
        "description": "Drafting action for human approval...",
    },
}


def _make_event(event_type: str, data: dict) -> dict:
    """Create an SSE event dict for sse-starlette."""
    return {
        "event": event_type,
        "data": json.dumps(data, default=str),
    }


async def stream_analysis(
    question: str,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    image_path: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> AsyncGenerator[dict, None]:
    """Stream the analysis process as SSE events.

    Yields dicts with 'event' and 'data' keys that sse-starlette serializes.

    Event types:
    - routing: Which agent was selected (with metadata)
    - thinking: Agent processing status update
    - data: Agent results (table, answer, forecast, classification)
    - action: Proposed action requiring human approval
    - error: Recoverable error (UI shows fallback state, not crash)
    - complete: Final assembled response
    """
    from agents.supervisor import run_supervisor, _classify_intent_with_gemini

    has_image = image_bytes is not None

    try:
        # --- Phase 1: Intent Classification ---
        yield _make_event("thinking", {
            "message": "Analyzing your request...",
            "phase": "classification",
        })

        await asyncio.sleep(0.3)

        # Classify intent
        intent = _classify_intent_with_gemini(question, has_image)
        agent_info = AGENT_DESCRIPTIONS.get(intent, AGENT_DESCRIPTIONS["structured"])

        yield _make_event("routing", {
            "intent": intent,
            "agent": agent_info["name"],
            "icon": agent_info["icon"],
            "color": agent_info["color"],
            "message": f"Routing to {agent_info['name']}",
        })

        await asyncio.sleep(0.3)

        yield _make_event("thinking", {
            "message": agent_info["description"],
            "phase": "processing",
            "agent": intent,
        })

        # --- Phase 2: Execute Agent ---
        try:
            result = await run_supervisor(
                question=question,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                image_path=image_path,
                latitude=latitude,
                longitude=longitude,
            )
        except Exception as agent_error:
            # Graceful degradation: emit error event, don't crash the stream
            yield _make_event("error", {
                "message": "The agent encountered an issue and is recalculating...",
                "detail": str(agent_error),
                "recoverable": True,
                "agent": intent,
            })

            await asyncio.sleep(0.5)

            yield _make_event("data", {
                "agent": intent,
                "fallback": True,
                "message": (
                    f"The {agent_info['name']} encountered an error while processing your request. "
                    f"This may be due to a temporary issue. Please try rephrasing your question or try again."
                ),
                "error_type": type(agent_error).__name__,
            })

            yield _make_event("complete", {
                "status": "partial",
                "message": "Analysis completed with fallback results.",
            })
            return

        # --- Phase 3: Emit Results ---
        agent_data = result.get("data", {})

        # Check for agent-level errors (e.g., bad SQL)
        if "error" in agent_data:
            yield _make_event("error", {
                "message": agent_data["error"],
                "recoverable": True,
                "agent": intent,
            })

        yield _make_event("data", agent_data)

        # --- Phase 4: Action (if triggered) ---
        if "action" in result:
            await asyncio.sleep(0.3)

            yield _make_event("thinking", {
                "message": "Drafting action for human approval...",
                "phase": "action",
                "agent": "action",
            })

            await asyncio.sleep(0.3)

            yield _make_event("action", result["action"])

        # --- Phase 5: Complete ---
        await asyncio.sleep(0.2)

        yield _make_event("complete", {
            "status": "success",
            "intent": intent,
            "agent_used": agent_info["name"],
        })

    except Exception as e:
        # Top-level error handler: the stream should NEVER crash silently
        error_detail = traceback.format_exc()
        print(f"[STREAM ERROR] {e}\n{error_detail}")

        yield _make_event("error", {
            "message": "An unexpected error occurred. The system is recovering...",
            "detail": str(e),
            "recoverable": False,
        })

        yield _make_event("complete", {
            "status": "error",
            "message": "Analysis could not be completed. Please try again.",
        })
