"""
LingAI Backend Models Package
"""
from app.models.schemas import (
    Sense,
    WordEntry,
    WordCreate,
    LessonInfo,
    LessonProgress,
    Quiz,
    QuizOption,
    QuizStem,
    WordbookEntry,
    DailyTask,
)

from app.models.content import LessonContent

from app.models.dict_ai import (
    DictAIRequest,
    ExampleSentence,
    MeaningDetail,
    Collocation,
    SynonymWord,
    RelatedWord,
    DictAIResponse,
    DictSearchResponse,
    QuickTranslateResponse,
)

from app.models.stats import (
    StatEvent,
    BatchStatsRequest,
    BatchStatsResponse,
)

from app.models.spirit import (
    ChatMessage,
    SpiritChatRequest,
    SpiritChatResponse,
)

from app.models.tts import (
    TTSRequest,
    TTSResponse,
)

__all__ = [
    # schemas
    "Sense",
    "WordEntry",
    "WordCreate",
    "LessonInfo",
    "LessonProgress",
    "Quiz",
    "QuizOption",
    "QuizStem",
    "WordbookEntry",
    "DailyTask",
    # content
    "LessonContent",
    # dict_ai
    "DictAIRequest",
    "ExampleSentence",
    "MeaningDetail",
    "Collocation",
    "SynonymWord",
    "RelatedWord",
    "DictAIResponse",
    "DictSearchResponse",
    "QuickTranslateResponse",
    # stats
    "StatEvent",
    "BatchStatsRequest",
    "BatchStatsResponse",
    # spirit
    "ChatMessage",
    "SpiritChatRequest",
    "SpiritChatResponse",
    # tts
    "TTSRequest",
    "TTSResponse",
]
