"""
Dictionary AI Router
Provides AI-enhanced dictionary lookup via Deepseek/Qwen
"""
import json
import os
import re
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Any
from loguru import logger

from app.services.llm_service import LLMService
from app.services.dict_service import DictService
from app.services.redis_service import get_redis_service
from app.config import get_settings


router = APIRouter()

# Load word data for local search
_words_data: List[dict] = []


def _load_words_data() -> List[dict]:
    """Load TOPIK words data from JSON file."""
    global _words_data
    if _words_data:
        return _words_data

    settings = get_settings()
    data_file = os.path.join(settings.data_dir, "topik1_words.json")

    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            _words_data = data.get('words', [])
            logger.info(f"Loaded {len(_words_data)} words for dictionary search")
    except Exception as e:
        logger.error(f"Failed to load words data: {e}")
        _words_data = []

    return _words_data


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


@router.get("/search")
async def search_dict(
    query: str = Query(..., min_length=1, max_length=50),
    direction: str = Query("auto", pattern="^(auto|ko2zh|zh2ko)$")
):
    """
    Dictionary search endpoint (LLM-only mode).

    - **query**: Word to search (Korean or Chinese)
    - **direction**: auto (detect), ko2zh (Korean→Chinese), zh2ko (Chinese→Korean)

    Uses LLM for dictionary lookup with Redis caching.
    No local vocabulary file search.
    """
    import re
    
    # Detect direction if auto
    if direction == "auto":
        # Check if query contains Korean characters
        korean_pattern = re.compile(r'[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]')
        if korean_pattern.search(query):
            actual_direction = "ko2zh"
        else:
            actual_direction = "zh2ko"
    else:
        actual_direction = direction

    settings = get_settings()
    redis = get_redis_service()
    cache_key = f"dict_search:{query}:{actual_direction}"
    
    # Check cache first
    cached_result = await redis.get_json(cache_key) if redis else None
    if cached_result:
        logger.info(f"Cache hit for: {query}")
        return cached_result
    
    # Cache miss - call LLM
    logger.info(f"Cache miss for: {query}, calling LLM")
    llm_service = LLMService(settings)
    
    try:
        ai_result = await llm_service.get_dict_supplement(
            word=query,
            direction=actual_direction
        )
        
        ai_response = DictAIResponse(**ai_result)
        
        # Build response
        response = DictSearchResponse(
            source='ai',
            query=query,
            direction=actual_direction,
            results=[],  # No local results
            ai_supplement=ai_response
        )
        
        result_dict = response.model_dump(by_alias=True)
        
        # Cache the result
        if redis:
            await redis.set_json(cache_key, result_dict)
        logger.info(f"Cached result for: {query}")
        
        return result_dict
        
    except Exception as e:
        logger.warning(f"LLM search failed: {e}")
        import traceback
        logger.warning(traceback.format_exc())
        
        # Return empty response on error
        response = DictSearchResponse(
            source='ai',
            query=query,
            direction=actual_direction,
            results=[],
            ai_supplement=None
        )
        return response.model_dump(by_alias=True)


