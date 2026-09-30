# 本地运行说明

FastAPI 是 Unified 的内部能力服务，只监听 `127.0.0.1:18000`。手机通过 Unified 访问，不直接连接此端口。服务自身不提供用户认证、签名或额度校验。

## 运行环境

使用 Python 3.11。已验证的解释器版本为 3.11.15，依赖完整解析结果由 `pip freeze` 生成到 `requirements-lock.txt`。`requirements.txt` 保存直接依赖，Edge TTS 固定为已验证的 7.2.8。安装命令在当前产品工作树执行：

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
.venv/bin/python -m pip check
```

不要将 `.venv/bin/python` 符号链接解析为基础解释器再启动，否则会脱离虚拟环境。无需运行词库预热脚本；全量预热会调用付费模型。

## 受控配置与资源

`.env` 不进入 Git，权限为 600，所在受控目录只对当前用户开放。保留原仓的 `.env`，在恢复工作树另建副本；本地数据连接必须全部改为专属资源。

| 配置 | 本地约束 |
| --- | --- |
| `HOST` / `PORT` | `127.0.0.1` / `18000` |
| `REDIS_HOST` / `REDIS_PORT` | `127.0.0.1` / `16379` |
| `REDIS_DB` / `REDIS_PREFIX` | `1` / `lingai-lg020` |
| `REDIS_PASSWORD` | 从本轮专属 Redis 的受控配置文件注入，不打印 |
| `DATA_DIR` / `AUDIO_CACHE_DIR` | 当前工作树的 `./data` / `./data/audio_cache` |
| `QWEN_API_KEY` / `DEEPSEEK_API_KEY` | 受控环境注入；Qwen 优先，Deepseek 回退 |
| `TTS_PROVIDER` | 本地显式 `edge`；`aliyun` 需可用 AccessKey、AppKey 与音色权限 |
| `TTS_FALLBACK_ENABLED` | 本地验证为 `false`，避免将回退当原供应商成功 |
| `TTS_PRELOAD_ENABLED` | 本地为 `false`，不自动预热 |
| `CORS_ENABLED` | `false`；确需启用时必须提供非空白名单 |

本地启动脚本拒绝其他监听地址或 Redis 组合，防止接到共享实例。Redis 的容器、卷和凭据由跨仓协调统一准备，FastAPI 不创建或清理共享资源。原公共 Redis 的 10399 端口不得用于此环境。

同步缓存、异步 JSON 缓存与预热均使用 `REDIS_PREFIX`。现有统计 `stats:summary:*` 与音频 `tts:audio:*` key 保持原约定，以专属实例和数据库隔离。音频文件在当前工作树缓存目录中保留。

## 启动和验证

前台启动，便于确认当前运行版本：

```bash
.venv/bin/python scripts/run_local.py
```

运行进程需要由协调者记录 PID、cwd、端口和日志位置。若后台运行，可将标准输出与错误写入忽略的 `logs/service.log`，PID 写入 `logs/service.pid`。停止或重启前，先核对 PID 的 cwd 和监听归属，按授权仅对该确切 PID 发送 `SIGTERM`，不得使用按进程名或端口批量结束的命令。

离线回归不连接真实供应商：

```bash
.venv/bin/python -B -m pytest -q tests
```

本地依赖验证会读真实词库、验证同步与异步缓存互读，并写入合成设备统计。测试 key 使用 300 秒过期，合成统计保留在专属数据库，不自动删除：

```bash
.venv/bin/python -B scripts/verify_local.py
```

仅在已经授权真实供应商调用时增加 `--external`。该选项执行一个词典冷流请求、一次对话和中韩各一次语音，随后复用缓存。`--tts-only` 只增加两次语音请求，不重复模型请求。外部调用结果保存到 `logs/verify-<id>/`；首次语音响应头应为实际 `edge` 或 `aliyun`，重复请求为 `cache`。`cache` 不能证明供应商仍可用。切换供应商时使用未缓存的公开测试文本，不能用旧缓存证明新提供方。

日志、`.env`、`.venv` 和音频缓存不进入 Git。分享证据前检查日志没有凭据、Token、真实手机号或用户数据。供应商异常仅记录安全类型；故障诊断不输出异常正文和请求 URL 中的凭据。

## 消费者契约和验收限制

- 学习入口为 `/api/content/levels`、`/api/content/words/topik/{level}` 和 `/api/content/words/level/{level}/lesson/{lesson_id}`。`/api/content/lesson/{id}` 需要单独的课程文件，本轮并未生成这些文件。
- 词典 JSON 使用 camelCase。`/api/dict/search` 的供应商空响应返回 503，不缓存空内容。
- 快速翻译 `/api/dict/quick-translate` 的模型空内容、空白或异常返回 503，不缓存失败。成功仍返回 word、translation、source。内部缓存使用 `quick_translate:v2:*` 及 schema_version/success 标记；旧 key 保留但不读取，避免历史失败内容被当作成功。
- 词典 SSE 冷流按 `token`、`done` 结束；命中缓存时只有一个 `cached` 事件便结束。解析或供应商失败发送既有 `error` 事件，不能把 HTTP 200 当模型成功。
- `/api/spirit/chat` 只有 `success=true` 且有回复才算真实模型成功。`success=false` 是失败响应，不应扣除成功额度。
- 手机语音使用 `GET /api/tts/play?text=...&lang=ko`。`POST /api/tts` 的 `file://` 是服务端文件路径；`POST /api/tts/audio` 需要网关专用二进制转发，不能由通用 JSON 包装替代。
- 统计依赖不可用、建立连接后读写失败均返回 503；合法计数零不会被判为失败。统计尚无事务、去重或可靠云同步，部分写入后失败时重试可能重复计数。
- 健康接口只证明进程响应，不证明 Redis、模型、语音和手机链路全部可用。真实手机播放、登录及网关额度需要另行验收。
