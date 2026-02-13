"""
Redis缓存服务
用于减少LLM重复调用
"""
import json
import redis
from typing import Any, Optional
from loguru import logger
from app.config import get_settings


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
    
    def __init__(self, redis_url: Optional[str] = None, prefix: str = "lingai"):
        if redis_url is None:
            redis_url = get_settings().redis_url
        self._prefix = prefix
        self._redis_url = redis_url
        self._client: Optional[redis.Redis] = None
        self._connect()
    
    def _connect(self) -> None:
        """建立Redis连接"""
        try:
            if RedisCache._pool is None:
                RedisCache._pool = redis.ConnectionPool.from_url(
                    self._redis_url,
                    decode_responses=True
                )
            self._client = redis.Redis(connection_pool=RedisCache._pool)
            # 测试连接
            self._client.ping()
            logger.info(f"Redis connected: {self._redis_url}")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self._client = None
    
    @classmethod
    def get_instance(cls, redis_url: Optional[str] = None) -> 'RedisCache':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = RedisCache(redis_url)
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


# 便捷函数
_cache_instance: Optional[RedisCache] = None

def get_cache(redis_url: Optional[str] = None) -> RedisCache:
    """获取缓存服务实例"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RedisCache(redis_url)
    return _cache_instance
