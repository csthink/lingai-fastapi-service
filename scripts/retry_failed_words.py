#!/usr/bin/env python3
"""
Retry failed words and add romanization to existing wordlist.

Usage:
    python scripts/retry_failed_words.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app.config import get_settings
from app.services.llm_service import LLMService


# Failed words from previous run
FAILED_WORDS = ['아버지', '고기', '나쁘다', '많다', '사다', '만나다', '빨간색', '노란색']


def romanize_korean(hangul: str) -> str:
    """Convert Korean Hangul to Romanization."""
    try:
        from korean_romanizer.romanizer import Romanizer
        r = Romanizer(hangul)
        return r.romanize()
    except ImportError:
        logger.warning("korean-romanizer not installed")
        return ""
    except Exception as e:
        logger.warning(f"Romanization failed for {hangul}: {e}")
        return ""


async def generate_word_content(llm_service: LLMService, word: str) -> dict:
    """Generate content for a single word."""
    logger.info(f"Generating content for: {word}")
    
    content = await llm_service.generate_word_content(word)
    
    if not content:
        logger.warning(f"Failed to generate content for: {word}")
        return None
    
    return {
        "hangul": word,
        "romanization": romanize_korean(word),
        "pos": content.get("pos", ""),
        "primary_meaning": content.get("primary_meaning", ""),
        "senses": content.get("senses", []),
        "collocations": content.get("collocations", []),
        "examples": content.get("examples", []),
    }


async def retry_failed_words():
    """Retry generating content for failed words."""
    settings = get_settings()
    llm_service = LLMService(settings)
    
    # Load existing wordlist
    wordlist_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "topik1_words.json"
    )
    
    with open(wordlist_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    existing_hanguls = {w["hangul"] for w in data["words"]}
    words_to_add = [w for w in FAILED_WORDS if w not in existing_hanguls]
    
    logger.info(f"Retrying {len(words_to_add)} failed words: {words_to_add}")
    
    # Generate content for each failed word (one at a time to avoid rate limits)
    new_words = []
    still_failed = []
    
    for word in words_to_add:
        try:
            content = await generate_word_content(llm_service, word)
            if content:
                # Assign ID and lesson_id
                next_id = max(w["id"] for w in data["words"]) + 1
                content["id"] = next_id
                content["topik_level"] = 1
                content["freq_rank"] = next_id
                content["lesson_id"] = (next_id - 1) // 50 + 1
                new_words.append(content)
                logger.info(f"✅ Successfully generated: {word}")
            else:
                still_failed.append(word)
        except Exception as e:
            logger.error(f"Error generating {word}: {e}")
            still_failed.append(word)
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)
    
    # Add new words to existing list
    if new_words:
        data["words"].extend(new_words)
        data["total_words"] = len(data["words"])
        data["total_lessons"] = (len(data["words"]) - 1) // 50 + 1
        
        # Save updated wordlist
        with open(wordlist_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Added {len(new_words)} words. Total: {data['total_words']}")
    
    if still_failed:
        logger.warning(f"❌ Still failed: {still_failed}")
    
    return len(new_words), still_failed


async def main():
    print("\n" + "="*60)
    print("🔄 Retrying failed words...")
    print("="*60)
    
    added, failed = await retry_failed_words()
    
    print("\n" + "="*60)
    print(f"📊 Results: Added {added} words")
    if failed:
        print(f"   Still failed: {failed}")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
