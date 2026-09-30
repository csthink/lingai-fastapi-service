"""
Application-level service singletons + FastAPI DI factories.

Usage in routers:
    from app.dependencies import get_llm_service, get_tts_service
    @router.get("/example")
    async def example(llm: LLMService = Depends(get_llm_service)):
        ...
"""
from typing import Optional
from loguru import logger

from app.config import Settings
from app.services.llm_service import LLMService
from app.services.aliyun_tts import AliyunTTSService

_llm_service: Optional[LLMService] = None
_tts_service: Optional[AliyunTTSService] = None


def init_services(settings: Settings) -> None:
    """Create singleton service instances on startup."""
    global _llm_service, _tts_service
    _llm_service = LLMService(settings)
    _tts_service = AliyunTTSService(settings)
    logger.info("LLMService and AliyunTTSService singletons initialised")


async def close_services() -> None:
    """Release resources on shutdown."""
    global _llm_service, _tts_service
    if _llm_service:
        await _llm_service.close()
    if _tts_service:
        await _tts_service.close()
    logger.info("Service singletons closed")


# ── FastAPI Depends factories ────────────────────────────────────────


def get_llm_service() -> LLMService:
    """Dependency that returns the LLMService singleton."""
    return _llm_service


def get_tts_service() -> AliyunTTSService:
    """Dependency that returns the AliyunTTSService singleton."""
    return _tts_service
