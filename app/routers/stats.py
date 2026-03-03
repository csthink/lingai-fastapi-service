"""
Statistics Router
Provides event tracking and statistics API with Redis-backed aggregation.
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from loguru import logger
from app.services.redis_service import get_redis_service

router = APIRouter()

STATS_KEY_PREFIX = "stats:summary:"


def _to_int(v, default=0):
    """Safely convert a value to int."""
    try:
        return int(v)
    except Exception:
        return default


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
    Upload batch statistics events and aggregate into Redis.

    - **device_id**: Device identifier
    - **events**: List of stat events

    Supported event names:
    - `study_minute` / `study_minutes` / `study_time` — increments total_study_minutes
    - `lesson_completed` / `lesson_complete` — increments total_lessons_completed
    - `word_mastered` / `word_learned` — increments total_words_mastered
    - `tts_play` — increments tts counters
    - `deepseek_call` — increments deepseek counters
    """
    logger.info(f"Received {len(request.events)} events from device {request.device_id}")

    redis = get_redis_service()
    if not redis or not redis.available:
        logger.warning("Redis unavailable, stats events dropped")
        return BatchStatsResponse(received=len(request.events), success=True)

    # Aggregate into both per-device and global hashes
    keys = [f"{STATS_KEY_PREFIX}{request.device_id}", f"{STATS_KEY_PREFIX}global"]
    for key in keys:
        await redis.hincrby(key, "total_sessions", 1)

    for event in request.events:
        ts = event.ts / 1000 if event.ts > 1_000_000_000_000 else event.ts
        event_time = datetime.fromtimestamp(ts)
        logger.debug(f"Event: {event.name} at {event_time} - {event.data}")

        data = event.data or {}
        for key in keys:
            if event.name in ("study_minute", "study_minutes", "study_time"):
                await redis.hincrby(key, "total_study_minutes", _to_int(data.get("minutes", 0)))
            elif event.name in ("lesson_completed", "lesson_complete"):
                await redis.hincrby(key, "total_lessons_completed", _to_int(data.get("count", 1)))
            elif event.name in ("word_mastered", "word_learned"):
                await redis.hincrby(key, "total_words_mastered", _to_int(data.get("count", 1)))
            elif event.name == "tts_play":
                await redis.hincrby(key, "tts_total_count", 1)
                if bool(data.get("success", False)):
                    await redis.hincrby(key, "tts_success_count", 1)
            elif event.name == "deepseek_call":
                await redis.hincrby(key, "deepseek_total_count", 1)
                if bool(data.get("success", False)):
                    await redis.hincrby(key, "deepseek_success_count", 1)

    return BatchStatsResponse(received=len(request.events), success=True)


@router.get("/summary")
async def get_stats_summary(device_id: str = Query("global")):
    """
    Get statistics summary from Redis.

    - **device_id**: Device identifier (defaults to "global" for all-device aggregate)
    """
    redis = get_redis_service()
    if not redis or not redis.available:
        return {
            "total_sessions": 0,
            "total_lessons_completed": 0,
            "total_words_mastered": 0,
            "total_study_minutes": 0,
            "tts_success_rate": 0.0,
            "deepseek_success_rate": 0.0,
            "message": "Redis unavailable",
        }

    raw = await redis.hgetall(f"{STATS_KEY_PREFIX}{device_id}")

    def getf(k: str) -> int:
        """Extract an int field from the raw hash (handles bytes keys)."""
        val = raw.get(k.encode(), b"0") if raw else b"0"
        return _to_int(val.decode() if isinstance(val, bytes) else val)

    tts_ok = getf("tts_success_count")
    tts_total = getf("tts_total_count")
    ds_ok = getf("deepseek_success_count")
    ds_total = getf("deepseek_total_count")

    return {
        "total_sessions": getf("total_sessions"),
        "total_lessons_completed": getf("total_lessons_completed"),
        "total_words_mastered": getf("total_words_mastered"),
        "total_study_minutes": getf("total_study_minutes"),
        "tts_success_rate": (tts_ok / tts_total) if tts_total else 0.0,
        "deepseek_success_rate": (ds_ok / ds_total) if ds_total else 0.0,
        "message": "OK",
    }
