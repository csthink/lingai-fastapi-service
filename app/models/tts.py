"""
TTS domain models.
"""
from pydantic import BaseModel
from typing import Optional


class TTSRequest(BaseModel):
    """TTS request model."""
    text: str
    lang: str = "ko"  # ko=Korean, zh=Chinese
    

class TTSResponse(BaseModel):
    """TTS response model with audio URL."""
    audio_url: Optional[str] = None
    duration_ms: Optional[int] = None
    cached: bool = False