@router.get("/search/stream")
async def search_dict_stream(
    query: str = Query(..., min_length=1, max_length=50),
    direction: str = Query("auto", pattern="^(auto|ko2zh|zh2ko)$")
):
    """
    SSE streaming dictionary search endpoint.
    
    Returns Server-Sent Events with real-time LLM token output.
    If cached, returns complete result immediately.
    
    Event types:
    - cached: {complete result} - Cache hit, full response
    - token: {text chunk} - LLM streaming token
    - done: {final result} - Streaming complete
    - error: {message} - Error occurred
    """
    # Detect direction if auto
    if direction == "auto":
        korean_pattern = re.compile(r'[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]')
        if korean_pattern.search(query):
            actual_direction = "ko2zh"
        else:
            actual_direction = "zh2ko"
    else:
        actual_direction = direction

    settings = get_settings()
    redis = get_redis_service()
    cache_key = f"dict_search:{query}:{actual_direction}"
    
    async def generate_sse():
        # Check cache first
        cached_result = await redis.get_json(cache_key) if redis else None
        if cached_result:
            logger.info(f"Stream: Cache hit for {query}")
            yield f"data: {json.dumps({'type': 'cached', 'data': cached_result}, ensure_ascii=False)}\n\n"
            return
        
        # Cache miss - stream from LLM
        logger.info(f"Stream: Cache miss for {query}, streaming from LLM")
        llm_service = LLMService(settings)
        
        # Build prompt (complete version with Chinese requirements)
        if actual_direction == "ko2zh":
            prompt = f'''请为韩语单词"{query}"提供详细的词典解析（JSON格式）：

1. ai_meaning: 主要中文释义（用斜杠分隔多个含义，如"爱/爱情/喜爱"）
2. word_type: 词性（名词/动词/形容词/副词/感叹词等）
3. hanja: 对应汉字（如果是汉字词，如"愛"；如果是固有词则为空）
4. composition: 词语构成解析（解释词根含义）
5. meanings: 含义详解数组，每项含：
   - type: 含义类型（具体义/抽象义/比喻义等）
   - explanation: 详细解释
6. collocations: 常用搭配词组数组，每项含：
   - phrase: 韩语搭配
   - meaning: 中文含义
   - example_ko: 韩语例句（可选）
   - example_zh: 中文翻译（可选）
7. ai_examples: 例句数组，按场景分类，每项含：
   - category: 场景分类（如"日常对话"、"正式场合"、"书面语"）
   - ko: 韩语例句
   - zh: 中文翻译
8. synonyms: 近义词数组，每项含：
   - word: 韩语词
   - meaning: 中文含义
   - difference: 区别说明（与原词的差异）
9. antonyms: 反义词数组，每项含：
   - word: 韩语词
   - meaning: 中文含义
10. related_words: 扩展词汇数组，每项含：
    - word: 韩语词
    - meaning: 中文含义
11. tips: 实用知识/文化背景（一句话描述，可选）

要求：
- 内容详尽准确，适合韩语学习者
- 例句自然地道，涵盖不同场景
- 仅输出JSON，无其他内容'''
        else:
            prompt = f'''请为中文词"{query}"提供韩语翻译的详细解析（JSON格式）：

1. ai_meaning: 最常用的韩语翻译（用斜杠分隔多个含义，如"병원"）
2. word_type: 词性（名词/动词/形容词/副词/感叹词等）
3. hanja: 对应汉字（如有）
4. composition: 词语构成解析
5. meanings: 含义详解数组，每项含：
   - type: 含义类型（用中文描述，如"一般含义"、"专业含义"、"口语"等）
   - explanation: 用中文详细解释该韩语词的含义
6. collocations: 常用搭配词组数组，每项含：
   - phrase: 韩语搭配
   - meaning: 中文含义（必须是中文！）
   - example_ko: 韩语例句（可选）
   - example_zh: 中文翻译（可选）
7. ai_examples: 例句数组，按场景分类，每项含：
   - category: 场景分类（如"日常对话"、"正式场合"）
   - ko: 韩语例句
   - zh: 中文翻译
8. synonyms: 近义词数组，每项含：
   - word: 韩语词
   - meaning: 中文含义
   - difference: 区别说明（用中文描述与原词的差异）
9. antonyms: 反义词数组，每项含：
   - word: 韩语词
   - meaning: 中文含义
10. related_words: 扩展词汇数组，每项含：
    - word: 韩语词
    - meaning: 中文含义
11. tips: 实用知识/文化背景（一句话描述）

要求：
- 内容详尽准确，适合中国学习者
- 仅输出JSON，无其他内容'''

        full_response = ""
        try:
            async for chunk in llm_service.stream_llm(prompt):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'token', 'data': chunk}, ensure_ascii=False)}\n\n"
            
            # Parse and cache the complete response
            try:
                # Extract JSON from response
                json_text = full_response.strip()
                if json_text.startswith("```"):
                    # Remove markdown code blocks
                    json_text = re.sub(r'^```(?:json)?\s*', '', json_text)
                    json_text = re.sub(r'\s*```$', '', json_text)
                
                ai_result = json.loads(json_text)
                ai_response = DictAIResponse(**ai_result)
                
                response = DictSearchResponse(
                    source='ai',
                    query=query,
                    direction=actual_direction,
                    results=[],
                    ai_supplement=ai_response
                )
                result_dict = response.model_dump(by_alias=True)
                
                # Cache the result
                if redis:
                    await redis.set_json(cache_key, result_dict)
                logger.info(f"Stream: Cached result for {query}")
                
                yield f"data: {json.dumps({'type': 'done', 'data': result_dict}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.warning(f"Stream: Failed to parse response: {e}")
                yield f"data: {json.dumps({'type': 'done', 'data': {'raw': full_response}}, ensure_ascii=False)}\n\n"
                
        except Exception as e:
            logger.error(f"Stream: LLM error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/ai", response_model=DictAIResponse)
