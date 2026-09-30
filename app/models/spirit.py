"""
Spirit chat domain models.
"""
from pydantic import BaseModel
from typing import List, Optional


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
