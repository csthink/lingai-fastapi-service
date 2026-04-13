#!/usr/bin/env python
"""
词典缓存预热脚本
批量生成TOPIK词库词典内容并存入Redis缓存

支持:
- 幂等性重试（已缓存的词跳过）
- 网络错误重试
- 分级别预热（TOPIK I / II / 常考词）
- 进度保存和恢复
"""
import asyncio
import json
import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from app.config import get_settings
from app.services.llm_service import LLMService
from app.services.redis_cache import RedisCache


# Configuration
BATCH_SIZE = 3  # Concurrent requests (conservative to avoid rate limiting)
DELAY_BETWEEN_WORDS = 0.5  # Seconds between words
DELAY_BETWEEN_BATCHES = 2.0  # Seconds between batches
MAX_RETRIES = 3


def load_words_from_file(filepath: str) -> List[Dict]:
    """Load words from a single JSON file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('words', [])
    except Exception as e:
        logger.error(f"Failed to load {filepath}: {e}")
        return []


def get_cached_words(cache: RedisCache) -> Set[str]:
    """Get set of already cached words."""
    try:
        cached = set()
        prefix = getattr(cache, "_prefix", "").strip()
        match_pattern = f"{prefix}:dict_search:*:ko2zh" if prefix else "dict_search:*:ko2zh"

        for key in cache._client.scan_iter(match=match_pattern, count=1000):
            # Extract word from key
            normalized_key = key.decode() if isinstance(key, bytes) else key
            parts = normalized_key.split(':')
            if len(parts) >= 3:
                cached.add(parts[-2])
        return cached
    except Exception as e:
        logger.warning(f"Failed to get cached keys: {e}")
        return set()


async def preload_single_word(
    word: str,
    llm_service: LLMService,
    cache: RedisCache,
    direction: str = "ko2zh"
) -> bool:
    """
    Preload a single word's dictionary content.
    Returns True on success, False on failure.
    """
    cache_key = f"dict_search:{word}:{direction}"
    
    # Idempotent check - skip if already cached
    if cache.exists(cache_key):
        logger.debug(f"Already cached: {word}")
        return True
    
    for retry in range(MAX_RETRIES):
        try:
            # Call LLM for dictionary content (matches dict_ai.py format)
            result = await llm_service.get_dict_supplement(word, direction)
            
            # Build response matching DictSearchResponse structure with camelCase
            response = {
                "source": "ai",
                "query": word,
                "direction": direction,
                "results": [],
                "aiSupplement": {
                    "aiMeaning": result.get("ai_meaning"),
                    "wordType": result.get("word_type"),
                    "hanja": result.get("hanja"),
                    "composition": result.get("composition"),
                    "meanings": result.get("meanings", []),
                    "collocations": result.get("collocations", []),
                    "aiExamples": result.get("ai_examples", []),
                    "synonyms": result.get("synonyms", []),
                    "antonyms": result.get("antonyms", []),
                    "relatedWords": result.get("related_words", []),
                    "tips": result.get("tips"),
                    "error": None
                }
            }
            
            # Cache the result (no TTL = permanent)
            cache.set(cache_key, response)
            logger.info(f"✓ Cached: {word}")
            return True
            
        except Exception as e:
            logger.warning(f"Retry {retry+1}/{MAX_RETRIES} failed for '{word}': {e}")
            if retry < MAX_RETRIES - 1:
                await asyncio.sleep(2 ** retry)  # Exponential backoff
    
    logger.error(f"✗ Failed after {MAX_RETRIES} retries: {word}")
    return False


async def preload_level(
    level_name: str,
    words: List[Dict],
    llm_service: LLMService,
    cache: RedisCache
) -> Dict:
    """Preload all words for a TOPIK level."""
    logger.info(f"=== 开始预热 {level_name} ({len(words)} 词) ===")
    
    # Get already cached words
    cached_words = get_cached_words(cache)
    
    # Filter to uncached words
    to_process = []
    for w in words:
        hangul = w.get('hangul', '')
        if hangul and hangul not in cached_words:
            to_process.append(hangul)
    
    already_cached = len(words) - len(to_process)
    logger.info(f"已缓存: {already_cached}, 待处理: {len(to_process)}")
    
    if not to_process:
        logger.info(f"{level_name} 已全部缓存!")
        return {"level": level_name, "total": len(words), "cached": len(words), "new": 0, "failed": 0}
    
    # Process words one by one with progress
    success_count = 0
    failed_words = []
    
    for i, word in enumerate(to_process, 1):
        result = await preload_single_word(word, llm_service, cache)
        
        if result:
            success_count += 1
        else:
            failed_words.append(word)
        
        # Progress log every 10 words
        if i % 10 == 0:
            progress = i / len(to_process) * 100
            logger.info(f"进度: {i}/{len(to_process)} ({progress:.1f}%) - 成功: {success_count}")
        
        # Delay between requests
        await asyncio.sleep(DELAY_BETWEEN_WORDS)
    
    # Final stats
    stats = {
        "level": level_name,
        "total": len(words),
        "cached": already_cached + success_count,
        "new": success_count,
        "failed": len(failed_words)
    }
    
    logger.info(f"=== {level_name} 预热完成 ===")
    logger.info(f"总词数: {stats['total']}, 已缓存: {stats['cached']}, "
                f"新增: {stats['new']}, 失败: {stats['failed']}")
    
    if failed_words:
        logger.warning(f"失败词汇: {failed_words[:20]}...")
    
    return stats


async def main():
    """Main preload function."""
    parser = argparse.ArgumentParser(description='词典缓存预热')
    parser.add_argument('--level', choices=['topik1', 'topik2', 'common', 'all'],
                        default='topik1', help='预热级别 (默认: topik1)')
    parser.add_argument('--limit', type=int, default=0,
                        help='限制处理词数 (0=全部)')
    args = parser.parse_args()
    
    logger.info(f"=== 词典缓存预热开始 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ===")
    logger.info(f"级别: {args.level}, 限制: {args.limit or '无'}")
    
    # Initialize services
    settings = get_settings()
    llm_service = LLMService(settings)
    cache = RedisCache(settings)
    
    # Define level files
    level_files = {
        'topik1': ('data/topik_i_words.json', 'TOPIK I'),
        'topik2': ('data/topik_ii_words.json', 'TOPIK II'),
        'common': ('data/common_words.json', '常考单词')
    }
    
    levels_to_process = []
    if args.level == 'all':
        levels_to_process = list(level_files.keys())
    else:
        levels_to_process = [args.level]
    
    all_stats = []
    
    for level_key in levels_to_process:
        filepath, level_name = level_files[level_key]
        words = load_words_from_file(filepath)
        
        if args.limit > 0:
            words = words[:args.limit]
        
        stats = await preload_level(level_name, words, llm_service, cache)
        all_stats.append(stats)
    
    # Final summary
    logger.info("=== 预热任务完成 ===")
    total_words = sum(s['total'] for s in all_stats)
    total_cached = sum(s['cached'] for s in all_stats)
    total_new = sum(s['new'] for s in all_stats)
    total_failed = sum(s['failed'] for s in all_stats)
    
    logger.info(f"总词数: {total_words}")
    logger.info(f"已缓存: {total_cached} ({total_cached/total_words*100:.1f}%)")
    logger.info(f"新增: {total_new}")
    logger.info(f"失败: {total_failed}")


if __name__ == "__main__":
    asyncio.run(main())
