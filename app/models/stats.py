"""
Statistics domain models.
"""
from pydantic import BaseModel
from typing import List, Optional, Any, Dict


class StatEvent(BaseModel):
    """Single stat event model."""
    name: str
    data: Optional[Dict[str, Any]] = None
    ts: int  # Unix timestamp


class BatchStatsRequest(BaseModel):
    """Batch stats upload request."""
    device_id: str
    events: List[StatEvent]


class BatchStatsResponse(BaseModel):
    """Batch stats upload response."""
    received: int
    success: bool
