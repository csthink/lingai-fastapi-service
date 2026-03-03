"""
Content domain models.
"""
from pydantic import BaseModel
from typing import List, Dict, Any

from app.models.schemas import WordEntry


class LessonContent(BaseModel):
    """Lesson content model."""
    lesson_id: int
    level: int
    title: str
    words: List[WordEntry]
    audio_urls: Dict[str, str] = {}  # word_id -> audio_url
    ai_mnemonics: Dict[str, Any] = {}  # word_id -> mnemonic data
