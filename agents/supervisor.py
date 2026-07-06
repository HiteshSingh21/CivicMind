"""
CivicMind -- Supervisor Agent
===============================
The orchestrator. Classifies user intent and routes to the appropriate
specialist agent(s). Never answers substantively itself.

Built on Google Agent Development Kit (ADK) patterns.
In production, this would use google.adk.agents.llm_agent.Agent with
sub-agents as AgentTools for full ADK integration.
"""

import os
import json
import re
from typing import Optional

from agents.data_agent import run_data_agent
from agents.rag_agent import run_rag_agent
from agents.forecasting_agent import run_forecasting_agent
from agents.multimodal_agent import run_multimodal_agent
from agents.action_agent import run_action_agent

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


INTENT_CATEGORIES = {
    "structured": "Data Agent -- for questions about structured civic data (counts, averages, comparisons, rankings from database tables)",
    "unstructured": "RAG Agent -- for questions about citizen complaints, meeting minutes, news, qualitative information",
    "predictive": "Forecasting Agent -- for predictions, trends, forecasts, 'will X happen', 'what's next'",
    "multimodal": "Multimodal Intake Agent -- for analyzing uploaded photos/images of civic issues",
    "action": "Action Agent -- for generating work orders, notifications, or taking action on findings",
}


def _classify_intent_with_gemini(question: str, has_image: bool = False) -> str:
    """Use Gemini to classify the intent of a query."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not GENAI_AVAILABLE:
        return _classify_intent_heuristic(question, has_image)

    client = genai.Client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    prompt = f"""You are an intent classifier for a civic intelligence system. Classify the following user input into exactly ONE category.

CATEGORIES:
- "structured" = Questions answerable from database tables (counts, stats, rankings, comparisons). Keywords: "which", "how many", "highest", "average", specific neighborhoods or metrics.
- "unstructured" = Questions about citizen opinions, complaints, reports, news, qualitative info. Keywords: "what have citizens said", "complaints about", "reports on", "what do people think".
- "predictive" = Questions about future trends, forecasts, predictions. Keywords: "will", "predict", "forecast", "next month", "keep rising", "trend".
- "multimodal" = The user has uploaded an image/photo for analysis. {"NOTE: An image IS attached to this request." if has_image else "No image attached."}
- "action" = Requests to take action, create work orders, send notifications. Keywords: "create", "send", "dispatch", "draft", "notify".

USER INPUT: "{question}"
{"[An image is attached]" if has_image else ""}

Respond with ONLY the category name (one word), nothing else:"""

    try:
        response = client.models.generate_content(model=model, contents=prompt)
        intent = response.text.strip().lower().replace('"', '').replace("'", "")
        if intent in INTENT_CATEGORIES:
            return intent
    except Exception:
        pass

    return _classify_intent_heuristic(question, has_image)


def _classify_intent_heuristic(question: str, has_image: bool = False) -> str:
    """Rule-based intent classification fallback."""
    if has_image:
        return "multimodal"

    q = question.lower()

    # Predictive signals
    predictive_signals = ["predict", "forecast", "will ", "next month", "next week",
                          "keep rising", "trend", "future", "projection", "expect"]
    if any(s in q for s in predictive_signals):
        return "predictive"

    # Action signals
    action_signals = ["create work order", "send notification", "dispatch", "draft",
                      "notify department", "take action", "generate report"]
    if any(s in q for s in action_signals):
        return "action"

    # Unstructured signals
    unstructured_signals = ["citizens said", "complaints about", "what have", "what do people",
                            "meeting minutes", "news about", "reports on", "opinions",
                            "public sentiment", "residents feel", "community feedback",
                            "reliability"]
    if any(s in q for s in unstructured_signals):
        return "unstructured"

    # Structured signals (default for data questions)
    structured_signals = ["which neighborhood", "how many", "highest", "lowest", "average",
                          "total", "count", "compare", "ranking", "spike", "top", "most",
                          "data", "statistics", "numbers"]
    if any(s in q for s in structured_signals):
        return "structured"

    # Default to structured for specific entity mentions
    if any(word in q for word in ["riverside", "downtown", "route 14", "aqi", "ridership"]):
        return "structured"

    # Default: structured for factual questions, unstructured otherwise
    if "?" in question or any(q.startswith(w) for w in ["what", "how", "where", "when"]):
        return "structured"

    return "unstructured"


async def run_supervisor(
    question: str,
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg",
    image_path: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> dict:
    """Run the Supervisor Agent: classify intent and route to specialists.

    This is the main entry point for the CivicMind system.

    Yields progress events as dicts for SSE streaming:
    - {"event": "routing", ...}
    - {"event": "thinking", ...}
    - {"event": "result", ...}
    - {"event": "action", ...}  (if action agent triggered)
    """
    has_image = image_bytes is not None

    # Step 1: Classify intent
    intent = _classify_intent_with_gemini(question, has_image)

    result = {
        "intent": intent,
        "agent_used": intent,
        "question": question,
    }

    # Step 2: Route to appropriate agent
    if intent == "structured":
        agent_result = await run_data_agent(question)
        result["data"] = agent_result

    elif intent == "unstructured":
        agent_result = await run_rag_agent(question)
        result["data"] = agent_result

    elif intent == "predictive":
        agent_result = await run_forecasting_agent(question)
        result["data"] = agent_result

    elif intent == "multimodal":
        if image_bytes:
            agent_result = await run_multimodal_agent(
                image_bytes=image_bytes,
                mime_type=image_mime_type,
                latitude=latitude,
                longitude=longitude,
                image_path=image_path,
            )
            result["data"] = agent_result

            # Auto-trigger action agent for multimodal results
            action_context = {
                "classification": agent_result.get("classification", {}),
                "geolocation": agent_result.get("geolocation", {}),
                "complaint_id": agent_result.get("complaint_id", ""),
            }
            action_result = await run_action_agent(action_context)
            result["action"] = action_result
        else:
            result["data"] = {
                "agent": "multimodal_agent",
                "error": "No image provided. Please upload a photo of the civic issue.",
            }

    elif intent == "action":
        # Action agent needs context from a previous analysis
        result["data"] = {
            "agent": "action_agent",
            "message": "The Action Agent requires context from a previous analysis. "
                       "Try asking a question first, then request action based on the findings.",
        }

    return result
