from unittest.mock import MagicMock

from app.config import Settings
from app.services.redis_cache import RedisCache


def test_split_redis_config_preserves_tts_and_tolerates_extra_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("REDIS_HOST=127.0.0.1\nREDIS_PORT=16379\nREDIS_DB=1\nREDIS_PREFIX=unit-test\nLEGACY_UNUSED=true\nTTS_PROVIDER=aliyun\nTTS_FALLBACK_ENABLED=false\n")
    settings = Settings(_env_file=env)
    assert settings.redis_sync_kwargs["port"] == 16379
    assert settings.redis_async_kwargs["db"] == 1
    assert settings.redis_prefix == "unit-test"
    assert settings.redis_async_kwargs["decode_responses"] is False
    assert settings.redis_sync_kwargs["decode_responses"] is True
    assert settings.redis_sync_kwargs["socket_timeout"] == settings.redis_socket_timeout
    assert settings.tts_provider == "aliyun"
    assert settings.tts_fallback_enabled is False
    assert settings.aliyun_region == "cn-shanghai"


def test_empty_cors_whitelist_stays_empty():
    settings = Settings(_env_file=None, cors_enabled=True, cors_allow_origins=" , ")
    assert settings.cors_origins_list == []


def test_cache_rebuilds_when_connection_or_timeout_changes(monkeypatch):
    pools = []
    def pool_factory(**kwargs):
        pool = MagicMock()
        pools.append(pool)
        return pool
    monkeypatch.setattr("app.services.redis_cache.redis.ConnectionPool", pool_factory)
    monkeypatch.setattr("app.services.redis_cache.redis.Redis", MagicMock())
    RedisCache._reset_singleton()
    first_settings = Settings(_env_file=None, redis_prefix="first")
    first = RedisCache.get_instance(first_settings)
    assert RedisCache.get_instance(first_settings) is first
    second = RedisCache.get_instance(first_settings.model_copy(update={"redis_prefix": "second"}))
    assert second is not first
    pools[0].disconnect.assert_called_once()
    third = RedisCache.get_instance(first_settings.model_copy(update={"redis_socket_timeout": 1.0}))
    assert third is not second
    pools[1].disconnect.assert_called_once()
    RedisCache._reset_singleton()
