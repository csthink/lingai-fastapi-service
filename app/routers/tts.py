"""
TTS (Text-to-Speech) Router
Provides Korean TTS via Alibaba Cloud
"""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from app.services.aliyun_tts import AliyunTTSService
from app.config import get_settings


router = APIRouter()


class TTSRequest(BaseModel):
    """TTS request model."""
    text: str
    lang: str = "ko"  # ko=Korean, zh=Chinese
    

class TTSResponse(BaseModel):
    """TTS response model with audio URL."""
    audio_url: Optional[str] = None
    duration_ms: Optional[int] = None
    cached: bool = False


@router.post("", response_model=TTSResponse)
async def text_to_speech(request: TTSRequest):
    """
    Convert text to speech audio.
    
    - **text**: Text to convert (Korean or Chinese)
    - **lang**: Language code (ko=Korean, zh=Chinese)
    
    Returns audio URL or audio data.
    """
    if not request.text or len(request.text) > 500:
        raise HTTPException(status_code=400, detail="Text must be 1-500 characters")
    
    settings = get_settings()
    tts_service = AliyunTTSService(settings)
    
    try:
        result = await tts_service.synthesize(request.text, request.lang)
        return TTSResponse(
            audio_url=result.get("audio_url"),
            duration_ms=result.get("duration_ms"),
            cached=result.get("cached", False)
        )
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        # 静默失败，返回空结果（符合PRD要求）
        raise HTTPException(status_code=503, detail="TTS service unavailable")


@router.post("/audio", response_class=Response)
async def text_to_speech_audio(request: TTSRequest):
    """
    Convert text to speech and return audio directly.

    Returns audio/mpeg binary data.
    """
    if not request.text or len(request.text) > 500:
        raise HTTPException(status_code=400, detail="Text must be 1-500 characters")

    settings = get_settings()
    tts_service = AliyunTTSService(settings)

    try:
        audio_data = await tts_service.synthesize_audio(request.text, request.lang)
        return Response(content=audio_data, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"TTS audio synthesis failed: {e}")
        raise HTTPException(status_code=503, detail="TTS service unavailable")


@router.get("/play")
async def text_to_speech_get(
    text: str = Query(..., min_length=1, max_length=500),
    lang: str = Query("ko")
):
    """
    GET endpoint for TTS audio playback.

    Allows direct URL playback from mobile clients.
    Returns audio/mpeg binary data.
    """
    settings = get_settings()
    tts_service = AliyunTTSService(settings)

    try:
        audio_data = await tts_service.synthesize_audio(text, lang)
        return Response(content=audio_data, media_type="audio/mpeg")
    except Exception as e:
        logger.error(f"TTS GET playback failed: {e}")
        raise HTTPException(status_code=503, detail="TTS service unavailable")
