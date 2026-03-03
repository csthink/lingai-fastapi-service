"""
LLM Service
Provides LLM capabilities via Deepseek and Qwen (fallback)
"""
import json
from typing import Dict, Any, Optional, List
from loguru import logger
from openai import AsyncOpenAI

from app.config import Settings


def _extract_json_from_response(text: str) -> str:
    """
    Extract JSON from LLM response that may be wrapped in markdown code blocks.

    Handles formats like:
    - ```json\n{...}\n```
    - ```\n{...}\n```
    - Pure JSON
    """
    import re

    # Try to find JSON in markdown code block
    # Pattern matches ```json or ``` followed by content and closing ```
    pattern = r'```(?:json)?\s*\n?([\s\S]*?)\n?```'
    match = re.search(pattern, text)

    if match:
        return match.group(1).strip()

    # If no markdown block, return as-is (might be pure JSON)
    return text.strip()


class LLMService:
    """
    LLM Service for dictionary AI and content generation.
    
    Primary: Deepseek Chat
    Fallback: Alibaba Cloud Qwen
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.timeout = settings.llm_timeout
        
        # Initialize Deepseek client
        if settings.deepseek_api_key:
            self.deepseek_client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url
            )
        else:
            self.deepseek_client = None
            logger.warning("Deepseek API key not configured")
        
        # Initialize Qwen client (fallback)
        if settings.qwen_api_key:
            self.qwen_client = AsyncOpenAI(
                api_key=settings.qwen_api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        else:
            self.qwen_client = None
            logger.warning("Qwen API key not configured")
    
    async def _call_deepseek(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """
        Call Deepseek Chat API.
        
        Returns response content or None on failure.
        """
        if not self.deepseek_client:
            return None
        
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = await self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                timeout=self.timeout
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Deepseek API call failed: {e}")
            return None
    
    async def _call_qwen(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """
        Call Qwen API (fallback).
        
        Returns response content or None on failure.
        """
        if not self.qwen_client:
            return None
        
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = await self.qwen_client.chat.completions.create(
                model="qwen-turbo",
                messages=messages,
                timeout=self.timeout
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Qwen API call failed: {e}")
            return None
    
    async def _call_llm(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """
        Call LLM with automatic fallback.
        
        Tries Qwen first (more stable), then Deepseek on failure.
        """
        # Try Qwen first (more stable and faster)
        result = await self._call_qwen(prompt, system_prompt)
        if result:
            return result
        
        # Fallback to Deepseek
        logger.info("Falling back to Deepseek")
        return await self._call_deepseek(prompt, system_prompt)
    
    async def stream_llm(self, prompt: str, system_prompt: str = ""):
        """
        Stream LLM response token by token.
        
        Yields content chunks as they are generated.
        Uses Qwen first, falls back to Deepseek.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Try Qwen streaming first
        if self.qwen_client:
            try:
                stream = await self.qwen_client.chat.completions.create(
                    model="qwen-turbo",
                    messages=messages,
                    stream=True,
                    timeout=self.timeout
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except Exception as e:
                logger.warning(f"Qwen streaming failed: {e}")
        
        # Fallback to Deepseek streaming
        if self.deepseek_client:
            try:
                stream = await self.deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages,
                    stream=True,
                    timeout=self.timeout
                )
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            except Exception as e:
                logger.warning(f"Deepseek streaming failed: {e}")
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str = ""
    ) -> Optional[str]:
        """
        Multi-turn chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            
        Returns:
            Assistant's response content or None on failure
        """
        if not messages:
            return None
        
        # Build full message list with system prompt
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        # Try Qwen first
        if self.qwen_client:
            try:
                response = await self.qwen_client.chat.completions.create(
                    model="qwen-turbo",
                    messages=full_messages,
                    timeout=self.timeout
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"Qwen chat completion failed: {e}")
        
        # Fallback to Deepseek
        if self.deepseek_client:
            try:
                response = await self.deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=full_messages,
                    timeout=self.timeout
                )
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"Deepseek chat completion failed: {e}")
        
        return None
    
    async def get_dict_supplement(
        self,
        word: str,
        direction: str = "ko2zh"
    ) -> Dict[str, Any]:
        """
        Get AI-supplemented dictionary information.
        
        Args:
            word: Word to look up
            direction: Translation direction (ko2zh or zh2ko)
            
        Returns:
            Dict with ai_meaning, ai_examples, synonyms, antonyms, detailed_content
        """
        if direction == "ko2zh":
            prompt = f"""请为韩语单词"{word}"提供详细的词典解析（JSON格式）：

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
- 仅输出JSON，无其他内容

示例输出结构：
{{"ai_meaning": "爱/爱情", "word_type": "名词", "hanja": "愛", "composition": "汉字词，对应'愛'", "meanings": [{{"type": "具体义", "explanation": "对人或事物的喜爱感情"}}], "collocations": [{{"phrase": "사랑하다", "meaning": "爱（动词形式）"}}], "ai_examples": [{{"category": "日常对话", "ko": "사랑해요", "zh": "我爱你"}}], "synonyms": [{{"word": "애정", "meaning": "爱情", "difference": "较正式"}}], "antonyms": [{{"word": "미움", "meaning": "憎恨"}}], "related_words": [{{"word": "사랑스럽다", "meaning": "可爱的"}}], "tips": "韩语中表达爱意时常用'사랑해요'。"}}"""
        else:
            prompt = f"""请为中文词"{word}"提供韩语翻译的详细解析（JSON格式）：

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
11. tips: 实用知识/使用提示（中文描述）

重要要求：
- 所有解释性文字（explanation, meaning, difference, tips等）必须使用中文
- 仅韩语内容使用韩语（word, phrase, ko, example_ko等）
- 仅输出JSON，无其他内容

示例输出结构：
{{"ai_meaning": "병원", "word_type": "名词", "hanja": "病院", "composition": "병(病) + 원(院)", "meanings": [{{"type": "一般含义", "explanation": "提供医疗服务的设施"}}], "collocations": [{{"phrase": "병원에 가다", "meaning": "去医院"}}], "ai_examples": [{{"category": "日常对话", "ko": "병원에 가야 해요", "zh": "我得去医院"}}], "synonyms": [{{"word": "의원", "meaning": "诊所", "difference": "规模较小"}}], "antonyms": [], "related_words": [{{"word": "의사", "meaning": "医生"}}], "tips": "韩国医院分为大型综合医院(병원)和小型诊所(의원)。"}}"""
        
        system_prompt = """你是专业的韩语词典专家和语言学者，为中文母语者提供详尽准确的韩语词汇解析。
你的解答要：
1. 内容详尽，覆盖词汇的各个方面
2. 例句地道自然，涵盖多种使用场景
3. 清晰说明近义词的细微差别
4. 提供实用的文化背景或学习提示"""
        
        result = await self._call_llm(prompt, system_prompt)
        
        if not result:
            return {
                "ai_meaning": None,
                "ai_examples": [],
                "synonyms": [],
                "antonyms": [],
                "word_type": None,
                "hanja": None,
                "composition": None,
                "meanings": [],
                "collocations": [],
                "related_words": [],
                "tips": None
            }
        
        try:
            # Extract JSON from potential markdown wrapper
            json_text = _extract_json_from_response(result)
            # Parse JSON response
            parsed = json.loads(json_text)
            return {
                "ai_meaning": parsed.get("ai_meaning"),
                "word_type": parsed.get("word_type"),
                "hanja": parsed.get("hanja"),
                "composition": parsed.get("composition"),
                "meanings": parsed.get("meanings", []),
                "collocations": parsed.get("collocations", []),
                "ai_examples": parsed.get("ai_examples", []),
                "synonyms": parsed.get("synonyms", []),
                "antonyms": parsed.get("antonyms", []),
                "related_words": parsed.get("related_words", []),
                "tips": parsed.get("tips")
            }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return {
                "ai_meaning": None,
                "ai_examples": [],
                "synonyms": [],
                "antonyms": [],
                "word_type": None,
                "hanja": None,
                "composition": None,
                "meanings": [],
                "collocations": [],
                "related_words": [],
                "tips": None
            }
    
    async def generate_mnemonic(
        self,
        word: str,
        meaning: str
    ) -> Dict[str, Any]:
        """
        Generate mnemonic content for vocabulary learning.
        
        Args:
            word: Korean word
            meaning: Chinese meaning
            
        Returns:
            Dict with examples, synonyms, antonyms
        """
        prompt = f"""为韩语单词"{word}"（释义：{meaning}）生成学习辅助内容（JSON格式）：

1. examples: 3个TOPIK考试风格的例句，每个含ko（韩文）和zh（中文翻译）
2. synonyms: 1-3个同义词（韩文带释义）
3. antonyms: 0-2个反义词（韩文带释义）

要求：
- 例句必须包含目标词
- 难度适合TOPIK考试
- 仅输出JSON"""
        
        system_prompt = "你是TOPIK韩语考试内容专家，擅长生成教学用例句和关联词汇。"
        
        result = await self._call_llm(prompt, system_prompt)
        
        if not result:
            return {"examples": [], "synonyms": [], "antonyms": []}
        
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"examples": [], "synonyms": [], "antonyms": []}
    
    async def generate_word_content(
        self,
        word: str
    ) -> Dict[str, Any]:
        """
        Generate complete word content for vocabulary building.
        
        Used by build_wordlist.py script.
        
        Args:
            word: Korean word (hangul)
            
        Returns:
            Dict with primary_meaning, senses, examples, collocations
        """
        prompt = f"""请为韩语单词"{word}"生成以下内容（JSON格式）：

1. primary_meaning: 最常用中文释义（10字以内）
2. senses: 所有义项列表，每项含：
   - meaning: 中文释义
   - examples: 1个例句（含ko和zh）
3. examples: 2个TOPIK风格例句，每个含ko和zh
4. collocations: 常用搭配（最多3个韩文短语）

要求：
- 例句必须包含目标词原形或词形变化
- 释义简洁准确
- 输出纯JSON，无解释

示例：
{{"primary_meaning": "学习", "senses": [{{"meaning": "学习，研习", "examples": [{{"ko": "한국어를 공부해요", "zh": "学习韩语"}}]}}], "examples": [{{"ko": "열심히 공부하세요", "zh": "请努力学习"}}], "collocations": ["공부하다", "공부를 하다"]}}"""
        
        system_prompt = "你是韩语词典编辑专家，生成的内容用于韩语学习App。"
        
        result = await self._call_llm(prompt, system_prompt)
        
        if not result:
            return None
        
        try:
            parsed = json.loads(result)
            # Validate: primary_meaning must exist
            if not parsed.get("primary_meaning"):
                return None
            return parsed
        except json.JSONDecodeError:
            return None

    async def quick_translate(self, word: str, direction: str) -> str:
        """
        Quick translate a word - returns only the translation.
        
        Args:
            word: Word to translate
            direction: ko2zh or zh2ko
            
        Returns:
            Translation string
        """
        if direction == "ko2zh":
            prompt = f'请将韩语词"{word}"翻译成中文，只返回中文翻译，不要解释。如果有多个含义用斜杠分隔。'
        else:
            prompt = f'请将中文词"{word}"翻译成韩语，只返回韩语翻译，不要解释。如果有多个含义用斜杠分隔。'
        
        system_prompt = "你是专业的韩中翻译，只返回翻译结果，不要任何解释和标点符号。"
        
        result = await self._call_llm(prompt, system_prompt)
        
        # Clean up result - remove quotes and extra whitespace
        if result:
            result = result.strip().strip('"').strip("'").strip()
        
        return result or "翻译失败"

    async def close(self):
        """Close underlying HTTP clients on shutdown."""
        if self.deepseek_client:
            await self.deepseek_client.close()
        if self.qwen_client:
            await self.qwen_client.close()
