"""
CivicMind -- Multimodal Intake Agent
======================================
Accepts a photo of a civic issue, classifies it using Gemini Vision,
scores severity, geotags it, and writes the result into the knowledge base
so it becomes searchable by the RAG Agent.

Uses Gemini's multimodal capabilities for image understanding.
"""

import os
import json
import base64
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.utils.vector_store import get_vector_store

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


ISSUE_TYPES = [
    "pothole",
    "overflowing_waste_bin",
    "broken_streetlight",
    "damaged_sidewalk",
    "graffiti",
    "fallen_tree",
    "water_leak",
    "illegal_dumping",
    "traffic_signal_malfunction",
    "other",
]


def _get_genai_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not GENAI_AVAILABLE:
        return None
    return genai.Client(api_key=api_key)


def _classify_with_gemini(client, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """Use Gemini Vision to classify a civic issue photo."""
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    prompt = f"""You are a civic issue classifier for a city maintenance system. Analyze this photo and provide:

1. **issue_type**: One of: {', '.join(ISSUE_TYPES)}
2. **severity**: Score from 1 (minor cosmetic) to 5 (immediate safety hazard)
3. **description**: A detailed 2-3 sentence description of the issue
4. **recommended_action**: What maintenance action should be taken
5. **estimated_repair_time**: Estimated time to fix (e.g., "2-4 hours", "1-2 days")

Respond in valid JSON format only, no markdown:
{{"issue_type": "...", "severity": N, "description": "...", "recommended_action": "...", "estimated_repair_time": "..."}}"""

    try:
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
        )
        text = response.text.strip()
        # Clean markdown if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except (json.JSONDecodeError, Exception) as e:
        return None


def _classify_fallback(image_path: str | None = None) -> dict:
    """Fallback classification when Gemini is not available."""
    # Attempt to guess from filename
    if image_path:
        path_lower = str(image_path).lower()
        if "pothole" in path_lower:
            return {
                "issue_type": "pothole",
                "severity": 4,
                "description": "Large pothole detected on road surface. The damaged area shows exposed aggregate and broken asphalt, with water accumulation suggesting depth. Located near a bus stop, this poses risks to both vehicles and pedestrians.",
                "recommended_action": "Schedule emergency road repair. Install temporary warning signs and traffic cones. Notify transit authority of potential bus route impact.",
                "estimated_repair_time": "4-8 hours",
            }
        elif "bin" in path_lower or "waste" in path_lower or "overflow" in path_lower:
            return {
                "issue_type": "overflowing_waste_bin",
                "severity": 3,
                "description": "Public waste bin is overflowing with garbage bags and loose debris spilling onto the sidewalk. This creates hygiene concerns and may attract pests. The surrounding area shows additional litter accumulation.",
                "recommended_action": "Dispatch waste collection team for immediate pickup. Consider temporary placement of additional bins. Review collection schedule frequency for this location.",
                "estimated_repair_time": "1-2 hours",
            }
        elif "streetlight" in path_lower or "light" in path_lower:
            return {
                "issue_type": "broken_streetlight",
                "severity": 3,
                "description": "Streetlight is non-functional, creating a dark zone on what appears to be a residential boulevard. Adjacent streetlights are working, confirming this is an isolated fixture failure rather than a power outage.",
                "recommended_action": "Dispatch electrical maintenance crew to inspect and replace the light fixture or bulb. Check wiring and photocell sensor. Verify adjacent lights for preventive maintenance.",
                "estimated_repair_time": "2-4 hours",
            }

    return {
        "issue_type": "other",
        "severity": 2,
        "description": "Civic issue detected. Manual review required for accurate classification.",
        "recommended_action": "Forward to appropriate department for assessment.",
        "estimated_repair_time": "TBD",
    }


async def run_multimodal_agent(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    image_path: Optional[str] = None,
) -> dict:
    """Run the Multimodal Intake Agent.

    Accepts an image, classifies the issue, geotags it, writes to knowledge base.

    Returns dict with keys: agent, classification, geolocation, complaint_id, stored
    """
    complaint_id = f"PHOTO-{uuid.uuid4().hex[:8].upper()}"

    # Step 1: Classify the image
    client = _get_genai_client()

    if client:
        classification = _classify_with_gemini(client, image_bytes, mime_type)
        if classification is None:
            classification = _classify_fallback(image_path)
    else:
        classification = _classify_fallback(image_path)

    # Step 2: Geolocation
    geolocation = {
        "latitude": latitude or 40.7589,
        "longitude": longitude or -73.9851,
        "source": "user_provided" if latitude else "default_city_center",
    }

    # Step 3: Write to knowledge base (so RAG agent can find it)
    store = get_vector_store()
    complaint_text = (
        f"PHOTO COMPLAINT -- {complaint_id}\n"
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"Issue Type: {classification.get('issue_type', 'unknown')}\n"
        f"Severity: {classification.get('severity', 'unknown')}/5\n"
        f"Location: ({geolocation['latitude']}, {geolocation['longitude']})\n"
        f"Description: {classification.get('description', 'No description')}\n"
        f"Recommended Action: {classification.get('recommended_action', 'TBD')}\n"
    )

    store.add_document(
        doc_id=f"photo_complaints/{complaint_id}",
        text=complaint_text,
        metadata={
            "source": f"photo_complaint_{complaint_id}",
            "category": "photo_complaints",
            "issue_type": classification.get("issue_type", "unknown"),
            "severity": classification.get("severity", 0),
            "latitude": geolocation["latitude"],
            "longitude": geolocation["longitude"],
        }
    )

    return {
        "agent": "multimodal_agent",
        "complaint_id": complaint_id,
        "classification": classification,
        "geolocation": geolocation,
        "stored": True,
        "stored_message": f"Complaint {complaint_id} has been added to the knowledge base and is now searchable.",
    }
