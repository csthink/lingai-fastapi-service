"""
LingAI Backend Configuration
"""
from functools import lru_cache
from typing import Any
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    
    # Deepseek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    
    # Alibaba Cloud Qwen (Backup LLM)
    qwen_api_key: str = ""
    
    # Alibaba Cloud TTS
    aliyun_access_key_id: str = ""
    aliyun_access_key_secret: str = ""
    aliyun_tts_app_key: str = ""
    aliyun_voice_ko: str = "xiaoyun"
    aliyun_voice_zh: str = "xiaoyun"
    
    # Data paths
    data_dir: str = "./data"
    audio_cache_dir: str = "./data/audio_cache"
    
    # API Timeouts (seconds)
    llm_timeout: int = 20  # LLM响应需要足够时间
    tts_timeout: int = 10
    
    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_prefix: str = "lingai"
    redis_socket_timeout: float = 5.0
    redis_connect_timeout: float = 5.0

    # CORS
    cors_enabled: bool = False
    cors_allow_origins: str = ""
    cors_allow_credentials: bool = False
    
    # TTS Redis Cache
    tts_redis_ttl: int = 7 * 24 * 3600  # 7 days
    tts_preload_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins."""
        if not self.cors_allow_origins.strip():
            return []
        return [
            origin.strip()
            for origin in self.cors_allow_origins.split(",")
            if origin.strip()
        ]

    @property
    def redis_endpoint(self) -> str:
        """Return a safe-to-log Redis endpoint string."""
        return f"{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def redis_base_kwargs(self) -> dict[str, Any]:
        """Shared Redis connection kwargs."""
        kwargs: dict[str, Any] = {
            "host": self.redis_host,
            "port": self.redis_port,
            "db": self.redis_db,
        }
        if self.redis_password:
            kwargs["password"] = self.redis_password
        return kwargs

    @property
    def redis_sync_kwargs(self) -> dict[str, Any]:
        """Redis kwargs for sync clients."""
        kwargs = self.redis_base_kwargs.copy()
        kwargs["decode_responses"] = True
        return kwargs

    @property
    def redis_async_kwargs(self) -> dict[str, Any]:
        """Redis kwargs for async clients."""
        kwargs = self.redis_base_kwargs.copy()
        kwargs["decode_responses"] = False
        kwargs["socket_timeout"] = self.redis_socket_timeout
        kwargs["socket_connect_timeout"] = self.redis_connect_timeout
        return kwargs


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
