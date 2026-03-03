"""
LingAI Backend Configuration
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import Optional


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
    
    # TTS Provider
    tts_provider: str = "aliyun"              # aliyun | edge
    tts_fallback_enabled: bool = True         # 生产建议 true（有降级）
    aliyun_nls_endpoint: str = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts"
    aliyun_region: str = "cn-shanghai"
    aliyun_voice_ko: str = "xiaoyun"          # 韩语音色（账号可用值，后续可调）
    aliyun_voice_zh: str = "xiaoyun"          # 中文音色
    
    # Data paths
    data_dir: str = "./data"
    audio_cache_dir: str = "./data/audio_cache"
    
    # API Timeouts (seconds)
    llm_timeout: int = 20  # LLM响应需要足够时间
    tts_timeout: int = 10
    
    # Redis（生产环境必须通过环境变量 REDIS_URL 注入，禁止在源码中写入密码）
    redis_url: str = "redis://localhost:6379/0"
    
    # TTS Redis Cache
    tts_redis_ttl: int = 7 * 24 * 3600  # 7 days
    tts_preload_enabled: bool = True
    
    # CORS（生产默认关闭，dev 通过 .env 显式开启）
    cors_enabled: bool = False
    cors_allow_origins: str = ""                  # 逗号分隔白名单，如 "http://localhost:3000,https://app.example.com"
    cors_allow_credentials: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
