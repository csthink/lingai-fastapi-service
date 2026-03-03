"""
TTS (Text-to-Speech) Router
Provides Korean TTS via Alibaba Cloud
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import Response
from loguru import logger

from app.services.aliyun_tts import AliyunTTSService
from app.dependencies import get_tts_service
from app.models.tts import TTSRequest, TTSResponse


router = APIRouter()


@router.post("", response_model=TTSResponse)
async def text_to_speech(
    request: TTSRequest,
    tts_service: AliyunTTSService = Depends(get_tts_service),
):
    """
    Convert text to speech audio.
    
    - **text**: Text to convert (Korean or Chinese)
    - **lang**: Language code (ko=Korean, zh=Chinese)
    
    Returns audio URL or audio data.
    """
    if not request.text or len(request.text) > 500:
        raise HTTPException(status_code=400, detail="Text must be 1-500 characters")
    
    try:
        result = await tts_service.synthesize(request.text, request.lang)
        response = TTSResponse(
            audio_url=result.get("audio_url"),
            duration_ms=result.get("duration_ms"),
            cached=result.get("cached", False)
        )
        return Response(
            content=response.model_dump_json(),
            media_type="application/json",
            headers={"X-TTS-Provider": result.get("provider", "unknown")},
        )
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        # 静默失败，返回空结果（符合PRD要求）
        raise HTTPException(status_code=503, detail="TTS service unavailable")


@router.post("/audio", response_class=Response)
async def text_to_speech_audio(
    request: TTSRequest,
    tts_service: AliyunTTSService = Depends(get_tts_service),
):
    """
    Convert text to speech and return audio directly.

    Returns audio/mpeg binary data.
    """
    if not request.text or len(request.text) > 500:
        raise HTTPException(status_code=400, detail="Text must be 1-500 characters")

    try:
        audio_data, provider = await tts_service.synthesize_audio(request.text, request.lang)
        return Response(
            content=audio_data,
            media_type="audio/mpeg",
            headers={"X-TTS-Provider": provider},
        )
    except Exception as e:
        logger.error(f"TTS audio synthesis failed: {e}")
        raise HTTPException(status_code=503, detail="TTS service unavailable")


@router.get("/play")
async def text_to_speech_get(
    text: str = Query(..., min_length=1, max_length=500),
    lang: str = Query("ko"),
    tts_service: AliyunTTSService = Depends(get_tts_service),
):
    """
    GET endpoint for TTS audio playback.

    Allows direct URL playback from mobile clients.
    Returns audio/mpeg binary data.
    """
    try:
        audio_data, provider = await tts_service.synthesize_audio(text, lang)
        return Response(
            content=audio_data,
            media_type="audio/mpeg",
            headers={"X-TTS-Provider": provider},
        )
    except Exception as e:
        logger.error(f"TTS GET playback failed: {e}")
        raise HTTPException(status_code=503, detail="TTS service unavailable")
