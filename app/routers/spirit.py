"""
Spirit Chat Router
AI韩语学习助手多轮对话接口
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from loguru import logger

from app.services.llm_service import LLMService
from app.dependencies import get_llm_service

router = APIRouter()

# System prompt for Korean learning assistant
SPIRIT_SYSTEM_PROMPT = """你是"小语灵"，一个专业且友好的韩语学习助手。

你的职责：
1. 解释韩语语法和用法
2. 翻译中韩双语内容
3. 解答TOPIK考试相关问题
4. 提供韩语学习建议和技巧

回答规范：
- 使用简洁明了的中文回答
- 韩语内容使用韩文字母，必要时提供罗马音
- 语法解释时给出例句
- 保持亲切友好的语气

注意：你只回答韩语学习相关的问题。对于无关问题，礼貌地引导用户回到韩语学习话题。"""


class ChatMessage(BaseModel):
    """Chat message model."""
    role: str  # 'user' or 'assistant'
    content: str


class SpiritChatRequest(BaseModel):
    """Spirit chat request model."""
    messages: List[ChatMessage]


class SpiritChatResponse(BaseModel):
    """Spirit chat response model."""
    reply: str
    success: bool = True
    error: Optional[str] = None


@router.post("/chat", response_model=SpiritChatResponse)
async def spirit_chat(
    request: SpiritChatRequest,
    llm_service: LLMService = Depends(get_llm_service),
):
    """
    多轮对话接口
    
    接收历史消息列表，返回AI回复
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages cannot be empty")
    
    try:
        # 构建对话历史
        messages_for_llm = []
        for msg in request.messages:
            messages_for_llm.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # 调用LLM
        reply = await llm_service.chat_completion(
            messages=messages_for_llm,
            system_prompt=SPIRIT_SYSTEM_PROMPT
        )
        
        if reply:
            logger.info(f"Spirit chat success: {len(request.messages)} messages")
            return SpiritChatResponse(reply=reply, success=True)
        else:
            logger.warning("Spirit chat: LLM returned empty response")
            return SpiritChatResponse(
                reply="抱歉，我暂时无法回答，请稍后再试。",
                success=False,
                error="LLM returned empty response"
            )
    
    except Exception as e:
        logger.error(f"Spirit chat error: {e}")
        return SpiritChatResponse(
            reply="服务暂时不可用，请稍后再试。",
            success=False,
            error=str(e)
        )
