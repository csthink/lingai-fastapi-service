"""
LingAI Backend - FastAPI Application Entry Point
"""
import time
import uuid

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
from loguru import logger
import os

from app.config import get_settings
from app.routers import tts, dict_ai, content, stats, spirit, sse_test
from app.services.redis_service import init_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    
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


# ---------------------------------------------------------------------------
#  Trace Middleware — 链路追踪
# ---------------------------------------------------------------------------

class TraceMiddleware(BaseHTTPMiddleware):
    """
    为每个请求分配 trace_id，用于全链路日志追踪。

    行为：
    1. 优先从请求头 X-Trace-Id 读取（由 Unified Service 网关透传）
    2. 若无则自动生成 UUID
    3. 写入 request.state.trace_id，供下游业务代码使用
    4. 响应头回传 X-Trace-Id
    5. 打印请求/响应摘要日志（含耗时）
    """

    TRACE_HEADER = "X-Trace-Id"

    async def dispatch(self, request: Request, call_next):
        # 1. 获取或生成 trace_id
        trace_id = request.headers.get(self.TRACE_HEADER) or uuid.uuid4().hex
        request.state.trace_id = trace_id

        # 2. 记录请求日志
        logger.info(
            "[{}] --> {} {} (client={})",
            trace_id, request.method, request.url.path,
            request.client.host if request.client else "-",
        )

        # 3. 执行后续处理并计时
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # 4. 响应头回传 trace_id
        response.headers[self.TRACE_HEADER] = trace_id

        # 5. 记录响应日志
        logger.info(
            "[{}] <-- {} {} {} ({:.1f}ms)",
            trace_id, request.method, request.url.path,
            response.status_code, elapsed_ms,
        )

        return response


# Create FastAPI application
app = FastAPI(
    title="LingAI Backend",
    description="韩语学习App服务端API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # POC: allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trace middleware — must be added after CORS so trace_id covers all routes
app.add_middleware(TraceMiddleware)

# Include routers
app.include_router(tts.router, prefix="/api/tts", tags=["TTS"])
app.include_router(dict_ai.router, prefix="/api/dict", tags=["Dictionary"])
app.include_router(content.router, prefix="/api/content", tags=["Content"])
app.include_router(stats.router, prefix="/api/stats", tags=["Statistics"])
app.include_router(spirit.router, prefix="/api/spirit", tags=["Spirit"])
app.include_router(sse_test.router, prefix="/api/sse", tags=["SSE Test"])


# ---------------------------------------------------------------------------
#  Global Exception Handlers — 统一 JSON 错误响应
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    trace_id = getattr(request.state, "trace_id", "")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "traceId": trace_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "trace_id", "")
    logger.exception("[{}] Unhandled exception: {}", trace_id, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "traceId": trace_id},
    )


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
