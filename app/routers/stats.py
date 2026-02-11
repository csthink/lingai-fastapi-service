"""
Statistics Router
Provides event tracking and statistics API
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from loguru import logger


router = APIRouter()


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


@router.post("/batch", response_model=BatchStatsResponse)
async def upload_batch_stats(request: BatchStatsRequest):
    """
    Upload batch statistics events.
    
    - **device_id**: Device identifier
    - **events**: List of stat events
    
    Events are logged for POC analytics.
    """
    logger.info(f"Received {len(request.events)} events from device {request.device_id}")
    
    # POC: Just log events, no persistent storage yet
    for event in request.events:
        event_time = datetime.fromtimestamp(event.ts)
        logger.debug(f"Event: {event.name} at {event_time} - {event.data}")
    
    return BatchStatsResponse(
        received=len(request.events),
        success=True
    )


@router.get("/summary")
async def get_stats_summary():
    """
    Get statistics summary (for debug page).
    
    POC: Returns placeholder data.
    """
    return {
        "total_sessions": 0,
        "total_lessons_completed": 0,
        "total_words_mastered": 0,
        "total_study_minutes": 0,
        "tts_success_rate": 0.0,
        "deepseek_success_rate": 0.0,
        "message": "POC: Stats not yet persisted"
    }
