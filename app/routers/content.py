"""
Content Router
Provides lesson content download API
"""
from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from loguru import logger
import json
import os

from app.config import get_settings


router = APIRouter()


class WordEntry(BaseModel):
    """Word entry model."""
    id: int
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


class LessonContent(BaseModel):
    """Lesson content model."""
    lesson_id: int
    level: int
    title: str
    words: List[WordEntry]
    audio_urls: Dict[str, str] = {}  # word_id -> audio_url
    ai_mnemonics: Dict[str, Any] = {}  # word_id -> mnemonic data


@router.get("/lesson/{lesson_id}", response_model=LessonContent)
async def get_lesson_content(
    lesson_id: int = Path(..., ge=1, le=200, description="Lesson ID (1-200)")
):
    """
    Get full lesson content for download.
    
    - **lesson_id**: Lesson ID (1-200)
    
    Returns complete lesson data including words, audio URLs, AI mnemonics.
    """
    settings = get_settings()
    
    # Try to load from pre-generated data file
    data_file = os.path.join(settings.data_dir, f"lesson_{lesson_id}.json")
    
    if os.path.exists(data_file):
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return LessonContent(**data)
        except Exception as e:
            logger.error(f"Failed to load lesson {lesson_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to load lesson data")
    else:
        # POC: Return placeholder for non-existent lessons
        raise HTTPException(status_code=404, detail=f"Lesson {lesson_id} not found")


@router.get("/levels")
async def get_level_info(words_per_lesson: int = 20):
    """
    Get TOPIK level information and lesson counts.
    
    - **words_per_lesson**: Number of words per lesson (default 20)
    
    Returns level structure for navigation.
    """
    import math
    
    # Word counts per level
    word_counts = {
        1: 1559,  # TOPIK I
        2: 3764,  # TOPIK II
        0: 1203,  # 常考单词
    }
    
    # Calculate lesson counts dynamically
    levels = [
        {"level": 1, "name": "TOPIK I", "lesson_start": 1, "lesson_end": math.ceil(word_counts[1] / words_per_lesson), "lesson_count": math.ceil(word_counts[1] / words_per_lesson), "word_count": word_counts[1]},
        {"level": 2, "name": "TOPIK II", "lesson_start": 1, "lesson_end": math.ceil(word_counts[2] / words_per_lesson), "lesson_count": math.ceil(word_counts[2] / words_per_lesson), "word_count": word_counts[2]},
        {"level": 0, "name": "常考单词", "lesson_start": 1, "lesson_end": math.ceil(word_counts[0] / words_per_lesson), "lesson_count": math.ceil(word_counts[0] / words_per_lesson), "word_count": word_counts[0]},
    ]
    total_lessons = sum(l["lesson_count"] for l in levels)
    return {"levels": levels, "total_lessons": total_lessons, "words_per_lesson": words_per_lesson}


@router.get("/lesson/{lesson_id}/quiz-config")
async def get_quiz_config(
    lesson_id: int = Path(..., ge=1, le=200)
):
    """
    Get quiz configuration for a lesson.
    
    Returns quiz type distribution and rules.
    """
    return {
        "lesson_id": lesson_id,
        "mastery_threshold": 0.85,  # 85% to pass
        "correct_count_required": 2,  # Answer correct 2 times to master
        "max_skip": 10,  # Max words to skip
        "quiz_types": {
            "basic_recognition": 0.25,
            "context_sense": 0.30,
            "confusion_words": 0.25,
            "collocation_fill": 0.20
        }
    }


# Level to file name mapping
def _get_level_file_name(level: int) -> str:
    """Map level to JSON file name."""
    mapping = {
        1: "topik_i_words.json",
        2: "topik_ii_words.json",
        0: "common_words.json"
    }
    return mapping.get(level, f"topik_{level}_words.json")


