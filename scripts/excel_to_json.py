#!/usr/bin/env python3
"""
Excel to JSON Wordlist Converter

Reads Excel files with vocabulary data (单词, 词性, 中文) and generates
JSON files with LLM-enhanced content (examples, collocations, etc.)

Usage:
    python scripts/excel_to_json.py --input data/topik_i_words.xlsx --output data/topik_i_words.json --level 1
"""

import asyncio
import json
import argparse
import os
import sys
from typing import List, Dict, Any, Optional
from loguru import logger
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.services.llm_service import LLMService


def romanize_korean(hangul: str) -> str:
    """Convert Korean Hangul to Romanization."""
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


def read_excel(file_path: str) -> List[Dict[str, str]]:
    """Read Excel file and return list of word entries."""
    logger.info(f"Reading Excel file: {file_path}")
    
    df = pd.read_excel(file_path)
    
    # Normalize column names
    df.columns = df.columns.str.strip()
    
    # Map possible column names
    column_mapping = {
        '单词': 'hangul',
        '词性': 'pos', 
        '中文': 'meaning'
    }
    
    # Check required columns exist
    for col in ['单词', '词性', '中文']:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    
    words = []
    for _, row in df.iterrows():
        hangul = str(row['单词']).strip()
        pos = str(row['词性']).strip() if pd.notna(row['词性']) else ''
        meaning = str(row['中文']).strip() if pd.notna(row['中文']) else ''
        
        if hangul and hangul != 'nan':
            words.append({
                'hangul': hangul,
                'pos': pos,
                'meaning': meaning
            })
    
    logger.info(f"Read {len(words)} words from Excel")
    return words


async def generate_word_content(
    llm_service: LLMService,
    word_data: Dict[str, str],
    level: int,
    lesson_id: int,
    word_id: int
) -> Optional[Dict[str, Any]]:
    """Generate complete word content using LLM."""
    word = word_data['hangul']
    logger.info(f"Generating content for: {word} ({word_id})")
    
    try:
        content = await llm_service.generate_word_content(word)
        
        if not content:
            logger.warning(f"Failed to generate content for: {word}")
            # Return basic entry without LLM content
            return {
                "id": word_id,
                "hangul": word,
                "romanization": romanize_korean(word),
                "pos": word_data['pos'],
                "primary_meaning": word_data['meaning'],
                "senses": [],
                "collocations": [],
                "examples": [],
                "topik_level": level,
                "freq_rank": word_id,
                "lesson_id": lesson_id
            }
        
        # Build complete word entry
        return {
            "id": word_id,
            "hangul": word,
            "romanization": romanize_korean(word),
            "pos": word_data['pos'] or content.get("pos", ""),
            "primary_meaning": word_data['meaning'] or content.get("primary_meaning", ""),
            "senses": content.get("senses", []),
            "collocations": content.get("collocations", []),
            "examples": content.get("examples", []),
            "topik_level": level,
            "freq_rank": word_id,
            "lesson_id": lesson_id
        }
    except Exception as e:
        logger.error(f"Error generating content for {word}: {e}")
        return None


