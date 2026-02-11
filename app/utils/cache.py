"""
Cache Utilities
"""
import os
import json
import hashlib
from typing import Any, Optional
from datetime import datetime, timedelta
from loguru import logger


class FileCache:
    """
    Simple file-based cache for storing JSON data.
    """
    
    def __init__(self, cache_dir: str, default_ttl_hours: int = 24):
        self.cache_dir = cache_dir
        self.default_ttl = timedelta(hours=default_ttl_hours)
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_path(self, key: str) -> str:
        """Generate cache file path from key."""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{key_hash}.json")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value by key.
        
        Returns None if not found or expired.
        """
        cache_path = self._get_cache_path(key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Check expiration
            expires_at = datetime.fromisoformat(data.get("expires_at", ""))
            if datetime.now() > expires_at:
                os.remove(cache_path)
                return None
            
            return data.get("value")
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[timedelta] = None):
        """
        Set cache value with optional TTL.
        """
        cache_path = self._get_cache_path(key)
        ttl = ttl or self.default_ttl
        expires_at = datetime.now() + ttl
        
        try:
            data = {
                "key": key,
                "value": value,
                "created_at": datetime.now().isoformat(),
                "expires_at": expires_at.isoformat()
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Cache write error: {e}")
    
    def delete(self, key: str):
        """Delete cached value."""
        cache_path = self._get_cache_path(key)
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception as e:
                logger.warning(f"Cache delete error: {e}")
    
    def clear(self):
        """Clear all cache files."""
        try:
            for filename in os.listdir(self.cache_dir):
                if filename.endswith(".json"):
                    os.remove(os.path.join(self.cache_dir, filename))
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
