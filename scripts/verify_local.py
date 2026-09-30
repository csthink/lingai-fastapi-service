#!/usr/bin/env python3
"""Verify isolated local contracts; --external enables small paid provider calls."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import httpx
from redis import Redis
from app.config import get_settings
from app.services.redis_cache import RedisCache
from app.services.redis_service import RedisService
from scripts.preload_dict_cache import get_cached_words


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external', action='store_true', help='Allow one cold dictionary stream, one chat, and two TTS requests')
    parser.add_argument('--tts-only', action='store_true', help='Only enable the two TTS provider requests, without repeating model calls')
    args = parser.parse_args()
    settings = get_settings()
    assert (settings.redis_host, settings.redis_port, settings.redis_db, settings.redis_prefix) == ('127.0.0.1', 16379, 1, 'lingai-lg020')
    assert not settings.tts_fallback_enabled, 'Provider verification requires TTS fallback disabled'
    run_id = uuid.uuid4().hex[:12]
    output = ROOT / 'logs' / f'verify-{run_id}'
    output.mkdir(mode=0o700, parents=True)
    report = {'run_id': run_id, 'external_enabled': args.external or args.tts_only, 'tts_provider': settings.tts_provider, 'checks': []}
    redis = Redis(**settings.redis_sync_kwargs)

    def record(name, action):
        try:
            data = action()
            report['checks'].append({'name': name, 'ok': True, **data})
        except Exception as error:
            report['checks'].append({'name': name, 'ok': False, 'error_type': type(error).__name__})
        (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report['checks'][-1], ensure_ascii=False), flush=True)

    with httpx.Client(base_url='http://127.0.0.1:18000', timeout=90, trust_env=False) as client:
        def content():
            levels = client.get('/api/content/levels')
            levels.raise_for_status()
            counts = {}
            for level, expected in [(0, 1203), (1, 1559), (2, 3764)]:
                response = client.get(f'/api/content/words/topik/{level}')
                response.raise_for_status()
                data = response.json()
                assert data['wordCount'] == expected == len(data['words'])
                assert all(word['hangul'] and word['primaryMeaning'] for word in data['words'])
                counts[str(level)] = expected
            lesson = client.get('/api/content/words/level/1/lesson/1').json()
            assert lesson['wordCount'] == 20
            return {'word_counts': counts, 'first_lesson_words': 20, 'trace_header': bool(levels.headers.get('x-trace-id'))}
        record('real_word_data', content)

        def cache():
            sync = RedisCache.get_instance(settings)
            key = f'verification:{run_id}'
            async def exchange():
                async_cache = RedisService(settings)
                await async_cache.connect()
                try:
                    assert sync.set(key, {'writer': 'sync', 'text': '학교'}, ttl=300)
                    assert await async_cache.get_json(key) == {'writer': 'sync', 'text': '학교'}
                    assert await async_cache.set_json(key, {'writer': 'async'}, ttl=300)
                    assert sync.get(key) == {'writer': 'async'}
                finally:
                    await async_cache.disconnect()
            asyncio.run(exchange())
            return {'sync_async_json_exchange': True, 'test_key_ttl_seconds': 300}
        record('real_redis_interoperability', cache)

        def statistics():
            device = f'lg020-verification-{run_id}'
            response = client.post('/api/stats/batch', json={'device_id': device, 'events': [
                {'name': 'study_minutes', 'ts': int(time.time()*1000), 'data': {'minutes': 2}},
                {'name': 'lesson_completed', 'ts': int(time.time()), 'data': {'count': 1}},
            ]})
            response.raise_for_status()
            assert response.json()['success'] is True
            result = client.get('/api/stats/summary', params={'device_id': device}).json()
            assert result['total_study_minutes'] == 2 and result['total_lessons_completed'] == 1
            return {'synthetic_device_id': device, 'study_minutes': 2, 'lessons_completed': 1}
        record('real_stats_aggregation', statistics)

        if args.external:
            def dictionary():
                query = '수요일'
                cache_key = f'{settings.redis_prefix}:dict_search:{query}:ko2zh'
                was_cached = bool(redis.exists(cache_key))
                events = []
                first_event_seconds = None
                started = time.monotonic()
                with client.stream('GET', '/api/dict/search/stream', params={'query': query, 'direction': 'ko2zh'}) as response:
                    response.raise_for_status()
                    assert response.headers['content-type'].startswith('text/event-stream')
                    for line in response.iter_lines():
                        if line.startswith('data: '):
                            if first_event_seconds is None:
                                first_event_seconds = round(time.monotonic()-started, 3)
                            events.append(json.loads(line[6:]))
                (output / 'dictionary-events.json').write_text(json.dumps(events, ensure_ascii=False, indent=2))
                types = [event['type'] for event in events]
                assert 'error' not in types
                assert types[-1] == ('cached' if was_cached else 'done')
                if not was_cached:
                    assert 'token' in types
                result = events[-1]['data']
                assert result['aiSupplement']['aiMeaning']
                normal = client.get('/api/dict/search', params={'query': query, 'direction': 'ko2zh'})
                normal.raise_for_status()
                assert normal.json() == result
                hot = client.get('/api/dict/search/stream', params={'query': query, 'direction': 'ko2zh'})
                hot_events = [json.loads(line[6:]) for line in hot.text.splitlines() if line.startswith('data: ')]
                assert [event['type'] for event in hot_events] == ['cached']
                assert query in get_cached_words(RedisCache.get_instance(settings))
                return {'query': query, 'cold_provider_call': not was_cached, 'token_events': types.count('token'), 'terminal_event': types[-1], 'warm_event': 'cached', 'first_event_seconds': first_event_seconds, 'total_seconds': round(time.monotonic()-started, 3)}
            record('dictionary_stream_and_cache', dictionary)

            def chat():
                response = client.post('/api/spirit/chat', json={'messages': [{'role': 'user', 'content': '请用一句话解释韩语 안녕하세요 的中文意思。'}]})
                response.raise_for_status()
                result = response.json()
                (output / 'chat.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
                assert result['success'] is True and result['reply'] and not result.get('error')
                return {'success': True, 'reply_characters': len(result['reply'])}
            record('real_ai_chat', chat)

        if args.external or args.tts_only:
            for lang, text in [('zh', '这是韩语学习语音测试。'), ('ko', '오늘은 한국어를 공부합니다.')]:
                def tts(lang=lang, text=text):
                    response = client.get('/api/tts/play', params={'text': text, 'lang': lang})
                    metadata = {'http_status': response.status_code, 'content_type': response.headers.get('content-type'), 'provider': response.headers.get('x-tts-provider')}
                    (output / f'tts-{lang}-metadata.json').write_text(json.dumps(metadata, indent=2))
                    response.raise_for_status()
                    assert response.headers['content-type'].startswith('audio/mpeg')
                    assert response.headers.get('x-tts-provider') in (settings.tts_provider, 'cache')
                    assert len(response.content) > 1000
                    audio = output / f'tts-{lang}.mp3'
                    audio.write_bytes(response.content)
                    return {**metadata, 'bytes': len(response.content), 'sha256': hashlib.sha256(response.content).hexdigest(), 'audio_path': str(audio)}
                record(f'real_tts_{lang}', tts)

    redis.close()
    RedisCache._reset_singleton()
    print('RESULT_PATH', output / 'summary.json', flush=True)
    raise SystemExit(0 if all(check['ok'] for check in report['checks']) else 1)


if __name__ == '__main__':
    main()
