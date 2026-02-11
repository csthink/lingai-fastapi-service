#!/usr/bin/env python3
"""
Add romanization to all words in the wordlist and retry remaining failed words.

Usage:
    python scripts/add_romanization.py
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from app.config import get_settings
from app.services.llm_service import LLMService


# Remaining failed word
REMAINING_FAILED = ['빨간색']


def romanize_korean(hangul: str) -> str:
    """Convert Korean Hangul to Romanization."""
    try:
        from korean_romanizer.romanizer import Romanizer
        r = Romanizer(hangul)
        result = r.romanize()
        return result
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


async def main():
    print("\n" + "="*60)
    print("🔄 Adding romanization to all words...")
    print("="*60)
    
    settings = get_settings()
    llm_service = LLMService(settings)
    
    # Load existing wordlist
    wordlist_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "topik1_words.json"
    )
    
    with open(wordlist_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # Add romanization to existing words
    updated_count = 0
    for word in data["words"]:
        if not word.get("romanization"):
            rom = romanize_korean(word["hangul"])
            if rom:
                word["romanization"] = rom
                updated_count += 1
                print(f"  {word['hangul']} → {rom}")
    
    print(f"\n✅ Updated romanization for {updated_count} words")
    
    # Try to generate remaining failed words
    existing_hanguls = {w["hangul"] for w in data["words"]}
    words_to_add = [w for w in REMAINING_FAILED if w not in existing_hanguls]
    
    if words_to_add:
        print(f"\n🔄 Retrying {len(words_to_add)} remaining failed words...")
        
        for word in words_to_add:
            try:
                content = await generate_word_content(llm_service, word)
                if content:
                    next_id = max(w["id"] for w in data["words"]) + 1
                    content["id"] = next_id
                    content["topik_level"] = 1
                    content["freq_rank"] = next_id
                    content["lesson_id"] = (next_id - 1) // 50 + 1
                    data["words"].append(content)
                    data["total_words"] = len(data["words"])
                    print(f"  ✅ Added: {word}")
                else:
                    print(f"  ❌ Still failed: {word}")
            except Exception as e:
                logger.error(f"Error: {e}")
                print(f"  ❌ Error for {word}: {e}")
    
    # Save updated wordlist
    with open(wordlist_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n" + "="*60)
    print(f"📊 Final wordlist: {data['total_words']} words")
    print("="*60)
    
    # Show sample with romanization
    print("\n📝 Sample words with romanization:")
    for word in data["words"][:5]:
        print(f"  {word['hangul']} ({word['romanization']}) - {word['primary_meaning']}")


if __name__ == "__main__":
    asyncio.run(main())
