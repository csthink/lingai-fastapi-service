# LingAI FastAPI Service

> LingAI 内部学习能力服务 - 为韩语学习 App 提供词典、内容、TTS、统计、AI 对话等核心业务能力。

## 在整体架构中的定位

本服务是 LingAI 多工程体系中的**内部能力层**，不直接对公网暴露，仅由 [Unified Service](../lingai-unified-service) 通过内网 HTTP 转发调用。

```
Harmony App / Admin Web
        │
        ▼
  Unified Service（统一入口 · 认证授权 · 网关）
        │  内网 HTTP
        ▼
 ┌──────────────────────────┐
 │  FastAPI Service (本仓库)  │  ← 词典 · 内容 · TTS · 统计 · AI 对话
 └──────────────────────────┘
        │
        ▼
   第三方能力（Deepseek / 通义千问 / 阿里云 TTS / Edge TTS）
```

**职责边界**：

| 本服务负责 | 本服务不负责 |
|---|---|
| 词典查询与 LLM 增强 | 用户账号体系 |
| TOPIK 学习内容分发 | 认证授权（JWT / 签名） |
| TTS 语音合成 | 对外暴露公网入口 |
| 学习统计事件收集 | 管理后台逻辑 |
| AI 韩语学习助手（多轮对话） | |

## 技术栈

