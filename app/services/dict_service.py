"""
Dictionary Service
Provides local dictionary search functionality
"""
import re
from typing import List, Dict, Any, Optional


class DictService:
    """
    Local dictionary search service.

    Supports:
    - Korean → Chinese (exact match on hangul)
    - Chinese → Korean (search in meanings, return Top N by freq_rank)
    """

    def __init__(self, words_data: List[Dict[str, Any]]):
        """
        Initialize with word list data.

        Args:
            words_data: List of word entries from topik JSON
        """
        self.words = words_data

    def detect_language(self, text: str) -> str:
        """
        Detect input language.

        Args:
            text: Input text to detect

        Returns:
            'ko' for Korean, 'zh' for Chinese
        """
        # Korean Hangul Unicode range: AC00-D7AF (syllables), 1100-11FF (Jamo)
        korean_pattern = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF]')

        if korean_pattern.search(text):
            return 'ko'
        return 'zh'

    def search_korean(self, hangul: str) -> List[Dict[str, Any]]:
        """
        Search by Korean word (exact match).

        Args:
            hangul: Korean word to search

        Returns:
            List of matching word entries
        """
        results = []
        hangul_lower = hangul.strip()

        for word in self.words:
            if word.get('hangul', '') == hangul_lower:
                results.append(word)

        return results

    def search_chinese(self, meaning: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Search by Chinese meaning.

        Searches in:
        - primary_meaning
        - senses[].meaning

        Args:
            meaning: Chinese text to search
            limit: Maximum results to return (default 3)

        Returns:
            List of matching word entries, sorted by freq_rank
        """
        results = []
        search_text = meaning.strip()

        for word in self.words:
            matched = False

            # Check primary_meaning
            primary = word.get('primary_meaning', '')
            if search_text in primary:
                matched = True

            # Check senses
            if not matched:
                senses = word.get('senses', [])
                for sense in senses:
                    sense_meaning = sense.get('meaning', '')
                    if search_text in sense_meaning:
                        matched = True
                        break

            if matched:
                results.append(word)

        # Sort by freq_rank (lower is more common)
        results.sort(key=lambda w: w.get('freq_rank', 9999))

        return results[:limit]

    def search(self, query: str, direction: str = 'auto', limit: int = 3) -> Dict[str, Any]:
        """
        Universal search method.

        Args:
            query: Search query (Korean or Chinese)
            direction: 'auto', 'ko2zh', or 'zh2ko'
            limit: Max results for zh2ko search

        Returns:
            Dict with direction and results
        """
        query = query.strip()

        # Determine direction
        if direction == 'auto':
            detected_lang = self.detect_language(query)
            actual_direction = 'ko2zh' if detected_lang == 'ko' else 'zh2ko'
        else:
            actual_direction = direction

        # Search based on direction
        if actual_direction == 'ko2zh':
            results = self.search_korean(query)
        else:
            results = self.search_chinese(query, limit=limit)

        return {
            'direction': actual_direction,
            'results': results
        }