@router.get("/words/topik/{level}")
async def get_topik_words(
    level: int = Path(..., ge=0, le=2, description="TOPIK level (0=常考单词, 1=TOPIK I, 2=TOPIK II)")
):
    """
    Get all words for a specific TOPIK level.
    
    - **level**: TOPIK level (0=常考单词, 1=TOPIK I, 2=TOPIK II)
    
    Returns list of word entries for the specified level.
    """
    settings = get_settings()
    
    # Load from topik words file
    file_name = _get_level_file_name(level)
    data_file = os.path.join(settings.data_dir, file_name)
    
    if not os.path.exists(data_file):
        raise HTTPException(status_code=404, detail=f"TOPIK level {level} word data not found")
    
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle nested structure: {level, words: [...]}
        words_data = data.get("words", []) if isinstance(data, dict) else data
        
        # Transform field names for frontend 
        words = []
        for word in words_data:
            # Get first example from senses if available
            examples = []
            senses = word.get("senses", [])
            for sense in senses:
                sense_examples = sense.get("examples", [])
                examples.extend(sense_examples)
            
            words.append({
                "id": word.get("id", 0),
                "hangul": word.get("hangul", ""),
                "romanization": word.get("romanization", ""),
                "pos": word.get("pos", ""),
                "primaryMeaning": word.get("primary_meaning", ""),
                "senses": senses,
                "collocations": word.get("collocations", []),
                "examples": examples[:3],  # Limit to 3 examples
                "topikLevel": level,
                "freqRank": word.get("id", 0),
                "lessonId": ((word.get("id", 1) - 1) // 50) + 1
            })
        
        return {
            "level": level,
            "wordCount": len(words),
            "words": words
        }
    except Exception as e:
        logger.error(f"Failed to load TOPIK {level} words: {e}")
        raise HTTPException(status_code=500, detail="Failed to load word data")


@router.get("/words/level/{level}/lesson/{lesson_id}")
async def get_lesson_words(
    level: int = Path(..., ge=0, le=2, description="TOPIK level (0=常考单词, 1=TOPIK I, 2=TOPIK II)"),
    lesson_id: int = Path(..., ge=1, le=500, description="Lesson ID within the level"),
    words_per_lesson: int = 20
):
    """
    Get words for a specific lesson within a TOPIK level.
    
    - **level**: TOPIK level (0=常考单词, 1=TOPIK I, 2=TOPIK II)
    - **lesson_id**: Lesson ID within the level (1-based)
    - **words_per_lesson**: Number of words per lesson (default 20)
    
    Returns words assigned to this lesson.
    """
    settings = get_settings()
    
    # Load level word data
    file_name = _get_level_file_name(level)
    data_file = os.path.join(settings.data_dir, file_name)
    
    if not os.path.exists(data_file):
        raise HTTPException(status_code=404, detail=f"TOPIK level {level} word data not found")
    
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle nested structure: {level, words: [...]}
        all_words = data.get("words", []) if isinstance(data, dict) else data
        
        # Calculate word range for this lesson (lesson_id is 1-based)
        start_idx = (lesson_id - 1) * words_per_lesson
        end_idx = min(start_idx + words_per_lesson, len(all_words))
        
        if start_idx >= len(all_words):
            return {
                "lessonId": lesson_id,
                "level": level,
                "wordCount": 0,
                "words": []
            }
        
        lesson_words = all_words[start_idx:end_idx]
        
        # Transform to frontend format
        words = []
        for word in lesson_words:
            # Get examples from senses
            examples = []
            senses = word.get("senses", [])
            for sense in senses:
                sense_examples = sense.get("examples", [])
                examples.extend(sense_examples)
            
            words.append({
                "id": word.get("id", 0),
                "hangul": word.get("hangul", ""),
                "romanization": word.get("romanization", ""),
                "pos": word.get("pos", ""),
                "primaryMeaning": word.get("primary_meaning", ""),
                "senses": senses,
                "collocations": word.get("collocations", []),
                "examples": examples[:3],
                "topikLevel": level,
                "freqRank": word.get("id", 0),
                "lessonId": lesson_id
            })
        
        return {
            "lessonId": lesson_id,
            "level": level,
            "wordCount": len(words),
            "words": words
        }
    except Exception as e:
        logger.error(f"Failed to load lesson {lesson_id} words: {e}")
        raise HTTPException(status_code=500, detail="Failed to load word data")