| 类别 | 技术 |
|---|---|
| 框架 | Python 3.11+、FastAPI 0.109、Uvicorn |
| 数据校验 | Pydantic v2、Pydantic-Settings |
| HTTP 客户端 | httpx、aiohttp |
| 缓存 | Redis，Python 客户端 redis 5.0.1 |
| LLM | 通义千问（优先）、[Deepseek](https://api.deepseek.com)（回退） |
| TTS | 阿里云 NLS / 显式 Edge TTS，响应头区分提供方与缓存 |
| 日志 | Loguru |
| 数据处理（脚本） | Pandas、openpyxl、korean-romanizer |
| 容器化 | Docker（python:3.11-slim） |

## 快速开始

### 1. 安装依赖

```bash
cd /path/to/lingai-fastapi-service
python3.11 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-lock.txt
```

如需运行数据处理脚本（Excel 转换、罗马音生成等）：

```bash
pip install -r requirements-scripts.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env，填入以下关键配置：
```

| 变量 | 说明 | 必填 |
|---|---|---|
| `DEEPSEEK_API_KEY` | Deepseek 回退 LLM Key | 与 QWEN_API_KEY 至少一项 |
| `QWEN_API_KEY` | 通义千问优先 LLM Key | 与 DEEPSEEK_API_KEY 至少一项 |
| `ALIYUN_ACCESS_KEY_ID` | 阿里云 TTS AccessKey | 生产必填 |
| `ALIYUN_ACCESS_KEY_SECRET` | 阿里云 TTS Secret | 生产必填 |
| `ALIYUN_TTS_APP_KEY` | 阿里云 TTS AppKey | 生产必填 |
| `ALIYUN_VOICE_KO` | 韩语音色（默认 `xiaoyun`） | 可选 |
| `ALIYUN_VOICE_ZH` | 中文音色（默认 `xiaoyun`） | 可选 |
| `REDIS_HOST` / `REDIS_PORT` | 专属 Redis 地址与端口 | ✅ |
| `REDIS_PASSWORD` / `REDIS_DB` | 受控密码与数据库编号 | ✅ |
| `REDIS_PREFIX` | JSON 缓存与预热共同前缀 | ✅ |
| `DATA_DIR` | 数据文件目录（默认 `./data`） | 可选 |
| `AUDIO_CACHE_DIR` | TTS 音频缓存目录 | 可选 |
| `TTS_PROVIDER` | 显式提供方；本地模板为 `edge`，类默认值为 `aliyun` | ✅ |
| `TTS_FALLBACK_ENABLED` | 提供方验证时为 `false`；模板关闭回退 | ✅ |
| `DEBUG` | 调试模式（默认 `true`） | 可选 |

> [!CAUTION]
> **安全规范**：
> - Redis 使用拆分变量 `REDIS_HOST`、`REDIS_PORT`、`REDIS_PASSWORD`、`REDIS_DB`、`REDIS_PREFIX`。通过环境变量或受控 `.env` 注入；不再读取 `REDIS_URL`
> - **严禁** 将真实密码写入源码默认值或提交到版本控制
> - `.env` 文件已在 `.gitignore` 中，请勿手动移除

### 3. 启动服务

```bash
.venv/bin/python scripts/run_local.py
```

本地环境准备、凭据注入、隔离要求与验证命令见 [本地运行说明](docs/local-development.md)。

### 4. 访问 API 文档

- **Swagger UI**：http://127.0.0.1:18000/docs
- **ReDoc**：http://127.0.0.1:18000/redoc
- **健康检查**：http://127.0.0.1:18000/health

## API 接口概览

所有接口前缀由 Unified Service 网关映射：`/api/app/biz/api/xxx` → 本服务 `/api/xxx`。

### 📖 词典（`/api/dict`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/dict/search` | LLM 增强词典查询（支持韩→中、中→韩、自动检测） |
| GET | `/api/dict/search/stream` | SSE 流式词典查询（实时输出 LLM Token） |
| POST | `/api/dict/ai` | AI 词义详解（含例句、近反义词、搭配等） |
| POST | `/api/dict/mnemonic` | 生成 AI 记忆辅助内容 |
| GET | `/api/dict/quick-translate` | 快速翻译（优先本地词库，回退 LLM） |

### 📚 学习内容（`/api/content`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/content/levels` | 获取 TOPIK 等级信息与课程数量 |
| GET | `/api/content/lesson/{lesson_id}` | 获取课程完整内容（单词、音频链接、AI 助记） |
| GET | `/api/content/lesson/{lesson_id}/quiz-config` | 获取课程测验配置 |
| GET | `/api/content/words/topik/{level}` | 获取指定 TOPIK 等级全部单词 |
| GET | `/api/content/words/level/{level}/lesson/{lesson_id}` | 获取指定课程单词列表（20 词/课） |

### 🔊 TTS 语音合成（`/api/tts`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/tts` | 文本转语音元数据（file:// 为服务端路径，手机播放使用 GET /play） |
| POST | `/api/tts/audio` | 文本转语音（返回 audio/mpeg 二进制） |
| GET | `/api/tts/play?text=...&lang=ko` | GET 方式播放语音（供客户端直接调用） |

### 📊 统计（`/api/stats`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/stats/batch` | 批量上报学习事件（Redis 聚合计数） |
| GET | `/api/stats/summary?device_id=xxx` | 获取统计摘要（支持按设备或全局查询） |

### 🤖 AI 助手（`/api/spirit`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/spirit/chat` | "小语灵" 多轮对话（韩语学习助手） |

## 项目结构

```
lingai-fastapi-service/
├── app/
│   ├── main.py                  # FastAPI 入口、生命周期管理、路由注册
│   ├── config.py                # 配置管理（Pydantic-Settings，读取 .env）
│   ├── routers/                 # API 路由层
│   │   ├── dict_ai.py           #   词典 + LLM 增强查询（含 SSE 流式）
│   │   ├── content.py           #   学习内容（等级、课程、单词）
│   │   ├── tts.py               #   TTS 语音合成
│   │   ├── stats.py             #   统计事件收集
│   │   ├── spirit.py            #   AI 韩语助手多轮对话
│   │   └── sse_test.py          #   SSE 测试端点
│   ├── services/                # 业务服务层
│   │   ├── llm_service.py       #   LLM 调用（通义千问优先 + Deepseek 回退）
│   │   ├── dict_service.py      #   词典业务逻辑
│   │   ├── aliyun_tts.py        #   阿里云 TTS + Edge TTS 回退
│   │   ├── redis_service.py     #   Redis 连接管理
│   │   └── redis_cache.py       #   Redis 缓存封装
│   ├── models/
│   │   └── schemas.py           #   Pydantic 数据模型（词条、课程、测验等）
│   └── utils/
│       └── cache.py             #   缓存工具
├── scripts/                     # 数据构建与预热脚本
│   ├── excel_to_json.py         #   Excel 词库转 JSON
│   ├── build_wordlist.py        #   构建单词列表
│   ├── add_romanization.py      #   批量生成罗马音
│   ├── convert_pos.py           #   词性转换
│   ├── preload_dict_cache.py    #   预热词典 Redis 缓存
│   ├── retry_failed_words.py    #   重试失败词条
│   └── test_services.py         #   服务测试脚本
├── data/                        # 数据文件
│   ├── common_words.json        #   常考单词库
│   ├── topik_i_words.json       #   TOPIK I 词库
│   ├── topik_ii_words.json      #   TOPIK II 词库
│   ├── *.xlsx                   #   原始 Excel 词库
│   └── audio_cache/             #   TTS 音频文件缓存
├── docs/
│   ├── prd.md                   # 产品需求文档
│   └── TechSpec.md              # 技术规格文档
├── Dockerfile                   # Docker 镜像构建
├── requirements.txt             # 运行时依赖
├── requirements-scripts.txt     # 数据处理脚本依赖
├── .env.example                 # 环境变量模板
└── .gitignore
```

## Docker 部署

```bash
# 构建镜像
docker build -t lingai-fastapi-service .

# 运行容器
docker run -d \
  --name lingai-fastapi \
  -p 127.0.0.1:18000:8000 \
  --env-file .env \
  lingai-fastapi-service
```

> **注意**：生产环境中本服务应仅监听内网端口，由 Unified Service 通过内网访问，不对公网暴露。

## 数据处理脚本

`scripts/` 目录下的脚本用于词库数据的构建和维护：

```bash
# 1. Excel 词库转 JSON
python scripts/excel_to_json.py

# 2. 为词条批量添加罗马音
python scripts/add_romanization.py

# 3. 预热词典缓存到 Redis
python scripts/preload_dict_cache.py
```

## 相关工程

| 工程 | 说明 |
|---|---|
| [lingai-unified-service](../lingai-unified-service) | 统一认证授权、网关、用户/设备/版本管理 |
| [lingai-korea-harmony-app](../lingai-korea-harmony-app) | 鸿蒙客户端 App |
| [lingai-admin-web](../lingai-admin-web) | 运营管理后台前端 |

> 完整架构设计请参考：[统一项目架构设计](../docs/统一项目架构设计.md)
