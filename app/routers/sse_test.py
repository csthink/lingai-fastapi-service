"""
SSE Test Router
用于验证HarmonyOS对Server-Sent Events的支持
"""
import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger


router = APIRouter()


async def generate_sse_events():
    """生成SSE测试事件流"""
    # 模拟LLM逐字输出
    test_text = "这是一个SSE流式响应测试。每个字会逐个发送，模拟LLM的打字机效果。안녕하세요 한국어도 테스트합니다."
    
    for i, char in enumerate(test_text):
        # SSE格式: data: {内容}\n\n
        yield f"data: {char}\n\n"
        await asyncio.sleep(0.1)  # 模拟延迟
    
    # 发送结束事件
    yield "data: [DONE]\n\n"


async def generate_dict_sse_demo():
    """模拟词典查询的SSE流式响应"""
    import json
    
    # 模拟分段返回词典内容
    stages = [
        {"type": "meaning", "content": "你好/您好"},
        {"type": "word_type", "content": "感叹词"},
        {"type": "example", "content": {"ko": "안녕하세요, 저는 학생입니다.", "zh": "你好，我是学生。"}},
        {"type": "tip", "content": "这是韩语中最常用的问候语，根据时间和场合可变形为안녕/안녕하십니까等。"},
        {"type": "done", "content": None}
    ]
    
    for stage in stages:
        yield f"data: {json.dumps(stage, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.5)  # 模拟LLM思考时间


@router.get("/test/simple")
async def sse_simple_test():
    """
    简单SSE测试端点
    
    返回逐字符流式响应，用于验证基本SSE支持
    """
    logger.info("SSE simple test started")
    return StreamingResponse(
        generate_sse_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用nginx缓冲
        }
    )


@router.get("/test/dict")
async def sse_dict_test():
    """
    词典查询SSE测试端点
    
    模拟分阶段返回词典内容（释义→词性→例句→Tips）
    """
    logger.info("SSE dict test started")
    return StreamingResponse(
        generate_dict_sse_demo(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
