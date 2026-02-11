"""
Pydantic Models/Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== Word Models ====================

class Sense(BaseModel):
    """Word sense/meaning model."""
    meaning: str
    examples: List[Dict[str, str]] = []  # [{"ko": "...", "zh": "..."}]


class WordEntry(BaseModel):
    """Complete word entry model."""
    id: int
    hangul: str = Field(..., description="Korean word in Hangul")
    romanization: Optional[str] = Field(None, description="Romanized pronunciation")
    pos: Optional[str] = Field(None, description="Part of speech")
    primary_meaning: str = Field(..., description="Primary Chinese meaning")
    senses: List[Sense] = Field(default_factory=list, description="All meanings")
    collocations: List[str] = Field(default_factory=list, description="Common collocations")
    examples: List[Dict[str, str]] = Field(default_factory=list, description="Example sentences")
    topik_level: int = Field(..., ge=1, le=6, description="TOPIK level 1-6")
    freq_rank: Optional[int] = Field(None, description="Frequency rank")
    lesson_id: int = Field(..., description="Belonging lesson ID")


class WordCreate(BaseModel):
    """Word creation input model."""
    hangul: str
    romanization: Optional[str] = None
    pos: Optional[str] = None
    primary_meaning: str
    senses: List[Dict[str, Any]] = []
    collocations: List[str] = []
    examples: List[Dict[str, str]] = []
    topik_level: int
    freq_rank: Optional[int] = None
    lesson_id: int


# ==================== Lesson Models ====================

class LessonInfo(BaseModel):
    """Lesson information model."""
    lesson_id: int
    level: int
    title: str
    word_count: int = 50
    status: str = "locked"  # locked, in_progress, completed


class LessonProgress(BaseModel):
    """User's lesson progress model."""
    lesson_id: int
    level: int
    status: int = 0  # 0: locked, 1: in_progress, 2: completed
    mastered_count: int = 0
    mastered_word_ids: List[int] = []
    skipped_word_ids: List[int] = []
    correct_counts: Dict[int, int] = {}  # word_id -> correct count
    updated_at: Optional[datetime] = None


# ==================== Quiz Models ====================

class QuizOption(BaseModel):
    """Quiz option model."""
    id: str  # A, B, C, D
    text: str
    correct: bool = False


class QuizStem(BaseModel):
    """Quiz stem (question) model."""
    display: str  # Text to display
    audio_url: Optional[str] = None  # For listening quizzes


class Quiz(BaseModel):
    """Quiz question model."""
    type: str  # basic_recognition, context_sense, confusion_words, collocation_fill
    word_id: int
    stem: QuizStem
    options: List[QuizOption]
    context: Optional[str] = None  # For context-based questions


# ==================== Review Models ====================

class WordbookEntry(BaseModel):
    """Wordbook (vocabulary notebook) entry model."""
    id: int
    word_id: int
    source: str = "dictionary"
    created_at: datetime
    next_review_at: Optional[datetime] = None
    review_stage: int = 0  # 0-5 corresponding to D0, D1, D3, D7, D14, D30
    ai_mnemonic: Optional[Dict[str, Any]] = None


# ==================== Daily Task Models ====================

class DailyTask(BaseModel):
    """Daily task progress model."""
    date: str  # YYYY-MM-DD
    lesson_step_done: int = 0
    review_count: int = 0
    study_minutes: int = 0
    updated_at: Optional[datetime] = None
