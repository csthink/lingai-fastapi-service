# LingAI FastAPI Service

韩语学习 App 的 Python FastAPI 服务端。

## 技术栈

- Python 3.11+
- FastAPI + uvicorn
- Redis（缓存）
- Deepseek / 通义千问（LLM）
- Edge TTS（开发环境回退）

## 快速开始

### 1. 进入目录并安装依赖

```bash
cd /Users/mars/sourceCode/LingAI-Project/lingai-fastapi-service
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate
pip install -r requirements.txt
```

如需运行数据处理脚本（Excel 转换、罗马音生成等）：

```bash
pip install -r requirements-scripts.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入 API Keys 和 Redis 配置
```

### 3. 启动服务

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 4. 访问 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 项目结构

```
lingai-fastapi-service/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── routers/             # API 路由
│   ├── services/            # 业务服务
│   ├── models/              # 数据模型
│   └── utils/               # 工具类
├── scripts/                 # 数据构建/预热脚本
├── data/                    # 词库与缓存数据
├── requirements.txt
├── requirements-scripts.txt
└── Dockerfile
```