async def dict_ai_lookup(request: DictAIRequest):
    """
    Get AI-enhanced dictionary information for a word.
    
    - **word**: Word to look up
    - **direction**: Translation direction (ko2zh or zh2ko)
    
    Returns AI-generated meaning, examples, synonyms, antonyms.
    Fails silently per PRD requirement.
    """
    if not request.word or len(request.word) > 50:
        raise HTTPException(status_code=400, detail="Word must be 1-50 characters")
    
    settings = get_settings()
    llm_service = LLMService(settings)
    
    try:
        result = await llm_service.get_dict_supplement(
            word=request.word,
            direction=request.direction
        )
        return DictAIResponse(**result)
    except Exception as e:
        logger.warning(f"Dictionary AI lookup failed: {e}")
        # 静默失败，返回空结果（符合PRD要求）
        return DictAIResponse(error=None)  # 不暴露错误细节


@router.post("/mnemonic")
async def generate_mnemonic(word: str, meaning: str):
    """
    Generate AI mnemonic content for vocabulary learning.
    
    - **word**: Korean word
    - **meaning**: Chinese meaning
    
    Returns TOPIK-style example sentences and related words.
    """
    settings = get_settings()
    llm_service = LLMService(settings)
    
    try:
        result = await llm_service.generate_mnemonic(word, meaning)
        return result
    except Exception as e:
        logger.warning(f"Mnemonic generation failed: {e}")
        return {"examples": [], "synonyms": [], "antonyms": []}


class QuickTranslateResponse(BaseModel):
    """Quick translate response model."""
    word: str
    translation: str
    source: str  # 'local' or 'ai'


@router.get("/quick-translate")
async def quick_translate(
    word: str = Query(..., min_length=1, max_length=50),
    direction: str = Query("auto", pattern="^(auto|ko2zh|zh2ko)$")
):
    """
    Quick translate a word - returns only translation result.
    First checks local dictionary, falls back to LLM if not found.
    """
    # Auto-detect direction
    if direction == "auto":
        import re
        korean_pattern = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF]')
        actual_direction = "ko2zh" if korean_pattern.search(word) else "zh2ko"
    else:
        actual_direction = direction
    
    # Try local dictionary first
    words_data = _load_words_data()
    
    if actual_direction == "ko2zh":
        # Search Korean word
        for entry in words_data:
            if entry.get('hangul') == word:
                return QuickTranslateResponse(
                    word=word,
                    translation=entry.get('primary_meaning', ''),
                    source='local'
                )
    else:
        # Search Chinese word - search in primary_meaning field
        for entry in words_data:
            if word in entry.get('primary_meaning', ''):
                return QuickTranslateResponse(
                    word=word,
                    translation=entry.get('hangul', ''),
                    source='local'
                )
    
    # Not found in local, use LLM
    settings = get_settings()
    redis = get_redis_service()
    cache_key = f"quick_translate:{word}:{actual_direction}"
    
    # Check cache
    cached_result = await redis.get_json(cache_key) if redis else None
    if cached_result:
        return QuickTranslateResponse(
            word=word,
            translation=cached_result.get('translation', ''),
            source='ai'
        )
    
    # Call LLM for quick translation
    llm_service = LLMService(settings)
    try:
        translation = await llm_service.quick_translate(word, actual_direction)
        
        # Cache the result
        if redis:
            await redis.set_json(cache_key, {"translation": translation}, ttl=86400 * 7)  # 7 days
        
        return QuickTranslateResponse(
            word=word,
            translation=translation,
            source='ai'
        )
    except Exception as e:
        logger.warning(f"Quick translate failed: {e}")
        return QuickTranslateResponse(
            word=word,
            translation="翻译失败",
            source='error'
        )

