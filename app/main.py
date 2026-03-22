"""
LingAI Backend - FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import os

from app.config import get_settings
from app.routers import tts, dict_ai, content, stats, spirit, sse_test
from app.services.redis_service import init_redis, close_redis

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("LingAI Backend starting...")
    
    # Ensure data directories exist
    os.makedirs(settings.data_dir, exist_ok=True)
    os.makedirs(settings.audio_cache_dir, exist_ok=True)
    
    logger.info(f"Data directory: {settings.data_dir}")
    logger.info(f"Audio cache directory: {settings.audio_cache_dir}")
    
    # Initialize Redis for TTS caching
    await init_redis(settings)
    
    yield
    
    # Shutdown
    await close_redis()
    logger.info("LingAI Backend shutting down...")


# Create FastAPI application
app = FastAPI(
    title="LingAI Backend",
    description="韩语学习App服务端API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for development
if settings.cors_enabled:
    allow_origins = settings.cors_origins_list or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include routers
app.include_router(tts.router, prefix="/api/tts", tags=["TTS"])
app.include_router(dict_ai.router, prefix="/api/dict", tags=["Dictionary"])
app.include_router(content.router, prefix="/api/content", tags=["Content"])
app.include_router(stats.router, prefix="/api/stats", tags=["Statistics"])
app.include_router(spirit.router, prefix="/api/spirit", tags=["Spirit"])
app.include_router(sse_test.router, prefix="/api/sse", tags=["SSE Test"])


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "name": "LingAI Backend",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