async def build_wordlist(
    input_path: str,
    output_path: str,
    level: int,
    words_per_lesson: int = 50,
    batch_size: int = 5,
    delay_between_batches: float = 1.0,
    skip_llm: bool = False
):
    """Build complete wordlist from Excel file with idempotency support."""
    settings = get_settings()
    llm_service = LLMService(settings)
    
    # Read Excel
    base_words = read_excel(input_path)
    
    logger.info(f"Building wordlist for TOPIK level {level}")
    logger.info(f"Total words in Excel: {len(base_words)}")
    
    # Load existing data for idempotency
    existing_words: Dict[str, dict] = {}
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                for word in existing_data.get('words', []):
                    hangul = word.get('hangul', '')
                    # Consider word complete if it has examples or senses
                    has_content = bool(word.get('examples')) or bool(word.get('senses'))
                    if hangul and has_content:
                        existing_words[hangul] = word
            logger.info(f"Loaded {len(existing_words)} existing words with LLM content")
        except Exception as e:
            logger.warning(f"Failed to load existing data: {e}")
    
    all_words = []
    failed_words = []
    skipped_count = 0
    
    if skip_llm:
        # Fast mode: just convert without LLM
        logger.info("Skip LLM mode: generating basic entries only")
        for i, word_data in enumerate(base_words):
            word_id = i + 1
            lesson_id = (word_id - 1) // words_per_lesson + 1
            entry = {
                "id": word_id,
                "hangul": word_data['hangul'],
                "romanization": romanize_korean(word_data['hangul']),
                "pos": word_data['pos'],
                "primary_meaning": word_data['meaning'],
                "senses": [],
                "collocations": [],
                "examples": [],
                "topik_level": level,
                "freq_rank": word_id,
                "lesson_id": lesson_id
            }
            all_words.append(entry)
    else:
        # Full mode: with LLM content generation
        for i in range(0, len(base_words), batch_size):
            batch = base_words[i:i + batch_size]
            
            # Check which words need processing
            words_to_process = []
            for j, word_data in enumerate(batch):
                word_id = i + j + 1
                hangul = word_data['hangul']
                
                # Skip if already has content (idempotency)
                if hangul in existing_words:
                    existing_entry = existing_words[hangul]
                    existing_entry['id'] = word_id  # Update ID
                    existing_entry['lesson_id'] = (word_id - 1) // words_per_lesson + 1
                    all_words.append(existing_entry)
                    skipped_count += 1
                else:
                    words_to_process.append((j, word_data, word_id))
            
            if not words_to_process:
                continue
            
            logger.info(f"Processing batch {i // batch_size + 1}: {[w[1]['hangul'] for w in words_to_process]} (skipped {len(batch) - len(words_to_process)})")
            
            tasks = []
            for j, word_data, word_id in words_to_process:
                lesson_id = (word_id - 1) // words_per_lesson + 1
                tasks.append(
                    generate_word_content(llm_service, word_data, level, lesson_id, word_id)
                )
            
            results = await asyncio.gather(*tasks)
            
            for (j, word_data, word_id), result in zip(words_to_process, results):
                if result:
                    all_words.append(result)
                else:
                    failed_words.append(word_data['hangul'])
            
            # Save intermediate results every 10 batches for crash recovery
            if (i // batch_size + 1) % 10 == 0:
                _save_intermediate(output_path, all_words, level, words_per_lesson)
                logger.info(f"Saved intermediate checkpoint: {len(all_words)} words")
            
            # Delay to avoid rate limiting
            if i + batch_size < len(base_words):
                await asyncio.sleep(delay_between_batches)
    
    if skipped_count > 0:
        logger.info(f"Skipped {skipped_count} words with existing content (idempotency)")
    
    # Save final results
    _save_final_results(output_path, all_words, failed_words, level, words_per_lesson)


def _save_intermediate(output_path: str, words: list, level: int, words_per_lesson: int):
    """Save intermediate results for crash recovery."""
    # Sort by ID to maintain order
    sorted_words = sorted(words, key=lambda w: w.get('id', 0))
    
    output_data = {
        "level": level,
        "version": "1.0.0",
        "total_words": len(sorted_words),
        "total_lessons": (len(sorted_words) - 1) // words_per_lesson + 1 if sorted_words else 0,
        "words_per_lesson": words_per_lesson,
        "words": sorted_words
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)


def _save_final_results(output_path: str, all_words: list, failed_words: list, level: int, words_per_lesson: int):
    """Save final results with failed words log."""
    # Sort by ID to maintain order
    sorted_words = sorted(all_words, key=lambda w: w.get('id', 0))
    
    output_data = {
        "level": level,
        "version": "1.0.0",
        "total_words": len(sorted_words),
        "total_lessons": (len(sorted_words) - 1) // words_per_lesson + 1 if sorted_words else 0,
        "words_per_lesson": words_per_lesson,
        "words": sorted_words
    }
    
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved {len(sorted_words)} words to {output_path}")
    
    if failed_words:
        logger.warning(f"Failed to generate content for {len(failed_words)} words:")
        logger.warning(failed_words)
        
        # Save failed words for retry
        failed_path = output_path.replace(".json", "_failed.txt")
        with open(failed_path, "w", encoding="utf-8") as f:
            f.write("\n".join(failed_words))


def main():
    parser = argparse.ArgumentParser(description="Convert Excel vocabulary to JSON with LLM enhancement")
    parser.add_argument("--input", type=str, required=True, help="Input Excel file path")
    parser.add_argument("--output", type=str, required=True, help="Output JSON file path")
    parser.add_argument("--level", type=int, default=1, help="TOPIK level (1=TOPIK I, 2=TOPIK II, 0=Common)")
    parser.add_argument("--batch-size", type=int, default=5, help="Batch size for LLM calls")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between batches (seconds)")
    parser.add_argument("--skip-llm", action="store_true", help="Skip LLM generation, create basic entries only")
    
    args = parser.parse_args()
    
    asyncio.run(build_wordlist(
        input_path=args.input,
        output_path=args.output,
        level=args.level,
        batch_size=args.batch_size,
        delay_between_batches=args.delay,
        skip_llm=args.skip_llm
    ))


if __name__ == "__main__":
    main()
