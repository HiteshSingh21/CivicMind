"""
CivicMind -- API Models
========================
Pydantic schemas for request/response models.
"""

from pydantic import BaseModel, Field
from typing import Optional, Any


class AnalyzeRequest(BaseModel):
    query: str = Field(..., description="Natural language question or description")
    latitude: Optional[float] = Field(None, description="GPS latitude for photo submissions")
    longitude: Optional[float] = Field(None, description="GPS longitude for photo submissions")


class ApproveActionRequest(BaseModel):
    action_id: str = Field(..., description="ID of the action to approve")


class RejectActionRequest(BaseModel):
    action_id: str = Field(..., description="ID of the action to reject")
    reason: str = Field("", description="Reason for rejection")


class SSEEvent(BaseModel):
    event: str  # routing, thinking, data, action, error, complete
    data: Any


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    agents: list[str] = [
        "supervisor",
        "data_agent",
        "rag_agent",
        "forecasting_agent",
        "multimodal_agent",
        "action_agent",
    ]
