"""
Redis Service
Manages Redis connection pool and caching operations for TTS audio
"""
import redis.asyncio as aioredis
from typing import Optional
from loguru import logger
from app.config import Settings


class RedisService:
    """Redis connection manager with async support."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[aioredis.Redis] = None
        self.available: bool = False
    
    async def connect(self):
        """Initialize Redis connection from URL."""
        try:
            self.client = aioredis.from_url(
                self.settings.redis_url,
                decode_responses=False,  # Keep binary data for audio
                socket_timeout=5.0,
                socket_connect_timeout=5.0
            )
            
            # Test connection
            await self.client.ping()
            self.available = True
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Will use file cache only.")
            self.client = None
            self.available = False
    
    async def disconnect(self):
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            logger.info("Redis disconnected")
    
    async def get(self, key: str) -> Optional[bytes]:
        """Get value from Redis."""
        if not self.available or not self.client:
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.warning(f"Redis GET failed for {key}: {e}")
            return None
    
    async def set(self, key: str, value: bytes, ttl: Optional[int] = None) -> bool:
        """Set value in Redis with optional TTL."""
        if not self.available or not self.client:
            return False
        try:
            if ttl:
                await self.client.setex(key, ttl, value)
            else:
                await self.client.set(key, value)
            return True
        except Exception as e:
            logger.warning(f"Redis SET failed for {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if not self.available or not self.client:
            return False
        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.warning(f"Redis EXISTS failed: {e}")
            return False
    
    async def keys(self, pattern: str) -> list:
        """Get keys matching pattern."""
        if not self.available or not self.client:
            return []
        try:
            return await self.client.keys(pattern)
        except Exception as e:
            logger.warning(f"Redis KEYS failed: {e}")
            return []


# Global instance
_redis_service: Optional[RedisService] = None


def get_redis_service() -> Optional[RedisService]:
    """Get Redis service instance."""
    return _redis_service


async def init_redis(settings: Settings) -> RedisService:
    """Initialize Redis service on startup."""
    global _redis_service
    _redis_service = RedisService(settings)
    await _redis_service.connect()
    return _redis_service


async def close_redis():
    """Close Redis service on shutdown."""
    global _redis_service
    if _redis_service:
        await _redis_service.disconnect()
