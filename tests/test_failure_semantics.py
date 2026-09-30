from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from loguru import logger

from app.config import Settings
from app.models.stats import BatchStatsRequest, StatEvent
from app.routers import dict_ai, stats
from app.services.aliyun_tts import AliyunTTSService


@pytest.mark.asyncio
async def test_stats_unavailable_does_not_acknowledge_dropped_events(monkeypatch):
    monkeypatch.setattr(stats, "get_redis_service", lambda: None)
    request = BatchStatsRequest(device_id="unit", events=[StatEvent(name="lesson_completed", ts=1700000000)])
    with pytest.raises(HTTPException) as caught:
        await stats.upload_batch_stats(request)
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_empty_dictionary_result_is_not_cached_as_success(monkeypatch):
    redis = SimpleNamespace(get_json=AsyncMock(return_value=None), set_json=AsyncMock())
    monkeypatch.setattr(dict_ai, "get_redis_service", lambda: redis)
    llm = SimpleNamespace(get_dict_supplement=AsyncMock(return_value={"ai_meaning": None}))
    with pytest.raises(HTTPException) as caught:
        await dict_ai.search_dict(query="학교", direction="ko2zh", llm_service=llm)
    assert caught.value.status_code == 503
    redis.set_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_stream_emits_error_instead_of_done(monkeypatch):
    monkeypatch.setattr(dict_ai, "get_redis_service", lambda: None)
    async def broken_stream(prompt):
        yield "invalid-json"
    llm = SimpleNamespace(stream_llm=broken_stream)
    response = await dict_ai.search_dict_stream(query="학교", direction="ko2zh", llm_service=llm)
    output = "".join([part async for part in response.body_iterator])
    assert '"type": "error"' in output
    assert '"type": "done"' not in output


@pytest.mark.asyncio
async def test_provider_failure_does_not_log_credentials_or_url(tmp_path):
    settings = Settings(_env_file=None, audio_cache_dir=str(tmp_path), tts_fallback_enabled=False)
    service = AliyunTTSService(settings)
    secret_marker = "unit-secret-do-not-log"
    service._call_aliyun_tts = AsyncMock(side_effect=RuntimeError("https://example.invalid/?token=" + secret_marker))
    messages = []
    sink = logger.add(lambda message: messages.append(str(message)))
    try:
        with pytest.raises(RuntimeError) as caught:
            await service._call_tts_api("公开测试", "zh")
    finally:
        logger.remove(sink)
    assert secret_marker not in str(caught.value)
    assert secret_marker not in "".join(messages)


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['batch', 'summary'])
async def test_stats_connection_failure_after_startup_returns_503(monkeypatch, operation):
    from redis.exceptions import ConnectionError as RedisConnectionError
    from app.services.redis_service import RedisService
    service = RedisService(Settings(_env_file=None))
    service.available = True
    service.client = AsyncMock()
    service.client.hincrby.side_effect = RedisConnectionError('synthetic connection lost')
    service.client.hgetall.side_effect = RedisConnectionError('synthetic connection lost')
    monkeypatch.setattr(stats, 'get_redis_service', lambda: service)
    with pytest.raises(HTTPException) as caught:
        if operation == 'batch':
            await stats.upload_batch_stats(BatchStatsRequest(device_id='unit', events=[]))
        else:
            await stats.get_stats_summary(device_id='unit')
    assert caught.value.status_code == 503


@pytest.mark.asyncio
async def test_stats_legitimate_zero_increment_is_not_a_failure(monkeypatch):
    service = SimpleNamespace(available=True, hincrby=AsyncMock(return_value=0))
    monkeypatch.setattr(stats, 'get_redis_service', lambda: service)
    result = await stats.upload_batch_stats(BatchStatsRequest(device_id='unit', events=[]))
    assert result.success is True


@pytest.mark.asyncio
@pytest.mark.parametrize('content', [None, '', '   ', '\"\"'])
async def test_quick_translation_provider_empty_content_raises(content):
    from app.services.llm_service import LLMService
    service = object.__new__(LLMService)
    service._call_llm = AsyncMock(return_value=content)
    with pytest.raises(RuntimeError):
        await service.quick_translate('검증단어', 'ko2zh')


@pytest.mark.asyncio
@pytest.mark.parametrize('content', [None, '', '   ', RuntimeError('synthetic provider failure')])
async def test_quick_translation_failures_are_503_and_not_cached(monkeypatch, content):
    monkeypatch.setattr(dict_ai, '_load_words_data', lambda: [])
    cache = SimpleNamespace(get_json=AsyncMock(return_value=None), set_json=AsyncMock())
    monkeypatch.setattr(dict_ai, 'get_redis_service', lambda: cache)
    method = AsyncMock(side_effect=content) if isinstance(content, Exception) else AsyncMock(return_value=content)
    with pytest.raises(HTTPException) as caught:
        await dict_ai.quick_translate(word='검증단어', direction='ko2zh', llm_service=SimpleNamespace(quick_translate=method))
    assert caught.value.status_code == 503
    cache.set_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_quick_translation_ignores_legacy_cache_without_deleting_it(monkeypatch):
    monkeypatch.setattr(dict_ai, '_load_words_data', lambda: [])
    old_key = 'quick_translate:검증단어:ko2zh'
    store = {old_key: {'translation': 'legacy-unverified-content'}}
    cache = SimpleNamespace(get_json=AsyncMock(side_effect=lambda key: store.get(key)), set_json=AsyncMock())
    monkeypatch.setattr(dict_ai, 'get_redis_service', lambda: cache)
    method = AsyncMock(return_value='验证单词')
    result = await dict_ai.quick_translate(word='검증단어', direction='ko2zh', llm_service=SimpleNamespace(quick_translate=method))
    assert result.model_dump() == {'word': '검증단어', 'translation': '验证单词', 'source': 'ai'}
    cache.get_json.assert_awaited_once_with('quick_translate:v2:검증단어:ko2zh')
    cache.set_json.assert_awaited_once_with('quick_translate:v2:검증단어:ko2zh', {'schema_version': 2, 'success': True, 'translation': '验证单词'}, ttl=86400 * 7)
    assert store[old_key] == {'translation': 'legacy-unverified-content'}
    method.assert_awaited_once()


@pytest.mark.asyncio
async def test_quick_translation_valid_v2_cache_does_not_call_provider(monkeypatch):
    monkeypatch.setattr(dict_ai, '_load_words_data', lambda: [])
    cache = SimpleNamespace(get_json=AsyncMock(return_value={'schema_version': 2, 'success': True, 'translation': '验证单词'}), set_json=AsyncMock())
    monkeypatch.setattr(dict_ai, 'get_redis_service', lambda: cache)
    method = AsyncMock()
    result = await dict_ai.quick_translate(word='검증단어', direction='ko2zh', llm_service=SimpleNamespace(quick_translate=method))
    assert result.translation == '验证单词' and result.source == 'ai'
    method.assert_not_awaited()
    cache.set_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_quick_translation_local_success_contract_is_preserved(monkeypatch):
    monkeypatch.setattr(dict_ai, '_load_words_data', lambda: [{'hangul': '학교', 'primary_meaning': '学校'}])
    method = AsyncMock()
    result = await dict_ai.quick_translate(word='학교', direction='ko2zh', llm_service=SimpleNamespace(quick_translate=method))
    assert result.model_dump() == {'word': '학교', 'translation': '学校', 'source': 'local'}
    method.assert_not_awaited()
