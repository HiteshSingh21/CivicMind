"""
CivicMind -- Action/Automation Agent
======================================
The loop-closer. Drafts concrete actions (work orders, notifications, alerts)
based on classified issues or analytical findings.

CRITICAL: Never auto-dispatches. Always returns a draft requiring human approval.
The human-approval checkpoint is a deliberate responsible-AI design choice.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Optional

try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


# In-memory action store (in production, this would be a database)
_pending_actions: dict[str, dict] = {}
_dispatched_actions: dict[str, dict] = {}


def _get_genai_client():
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not GENAI_AVAILABLE:
        return None
    return genai.Client(api_key=api_key)


def _draft_work_order(issue_data: dict) -> dict:
    """Draft a maintenance work order from a classified issue."""
    issue_type = issue_data.get("issue_type", "unknown")
    severity = issue_data.get("severity", 3)
    description = issue_data.get("description", "No description provided")
    recommended_action = issue_data.get("recommended_action", "Inspect and assess")
    location = issue_data.get("geolocation", {})
    complaint_id = issue_data.get("complaint_id", "N/A")

    priority_map = {5: "CRITICAL", 4: "HIGH", 3: "MEDIUM", 2: "LOW", 1: "ROUTINE"}
    priority = priority_map.get(severity, "MEDIUM")

    # Department routing
    dept_map = {
        "pothole": "Department of Public Works - Roads Division",
        "overflowing_waste_bin": "Sanitation Department",
        "broken_streetlight": "Department of Public Works - Electrical Division",
        "damaged_sidewalk": "Department of Public Works - Roads Division",
        "water_leak": "Water & Sewer Department",
        "fallen_tree": "Parks & Recreation Department",
        "traffic_signal_malfunction": "Traffic Engineering Department",
    }
    department = dept_map.get(issue_type, "Department of Public Works - General")

    return {
        "action_type": "work_order",
        "title": f"Work Order: {issue_type.replace('_', ' ').title()} Repair",
        "priority": priority,
        "department": department,
        "description": description,
        "recommended_action": recommended_action,
        "location": f"({location.get('latitude', 'N/A')}, {location.get('longitude', 'N/A')})",
        "estimated_repair_time": issue_data.get("estimated_repair_time", "TBD"),
        "reference": complaint_id,
    }


def _draft_notification(finding: dict) -> dict:
    """Draft a department notification from an analytical finding."""
    return {
        "action_type": "department_notification",
        "title": f"Alert: {finding.get('title', 'Civic Intelligence Finding')}",
        "priority": finding.get("priority", "MEDIUM"),
        "department": finding.get("department", "City Manager's Office"),
        "message": finding.get("message", "Review required for recent civic intelligence finding."),
        "data_summary": finding.get("data_summary", ""),
        "recommended_response": finding.get("recommended_response", "Review and assess"),
    }


def _draft_resident_update(update_data: dict) -> dict:
    """Draft a resident notification (SMS/email template)."""
    return {
        "action_type": "resident_update",
        "title": "Resident Update Notification",
        "channel": update_data.get("channel", "email"),
        "subject": update_data.get("subject", "Update on Your Civic Report"),
        "message": update_data.get("message", "Your report has been received and is being processed."),
        "affected_area": update_data.get("area", "City-wide"),
    }


async def run_action_agent(context: dict) -> dict:
    """Run the Action Agent: draft an action based on the provided context.

    The context should come from another agent's output (e.g., multimodal classification,
    forecasting alert, or data analysis finding).

    IMPORTANT: Returns requires_approval=True. The action is NEVER auto-dispatched.
    This is a deliberate responsible-AI design choice.

    Returns dict with keys: agent, action_id, action, requires_approval, approval_message
    """
    action_id = f"ACT-{uuid.uuid4().hex[:8].upper()}"

    # Determine action type from context
    if "classification" in context:
        # From multimodal agent — draft work order
        action_data = context.get("classification", {})
        action_data["geolocation"] = context.get("geolocation", {})
        action_data["complaint_id"] = context.get("complaint_id", "N/A")
        action = _draft_work_order(action_data)

    elif "forecast" in context:
        # From forecasting agent — draft alert notification
        metric = context.get("metric", "Unknown Metric")
        summary = context.get("summary", "")
        action = _draft_notification({
            "title": f"Forecast Alert: {metric}",
            "priority": "HIGH",
            "department": "City Manager's Office",
            "message": f"Forecasting analysis has identified a significant trend requiring attention.\n\n{summary}",
            "data_summary": summary,
            "recommended_response": "Review forecast data and convene relevant department heads.",
        })

    elif "results" in context:
        # From data agent — draft based on data findings
        summary = context.get("summary", "")
        action = _draft_notification({
            "title": "Data Analysis Finding",
            "priority": "MEDIUM",
            "department": "City Manager's Office",
            "message": f"Structured data analysis has produced a finding requiring review.\n\n{summary}",
            "data_summary": summary,
            "recommended_response": "Review data and determine if intervention is needed.",
        })

    else:
        # Generic action
        action = _draft_notification({
            "title": "Civic Intelligence Alert",
            "priority": "MEDIUM",
            "department": "City Manager's Office",
            "message": "A civic intelligence finding requires your attention.",
            "recommended_response": "Review and assess.",
        })

    # Enhance with Gemini if available
    client = _get_genai_client()
    if client and action["action_type"] == "work_order":
        try:
            model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
            resp = client.models.generate_content(
                model=model,
                contents=f"""Write a professional, concise work order description for a city maintenance team.

