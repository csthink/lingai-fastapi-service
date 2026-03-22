"""
LingAI Backend Configuration
"""
from functools import lru_cache
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
    redis_url: str = "redis://:**@localhost:10399/0"

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


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
