"""
Dictionary AI domain models.
"""
from pydantic import BaseModel
from typing import Optional, List, Any


class DictAIRequest(BaseModel):
    """Dictionary AI request model."""
    word: str
    direction: str = "ko2zh"  # ko2zh or zh2ko


class ExampleSentence(BaseModel):
    """Example sentence model."""
    ko: str
    zh: str
    category: Optional[str] = None  # 场景分类


class MeaningDetail(BaseModel):
    """Meaning detail model."""
    type: str  # 含义类型
    explanation: str  # 详细解释


class Collocation(BaseModel):
    """Collocation model."""
    phrase: str  # 韩语搭配
    meaning: str  # 中文含义
    example_ko: Optional[str] = None
    example_zh: Optional[str] = None
    
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: ''.join(word.capitalize() if i else word for i, word in enumerate(s.split('_')))
    }


class SynonymWord(BaseModel):
    """Synonym with difference explanation."""
    word: str
    meaning: str
    difference: Optional[str] = None  # 区别说明


class RelatedWord(BaseModel):
    """Related word model."""
    word: str
    meaning: str


class DictAIResponse(BaseModel):
    """Dictionary AI response model - detailed version."""
    ai_meaning: Optional[str] = None
    word_type: Optional[str] = None  # 词性
    hanja: Optional[str] = None  # 对应汉字
    composition: Optional[str] = None  # 词语构成
    meanings: List[MeaningDetail] = []  # 含义详解
    collocations: List[Collocation] = []  # 常用搭配
    ai_examples: List[ExampleSentence] = []  # 例句
    synonyms: List[SynonymWord] = []  # 近义词
    antonyms: List[RelatedWord] = []  # 反义词
    related_words: List[RelatedWord] = []  # 扩展词汇
    tips: Optional[str] = None  # 实用知识
    error: Optional[str] = None
    
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: ''.join(word.capitalize() if i else word for i, word in enumerate(s.split('_')))
    }


class DictSearchResponse(BaseModel):
    """Dictionary search response model."""
    source: str  # 'local' or 'ai'
    query: str
    direction: str  # 'ko2zh' or 'zh2ko'
    results: List[Any] = []  # Local word entries
    ai_supplement: Optional[DictAIResponse] = None
    
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: ''.join(word.capitalize() if i else word for i, word in enumerate(s.split('_')))
    }


class QuickTranslateResponse(BaseModel):
    """Quick translate response model."""
    word: str
    translation: str
    source: str  # 'local' or 'ai'
