import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.services.redis_cache import RedisCache
from app.services.redis_service import RedisService
from scripts.preload_dict_cache import get_cached_words


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["lingai-lg020", ""])
async def test_runtime_and_preloader_share_json_keys(prefix):
    settings = Settings(_env_file=None, redis_prefix=prefix)
    service = RedisService(settings)
    service.available = True
    service.client = AsyncMock()
    payload = {"query": "학교", "aiSupplement": {"aiMeaning": "学校"}}
    key = "dict_search:학교:ko2zh"
    expected = f"{prefix}:{key}" if prefix else key
    assert await service.set_json(key, payload)
    written_key, written_payload = service.client.set.call_args.args
    assert written_key == expected
    service.client.get.return_value = written_payload
    assert await service.get_json(key) == payload
    service.client.get.assert_awaited_once_with(expected)
    sync_cache = object.__new__(RedisCache)
    sync_cache._prefix = prefix
    assert sync_cache._make_key(key) == expected
    for stored_key in [expected, expected.encode()]:
        client = MagicMock()
        client.scan_iter.return_value = [stored_key]
        cache = SimpleNamespace(_prefix=prefix, _client=client)
        assert get_cached_words(cache) == {"학교"}
        client.scan_iter.assert_called_once_with(match=f"{prefix}:dict_search:*:ko2zh" if prefix else "dict_search:*:ko2zh", count=1000)


@pytest.mark.asyncio
async def test_binary_audio_and_stats_keep_existing_keys():
    service = RedisService(Settings(_env_file=None, redis_prefix="lingai-lg020"))
    service.available = True
    service.client = AsyncMock()
    audio = b"\xff\xfb\x90test-audio"
    assert await service.set("tts:audio:ko:unit", audio, ttl=60)
    service.client.setex.assert_awaited_once_with("tts:audio:ko:unit", 60, audio)
    await service.hincrby("stats:summary:unit", "total_sessions", 1)
    service.client.hincrby.assert_awaited_once_with("stats:summary:unit", "total_sessions", 1)


@pytest.mark.asyncio
async def test_json_failure_is_cache_miss_and_unavailable_write_is_false():
    service = RedisService(Settings(_env_file=None))
    assert await service.set_json("unit", {"ok": True}) is False
    service.available = True
    service.client = AsyncMock()
    service.client.get.return_value = b"not-json"
    assert await service.get_json("unit") is None
