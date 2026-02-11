#!/usr/bin/env python3
"""
LingAI Service Connectivity Test

Tests connectivity to:
1. Deepseek API
2. Qwen API (fallback)
3. Edge TTS (development TTS)

Usage:
    cd lingai-fastapi-service
    source venv/bin/activate
    python scripts/test_services.py
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger


async def test_deepseek():
    """Test Deepseek API connectivity."""
    print("\n" + "="*50)
    print("🔍 Testing Deepseek API...")
    print("="*50)
    
    from app.config import get_settings
    settings = get_settings()
    
    if not settings.deepseek_api_key:
        print("❌ DEEPSEEK_API_KEY not configured")
        return False
    
    print(f"   API Key: {settings.deepseek_api_key[:8]}...{settings.deepseek_api_key[-4:]}")
    print(f"   Base URL: {settings.deepseek_base_url}")
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        
        response = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": "请用一句话介绍韩语。"}],
            max_tokens=50,
            timeout=15
        )
        
        result = response.choices[0].message.content
        print(f"✅ Deepseek API working!")
        print(f"   Response: {result}")
        return True
    except Exception as e:
        print(f"❌ Deepseek API failed: {e}")
        return False


async def test_qwen():
    """Test Qwen API connectivity."""
    print("\n" + "="*50)
    print("🔍 Testing Qwen API (backup)...")
    print("="*50)
    
    from app.config import get_settings
    settings = get_settings()
    
    if not settings.qwen_api_key:
        print("⚠️  QWEN_API_KEY not configured (optional backup)")
        return None
    
    print(f"   API Key: {settings.qwen_api_key[:8]}...{settings.qwen_api_key[-4:]}")
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.qwen_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        
        response = await client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "user", "content": "请用一句话介绍韩语。"}],
            max_tokens=50,
            timeout=15
        )
        
        result = response.choices[0].message.content
        print(f"✅ Qwen API working!")
        print(f"   Response: {result}")
        return True
    except Exception as e:
        print(f"❌ Qwen API failed: {e}")
        return False


async def test_tts():
    """Test Edge TTS (development fallback)."""
    print("\n" + "="*50)
    print("🔍 Testing Edge TTS (Korean)...")
    print("="*50)
    
    try:
        import edge_tts
        
        text = "안녕하세요"  # Hello in Korean
        voice = "ko-KR-SunHiNeural"
        
        print(f"   Text: {text}")
        print(f"   Voice: {voice}")
        
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        
        if len(audio_data) > 0:
            # Save test audio
            test_audio_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "test_audio.mp3"
            )
            os.makedirs(os.path.dirname(test_audio_path), exist_ok=True)
            
            with open(test_audio_path, "wb") as f:
                f.write(audio_data)
            
            print(f"✅ Edge TTS working!")
            print(f"   Audio size: {len(audio_data)} bytes")
            print(f"   Saved to: {test_audio_path}")
            return True
        else:
            print("❌ Edge TTS returned empty audio")
            return False
            
    except ImportError:
        print("❌ edge-tts package not installed")
        return False
    except Exception as e:
        print(f"❌ Edge TTS failed: {e}")
        return False


async def test_llm_service():
    """Test integrated LLM service with failover."""
    print("\n" + "="*50)
    print("🔍 Testing LLM Service (word content generation)...")
    print("="*50)
    
    try:
        from app.config import get_settings
        from app.services.llm_service import LLMService
        
        settings = get_settings()
        llm_service = LLMService(settings)
        
        # Test dictionary supplement
        print("   Testing dict_supplement for '사랑' (love)...")
        result = await llm_service.get_dict_supplement("사랑", "ko2zh")
        
        if result.get("ai_meaning"):
            print(f"✅ LLM Service working!")
            print(f"   Meaning: {result.get('ai_meaning')}")
            print(f"   Examples: {len(result.get('ai_examples', []))} items")
            print(f"   Synonyms: {result.get('synonyms', [])}")
            return True
        else:
            print("⚠️  LLM returned empty result (API may be unavailable)")
            return False
            
    except Exception as e:
        print(f"❌ LLM Service failed: {e}")
        return False


async def main():
    """Run all service tests."""
    print("\n" + "#"*60)
    print("#  LingAI Backend - Service Connectivity Test")
    print("#"*60)
    
    # Check .env location
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(backend_dir, ".env")
    app_env_path = os.path.join(backend_dir, "app", ".env")
    
    if os.path.exists(app_env_path) and not os.path.exists(env_path):
        print(f"\n⚠️  Note: .env found in app/ directory")
        print(f"   Moving to correct location: {env_path}")
        import shutil
        shutil.copy(app_env_path, env_path)
        print("   Done!")
    
    results = {}
    
    # Test each service
    results["Deepseek"] = await test_deepseek()
    results["Qwen"] = await test_qwen()
    results["Edge TTS"] = await test_tts()
    results["LLM Service"] = await test_llm_service()
    
    # Summary
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)
    
    for service, status in results.items():
        if status is True:
            icon = "✅"
        elif status is False:
            icon = "❌"
        else:
            icon = "⚠️"
        print(f"   {icon} {service}")
    
    # Check critical services
    critical_ok = results["Deepseek"] or results["Qwen"]
    tts_ok = results["Edge TTS"]
    
    print("\n" + "-"*60)
    if critical_ok and tts_ok:
        print("🎉 All critical services are working! Ready to proceed.")
        return 0
    else:
        if not critical_ok:
            print("❌ LLM service not available. Check API keys.")
        if not tts_ok:
            print("❌ TTS service not available.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
