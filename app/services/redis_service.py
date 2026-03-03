"""
Redis Service
Manages Redis connection pool and caching operations for TTS audio
"""
import json
import redis.asyncio as aioredis
from typing import Any, Optional
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

    async def get_json(self, key: str, prefix: str = "lingai") -> Optional[Any]:
        """Get JSON-serialized value from Redis. Returns deserialized object or None."""
        full_key = f"{prefix}:{key}"
        raw = await self.get(full_key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Redis JSON decode failed for {full_key}: {e}")
            return None

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None, prefix: str = "lingai") -> bool:
        """Set JSON-serialized value with optional TTL."""
        full_key = f"{prefix}:{key}"
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        return await self.set(full_key, data, ttl=ttl)

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

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        """Increment hash field by amount."""
        if not self.available or not self.client:
            return 0
        try:
            return await self.client.hincrby(key, field, amount)
        except Exception as e:
            logger.warning(f"Redis HINCRBY failed for {key}.{field}: {e}")
            return 0

    async def hgetall(self, key: str) -> dict:
        """Get all fields and values of a hash."""
        if not self.available or not self.client:
            return {}
        try:
            return await self.client.hgetall(key)
        except Exception as e:
            logger.warning(f"Redis HGETALL failed for {key}: {e}")
            return {}


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
