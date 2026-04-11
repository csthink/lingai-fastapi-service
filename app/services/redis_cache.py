"""
Redis缓存服务
用于减少LLM重复调用
"""
import json
import redis
from typing import Any, Optional
from loguru import logger

from app.config import Settings, get_settings


class RedisCache:
    """
    Redis缓存服务封装
    
    特点：
    - 连接池管理
    - JSON序列化/反序列化
    - 键前缀支持
    - 可选TTL
    """
    
    _instance: Optional['RedisCache'] = None
    _pool: Optional[redis.ConnectionPool] = None
    _config_signature: Optional[tuple[str, int, int, str, str]] = None

    def __init__(self, settings: Settings):
        self._settings = settings
        self._prefix = settings.redis_prefix
        self._client: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self) -> None:
        """建立Redis连接"""
        try:
            if RedisCache._pool is None:
                RedisCache._pool = redis.ConnectionPool(**self._settings.redis_sync_kwargs)
            self._client = redis.Redis(connection_pool=RedisCache._pool)
            # 测试连接
            self._client.ping()
            logger.info("Redis connected: {}", self._settings.redis_endpoint)
        except Exception as e:
            logger.error("Redis connection failed for {}: {}", self._settings.redis_endpoint, e)
            self._client = None
    
    @classmethod
    def _build_signature(cls, settings: Settings) -> tuple[str, int, int, str, str]:
        return (
            settings.redis_host,
            settings.redis_port,
            settings.redis_db,
            settings.redis_password,
            settings.redis_prefix,
        )

    @classmethod
    def _reset_singleton(cls) -> None:
        if cls._pool is not None:
            cls._pool.disconnect()
        cls._pool = None
        cls._instance = None
        cls._config_signature = None

    @classmethod
    def get_instance(cls, settings: Optional[Settings] = None) -> 'RedisCache':
        """获取单例实例"""
        settings = settings or get_settings()
        signature = cls._build_signature(settings)
        if cls._instance is None or cls._config_signature != signature:
            cls._reset_singleton()
            cls._instance = RedisCache(settings)
            cls._config_signature = signature
        return cls._instance
    
    def _make_key(self, key: str) -> str:
        """构建带前缀的键"""
        return f"{self._prefix}:{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            反序列化后的值，未命中返回None
        """
        if not self._client:
            return None
            
        try:
            full_key = self._make_key(key)
            value = self._client.get(full_key)
            if value:
                logger.debug(f"Cache hit: {key}")
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值（会被JSON序列化）
            ttl: 过期时间（秒），None表示永不过期
            
        Returns:
            是否成功
        """
        if not self._client:
            return False
            
        try:
            full_key = self._make_key(key)
            json_value = json.dumps(value, ensure_ascii=False)
            if ttl:
                self._client.setex(full_key, ttl, json_value)
            else:
                self._client.set(full_key, json_value)
            logger.debug(f"Cache set: {key}")
            return True
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存项"""
        if not self._client:
            return False
        try:
            full_key = self._make_key(key)
            return self._client.delete(full_key) > 0
        except Exception as e:
            logger.warning(f"Cache delete failed: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查缓存是否存在"""
        if not self._client:
            return False
        try:
            full_key = self._make_key(key)
            return self._client.exists(full_key) > 0
        except Exception as e:
            return False
    
    def is_connected(self) -> bool:
        """检查Redis连接状态"""
        if not self._client:
            return False
        try:
            self._client.ping()
            return True
        except:
            return False


def get_cache(settings: Optional[Settings] = None) -> RedisCache:
    """获取缓存服务实例"""
    return RedisCache.get_instance(settings)
