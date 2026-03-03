"""
Alibaba Cloud TTS Service
Provides Korean text-to-speech synthesis with Redis + File caching
"""
import os
import asyncio
import hashlib
import json
import time
from typing import Dict, Any, Optional
from loguru import logger
import httpx

from app.config import Settings
from app.services.redis_service import get_redis_service


class AliyunTTSService:
    """
    Alibaba Cloud TTS Service wrapper with dual-layer caching.
    
    Cache layers:
    - L1: Redis (hot data, fast access)
    - L2: File system (full data, persistent)
    - L3: TTS API (real-time synthesis)
    """
    
    # Korean voice options
    KOREAN_VOICES = {
        "female": "Yoomi",  # 阿里云韩语女声
        "male": "Jinho"     # 阿里云韩语男声
    }
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache_dir = settings.audio_cache_dir
        self.redis = get_redis_service()
        self._token_cache: Dict[str, Any] = {"token": "", "expire": 0}
        os.makedirs(self.cache_dir, exist_ok=True)

    async def close(self):
        """Release resources on shutdown (reserved for future long-lived clients)."""
        pass
    
    def _get_cache_key(self, text: str, lang: str) -> str:
        """Generate cache key for Redis and file."""
        text_hash = hashlib.md5(f"{text}_{lang}".encode()).hexdigest()
        return text_hash
    
    def _get_redis_key(self, text: str, lang: str) -> str:
        """Generate Redis cache key."""
        text_hash = self._get_cache_key(text, lang)
        return f"tts:audio:{lang}:{text_hash}"
    
    def _get_cache_path(self, text: str, lang: str) -> str:
        """Generate cache file path for text."""
        text_hash = self._get_cache_key(text, lang)
        return os.path.join(self.cache_dir, f"{text_hash}.mp3")
    
    def _check_file_cache(self, text: str, lang: str) -> Optional[bytes]:
        """Check if audio is in file cache."""
        cache_path = self._get_cache_path(text, lang)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "rb") as f:
                    return f.read()
            except Exception as e:
                logger.warning(f"Failed to read file cache: {e}")
        return None
    
    def _save_file_cache(self, text: str, lang: str, audio_data: bytes):
        """Save audio to file cache."""
        cache_path = self._get_cache_path(text, lang)
        try:
            with open(cache_path, "wb") as f:
                f.write(audio_data)
        except Exception as e:
            logger.warning(f"Failed to save file cache: {e}")
    
    async def synthesize(self, text: str, lang: str = "ko") -> Dict[str, Any]:
        """
        Synthesize text to speech (returns metadata).
        """
        # Get audio first
        _audio, provider = await self.synthesize_audio(text, lang)
        cache_path = self._get_cache_path(text, lang)
        
        return {
            "audio_url": f"file://{cache_path}",
            "duration_ms": self._estimate_duration(text, lang),
            "cached": True,
            "provider": provider,
        }
    
    async def synthesize_audio(self, text: str, lang: str = "ko") -> tuple:
        """
        Synthesize text and return (audio_bytes, provider).
        
        Three-layer cache strategy:
        1. L1 Redis cache (hot data, memory)
        2. L2 File cache (full data, disk)
        3. L3 TTS API (real-time synthesis)
        
        Returns:
            tuple[bytes, str]: (audio_data, provider)
        """
        redis_key = self._get_redis_key(text, lang)
        
        # L1: Check Redis cache
        if self.redis and self.redis.available:
            cached_audio = await self.redis.get(redis_key)
            if cached_audio:
                logger.debug(f"Redis cache HIT: {text[:20]}...")
                return cached_audio, "cache"
        
        # L2: Check file cache
        file_cached = self._check_file_cache(text, lang)
        if file_cached:
            logger.debug(f"File cache HIT: {text[:20]}...")
            # Backfill to Redis for faster future access
            if self.redis and self.redis.available:
                await self.redis.set(
                    redis_key, 
                    file_cached, 
                    ttl=self.settings.tts_redis_ttl
                )
            return file_cached, "cache"
        
        # L3: Call TTS API for synthesis
        logger.info(f"TTS API synthesis: {text[:20]}...")
        audio_data, provider = await self._call_tts_api(text, lang)
        
        # Save to L2 file cache
        self._save_file_cache(text, lang, audio_data)
        
        # Save to L1 Redis cache
        if self.redis and self.redis.available:
            await self.redis.set(
                redis_key, 
                audio_data, 
                ttl=self.settings.tts_redis_ttl
            )
        
        return audio_data, provider
    
    # ── Aliyun Token management ──────────────────────────────────────
    
    async def _get_aliyun_token(self) -> str:
        """Get Aliyun NLS token with in-memory caching."""
        now = int(time.time())
        if self._token_cache["token"] and now < self._token_cache["expire"] - 60:
            return self._token_cache["token"]
        
        def _create():
            from aliyunsdkcore.client import AcsClient
            from aliyunsdkcore.request import CommonRequest
            
            client = AcsClient(
                self.settings.aliyun_access_key_id,
                self.settings.aliyun_access_key_secret,
                self.settings.aliyun_region,
            )
            req = CommonRequest()
            req.set_method("POST")
            req.set_domain("nls-meta.cn-shanghai.aliyuncs.com")
            req.set_version("2019-02-28")
            req.set_action_name("CreateToken")
            raw = client.do_action_with_exception(req)
            data = json.loads(raw.decode("utf-8"))
            return data["Token"]["Id"], int(data["Token"]["ExpireTime"])
        
        logger.info("Refreshing Aliyun NLS token ...")
        token, expire = await asyncio.to_thread(_create)
        self._token_cache = {"token": token, "expire": expire}
        logger.info(f"Aliyun NLS token refreshed, expires at {expire}")
        return token
    
    # ── Aliyun REST TTS ──────────────────────────────────────────────
    
    async def _call_aliyun_tts(self, text: str, lang: str) -> tuple:
        """Call Aliyun NLS REST TTS endpoint. Returns (bytes, provider)."""
        token = await self._get_aliyun_token()
        voice = self.settings.aliyun_voice_ko if lang == "ko" else self.settings.aliyun_voice_zh
        params = {
            "token": token,
            "appkey": self.settings.aliyun_tts_app_key,
            "text": text,
            "format": "mp3",
            "sample_rate": 16000,
            "voice": voice,
        }
        async with httpx.AsyncClient(timeout=self.settings.tts_timeout) as client:
            resp = await client.get(self.settings.aliyun_nls_endpoint, params=params)
        ct = resp.headers.get("content-type", "")
        if resp.status_code != 200 or "audio" not in ct:
            raise RuntimeError(
                f"Aliyun TTS failed: status={resp.status_code}, lang={lang}, voice={voice}, body={resp.text[:200]}"
            )
        return resp.content, "aliyun"
    
    # ── Provider dispatch ────────────────────────────────────────────
    
    async def _call_tts_api(self, text: str, lang: str) -> tuple:
        """
        Call TTS API with provider routing.
        Returns (bytes, provider_name).
        
        Priority (configurable via tts_provider):
        1. Alibaba Cloud TTS (default)
        2. Edge TTS (fallback / dev-only)
        """
        # Explicit Edge-only mode
        if self.settings.tts_provider == "edge":
            logger.info("TTS provider=edge, using Edge TTS directly")
            audio = await self._fallback_tts(text, lang)
            return audio, "edge"
        
        # Aliyun primary
        try:
            return await self._call_aliyun_tts(text, lang)
        except Exception as e:
            logger.warning(f"Aliyun TTS error: {e}")
            if not self.settings.tts_fallback_enabled:
                raise
            logger.info("Falling back to Edge TTS")
            audio = await self._fallback_tts(text, lang)
            return audio, "edge"
    
    async def _fallback_tts(self, text: str, lang: str) -> bytes:
        """
        Fallback TTS using edge-tts (free Microsoft Edge TTS).
        
        POC only - for development without Aliyun credentials.
        """
        try:
            import edge_tts
            
            # Select voice based on language
            if lang == "ko":
                voice = "ko-KR-SunHiNeural"  # Korean female
            else:
                voice = "zh-CN-XiaoxiaoNeural"  # Chinese female
            
            communicate = edge_tts.Communicate(text, voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            
            return audio_data
        except ImportError:
            logger.error("edge-tts not installed. Run: pip install edge-tts")
            raise RuntimeError("TTS service not available")
        except Exception as e:
            logger.error(f"Fallback TTS failed: {e}")
            raise
    
    def _estimate_duration(self, text: str, lang: str) -> int:
        """Estimate audio duration in milliseconds."""
        # Rough estimate: ~150ms per character for Korean
        chars_per_second = 7 if lang == "ko" else 5
        return int(len(text) / chars_per_second * 1000)
