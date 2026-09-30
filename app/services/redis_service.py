"""
Redis Service
Manages Redis connection pool and caching operations for TTS audio
"""
import json
import redis.asyncio as aioredis
from typing import Any, Optional
from loguru import logger
from app.config import Settings


class RedisStorageError(RuntimeError):
    """A required Redis operation could not be completed."""


class RedisService:
    """Redis connection manager with async support."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client: Optional[aioredis.Redis] = None
        self.available: bool = False
    
    async def connect(self):
        """Initialize Redis connection from settings."""
        try:
            self.client = aioredis.Redis(**self.settings.redis_async_kwargs)

            # Test connection
            await self.client.ping()
            self.available = True
            logger.info("Redis connected successfully: {}", self.settings.redis_endpoint)
        except Exception as e:
            logger.warning(
                "Redis connection failed for {}: {}. Will use file cache only.",
                self.settings.redis_endpoint,
                e,
            )
            self.client = None
            self.available = False
    
    async def disconnect(self):
        """Close Redis connection."""
        if self.client:
            await self.client.aclose()
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

    async def get_json(self, key: str, prefix: Optional[str] = None) -> Optional[Any]:
        """Get JSON-serialized value from Redis. Returns deserialized object or None."""
        selected_prefix = self.settings.redis_prefix if prefix is None else prefix
        full_key = f"{selected_prefix}:{key}" if selected_prefix else key
        raw = await self.get(full_key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Redis JSON decode failed for {full_key}: {e}")
            return None

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None, prefix: Optional[str] = None) -> bool:
        """Set JSON-serialized value with optional TTL."""
        selected_prefix = self.settings.redis_prefix if prefix is None else prefix
        full_key = f"{selected_prefix}:{key}" if selected_prefix else key
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
        """Increment a hash field; never acknowledge a failed statistics write."""
        if not self.available or not self.client:
            raise RedisStorageError("Statistics storage unavailable")
        try:
            return await self.client.hincrby(key, field, amount)
        except Exception as error:
            logger.warning("Redis HINCRBY failed ({})", type(error).__name__)
            raise RedisStorageError("Statistics storage unavailable") from None

    async def hgetall(self, key: str) -> dict:
        """Read hash fields, distinguishing an empty hash from a read failure."""
        if not self.available or not self.client:
            raise RedisStorageError("Statistics storage unavailable")
        try:
            return await self.client.hgetall(key)
        except Exception as error:
            logger.warning("Redis HGETALL failed ({})", type(error).__name__)
            raise RedisStorageError("Statistics storage unavailable") from None


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