Issue: {action['title']}
Priority: {action['priority']}
Department: {action['department']}
Details: {action['description']}
Recommended Action: {action['recommended_action']}

Write 3-4 sentences that a field crew would understand. Include safety notes if priority is HIGH or CRITICAL.""",
            )
            action["enhanced_description"] = resp.text.strip()
        except Exception:
            pass

    # Store as pending (not dispatched!)
    _pending_actions[action_id] = {
        "action_id": action_id,
        "action": action,
        "created_at": datetime.now().isoformat(),
        "status": "pending_approval",
        "context_summary": context.get("summary", context.get("classification", {}).get("description", "")),
    }

    return {
        "agent": "action_agent",
        "action_id": action_id,
        "action": action,
        "requires_approval": True,
        "approval_message": (
            "This action requires human approval before dispatch. "
            "This is a deliberate responsible-AI design choice -- CivicMind never "
            "takes autonomous action without human oversight."
        ),
        "status": "pending_approval",
    }


async def approve_action(action_id: str) -> dict:
    """Approve and 'dispatch' a pending action.

    In production, this would integrate with a ticketing system, SMS gateway, etc.
    For the demo, it logs the dispatch and marks the action as completed.
    """
    if action_id not in _pending_actions:
        return {
            "success": False,
            "error": f"Action {action_id} not found or already processed.",
        }

    action_data = _pending_actions.pop(action_id)
    action_data["status"] = "dispatched"
    action_data["dispatched_at"] = datetime.now().isoformat()
    action_data["dispatched_by"] = "human_operator"

    _dispatched_actions[action_id] = action_data

    # Log dispatch (simulated -- in production this would call external APIs)
    action_type = action_data["action"]["action_type"]
    print(f"[ACTION DISPATCHED] {action_id} | Type: {action_type} | "
          f"Dept: {action_data['action'].get('department', 'N/A')} | "
          f"Time: {action_data['dispatched_at']}")

    return {
        "success": True,
        "action_id": action_id,
        "status": "dispatched",
        "dispatched_at": action_data["dispatched_at"],
        "message": f"Action {action_id} has been approved and dispatched. "
                   f"(Simulated -- in production, this would create a ticket in the city's "
                   f"work order system and notify the {action_data['action'].get('department', 'responsible department')}.)",
        "dispatch_note": "SMS/email dispatch is logged to console, not actually sent.",
    }


async def reject_action(action_id: str, reason: str = "") -> dict:
    """Reject a pending action."""
    if action_id not in _pending_actions:
        return {
            "success": False,
            "error": f"Action {action_id} not found or already processed.",
        }

    action_data = _pending_actions.pop(action_id)
    action_data["status"] = "rejected"
    action_data["rejected_at"] = datetime.now().isoformat()
    action_data["rejection_reason"] = reason

    print(f"[ACTION REJECTED] {action_id} | Reason: {reason or 'No reason given'}")

    return {
        "success": True,
        "action_id": action_id,
        "status": "rejected",
        "message": f"Action {action_id} has been rejected.",
    }
