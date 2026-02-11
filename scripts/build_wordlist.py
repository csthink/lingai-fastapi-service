#!/usr/bin/env python3
"""
TOPIK 1 Wordlist Builder

This script builds the TOPIK Level 1 vocabulary dataset using:
1. Base word list (Korean frequency words)
2. LLM-generated content (meanings, examples, collocations)
3. Romanization generation

Usage:
    python scripts/build_wordlist.py --level 1 --output data/topik1_words.json
"""

import asyncio
import json
import argparse
import os
import sys
from typing import List, Dict, Any, Optional
from loguru import logger

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.services.llm_service import LLMService


# TOPIK 1 sample word list (first 100 words - POC)
# Full list should be loaded from official TOPIK vocabulary
TOPIK1_BASE_WORDS = [
    # Greetings and basics
    "안녕", "감사", "미안", "네", "아니요",
    # Pronouns
    "저", "나", "너", "우리", "여기",
    # Common nouns
    "사람", "학생", "선생님", "친구", "가족",
    "아버지", "어머니", "형", "누나", "동생",
    "집", "학교", "회사", "가게", "병원",
    "음식", "물", "밥", "고기", "과일",
    "책", "신문", "사진", "영화", "음악",
    "시간", "오늘", "내일", "어제", "아침",
    "저녁", "밤", "주", "월", "년",
    # Common verbs (dictionary form stems)
    "가다", "오다", "먹다", "마시다", "하다",
    "보다", "듣다", "읽다", "쓰다", "말하다",
    "배우다", "가르치다", "알다", "모르다", "좋다",
    "나쁘다", "크다", "작다", "많다", "적다",
    "있다", "없다", "사다", "팔다", "주다",
    "받다", "만나다", "기다리다", "걷다", "뛰다",
    # Numbers and counters
    "하나", "둘", "셋", "넷", "다섯",
    "여섯", "일곱", "여덟", "아홉", "열",
    # Common adjectives
    "예쁘다", "멋있다", "재미있다", "어렵다", "쉽다",
    "비싸다", "싸다", "덥다", "춥다", "맛있다",
    # Question words
    "뭐", "누구", "어디", "언제", "왜", "어떻게",
    # Colors
    "빨간색", "파란색", "노란색", "검은색", "흰색",
    # Weather
    "날씨", "비", "눈", "바람", "해",
]


def romanize_korean(hangul: str) -> str:
    """
    Convert Korean Hangul to Romanization (Revised Romanization).
    
    POC: Simple mapping, production should use proper library.
    """
    try:
        from korean_romanizer.romanizer import Romanizer
        r = Romanizer(hangul)
        return r.romanize()
    except ImportError:
        logger.warning("korean-romanizer not installed, using placeholder")
        return ""
    except Exception as e:
        logger.warning(f"Romanization failed for {hangul}: {e}")
        return ""


async def generate_word_content(
    llm_service: LLMService,
    word: str,
    level: int,
    lesson_id: int,
    word_id: int
) -> Optional[Dict[str, Any]]:
    """
    Generate complete word content using LLM.
    """
    logger.info(f"Generating content for: {word}")
    
    content = await llm_service.generate_word_content(word)
    
    if not content:
        logger.warning(f"Failed to generate content for: {word}")
        return None
    
    # Build complete word entry
    return {
        "id": word_id,
        "hangul": word,
        "romanization": romanize_korean(word),
        "pos": content.get("pos", ""),
        "primary_meaning": content.get("primary_meaning", ""),
        "senses": content.get("senses", []),
        "collocations": content.get("collocations", []),
        "examples": content.get("examples", []),
        "topik_level": level,
        "freq_rank": word_id,
        "lesson_id": lesson_id
    }


async def build_wordlist(
    level: int,
    output_path: str,
    words_per_lesson: int = 50,
    batch_size: int = 5,
    delay_between_batches: float = 1.0
):
    """
    Build complete wordlist for a TOPIK level.
    """
    settings = get_settings()
    llm_service = LLMService(settings)
    
    # Get base words for level
    if level == 1:
        base_words = TOPIK1_BASE_WORDS
    else:
        logger.error(f"Level {level} not yet supported")
        return
    
    logger.info(f"Building wordlist for TOPIK {level}")
    logger.info(f"Total words: {len(base_words)}")
    
    all_words = []
    failed_words = []
    
    # Process in batches
    for i in range(0, len(base_words), batch_size):
        batch = base_words[i:i + batch_size]
        logger.info(f"Processing batch {i // batch_size + 1}: {batch}")
        
        tasks = []
        for j, word in enumerate(batch):
            word_id = i + j + 1
            lesson_id = (word_id - 1) // words_per_lesson + 1
            tasks.append(
                generate_word_content(llm_service, word, level, lesson_id, word_id)
            )
        
        results = await asyncio.gather(*tasks)
        
        for word, result in zip(batch, results):
            if result:
                all_words.append(result)
            else:
                failed_words.append(word)
        
        # Delay to avoid rate limiting
        if i + batch_size < len(base_words):
            await asyncio.sleep(delay_between_batches)
    
    # Save results
    output_data = {
        "level": level,
        "version": "1.0.0",
        "total_words": len(all_words),
        "total_lessons": (len(all_words) - 1) // words_per_lesson + 1,
        "words_per_lesson": words_per_lesson,
        "words": all_words
    }
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved {len(all_words)} words to {output_path}")
    
    if failed_words:
        logger.warning(f"Failed to generate content for {len(failed_words)} words:")
        logger.warning(failed_words)
        
        # Save failed words for retry
        failed_path = output_path.replace(".json", "_failed.txt")
        with open(failed_path, "w", encoding="utf-8") as f:
            f.write("\n".join(failed_words))


def main():
    parser = argparse.ArgumentParser(description="Build TOPIK vocabulary dataset")
    parser.add_argument("--level", type=int, default=1, help="TOPIK level (1-6)")
    parser.add_argument("--output", type=str, default="data/topik1_words.json",
                        help="Output JSON file path")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Batch size for LLM calls")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between batches (seconds)")
    
    args = parser.parse_args()
    
    asyncio.run(build_wordlist(
        level=args.level,
        output_path=args.output,
        batch_size=args.batch_size,
        delay_between_batches=args.delay
    ))


if __name__ == "__main__":
    main()
