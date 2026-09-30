# Agent 协作平台（Google A2A SDK + DeepSeek + React）





## 🎯 概述

本项目展示如何使用 **Google 官方 A2A Python SDK** 构建标准化的多 Agent 协作系统，并提供一个 **React Web 应用** 作为可视化交互界面。

### 核心特性
- ✅ 标准化的 Agent-to-Agent 通信协议
- ✅ Agent Card 服务发现机制
- ✅ 类型安全的消息传递
- ✅ 支持多种协作模式（串行、并行、条件路由、管道）
- ✅ 🤖 集成 **DeepSeek**（deepseek-v4-flash）提供智能能力
- ✅ 🖥️ **React Web 应用**：Agent 状态监控、单 Agent 对话、多 Agent 协作管道可视化


程序运行演示

[【无声演示】A2A Agent协作平台](https://www.bilibili.com/video/BV1Mha86jEqa/)






## 参考代码

https://github.com/yh-yao/super_agent_book/tree/main/a2a_%E6%99%BA%E8%83%BD%E4%BD%93



## 🏗️ 系统架构

```
┌─────────────┐     HTTP/JSON      ┌──────────────┐     A2A 协议      ┌───────────────┐
│  React 前端  │ ─────────────────▶ │  FastAPI 网关 │ ───────────────▶ │  4 个 Agent    │
│  (端口 5173) │                    │  (端口 8080)  │                  │  (8001-8004)   │
└─────────────┘                    └──────────────┘                  └───────┬───────┘
                                                                             │
                                                                     DeepSeek API
                                                                     (deepseek-v4-flash)
```

| 组件 | 目录 | 端口 | 说明 |
|------|------|------|------|
| React 前端 | `webapp/` | 5173 | Vite + React 18，可视化交互界面 |
| Web 网关 | `server/gateway.py` | 8080 | FastAPI，桥接前端与 Agent，编排协作管道 |
| Collector Agent | `agents/collector_agent.py` | 8001 | 信息收集 |
| Summarizer Agent | `agents/summarizer_agent.py` | 8002 | 摘要生成 |
| Translator Agent | `agents/translator_agent.py` | 8003 | 文本翻译 |
| Classifier Agent | `agents/classifier_agent.py` | 8004 | 内容分类 |

---

## 🚀 快速开始

### 1. 安装后端依赖

```bash
pip install -r requirements.txt
```

依赖包括：`a2a-sdk`, `fastapi`, `uvicorn`, `httpx`, `openai`, `python-dotenv`

### 2. 配置 DeepSeek API Key

编辑项目根目录的 **`config.env`** 文件（所有 Agent 与网关统一从此文件读取配置）：

```env
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# 搜索 API（Collector Agent 网络搜索，优先 SerpAPI，失败回退 Bocha）
SERPAPI_API_KEY=your_serpapi_key_here
BOCHA_API_KEY=your_bocha_key_here

# PostgreSQL（记录搜索结果）
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=a2a_news
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

**当前可用的 DeepSeek 模型**（官方 API 现仅提供以下两个模型，旧模型名 `deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 停用）：

| 模型 | 特点 | 适用场景 |
|------|------|---------|
| `deepseek-v4-flash` | 快速、性价比高 | 本项目默认，日常对话/分类/翻译/摘要 |
| `deepseek-v4-pro` | 更强的推理能力 | 需要更高质量输出时替换 `DEEPSEEK_MODEL` 即可 |

> ⚠️ `config.env` 已在 `.gitignore` 中排除，请勿将 API Key 提交到版本库。
> API Key 获取：https://platform.deepseek.com
> 定价详情：https://api-docs.deepseek.com/zh-cn/quick_start/pricing

### 3. 启动 Agent 服务（4 个终端）

```bash
python agents/collector_agent.py    # 端口 8001
python agents/summarizer_agent.py   # 端口 8002
python agents/translator_agent.py   # 端口 8003
python agents/classifier_agent.py   # 端口 8004
```

### 4. 启动 Web 网关

```bash
python server/gateway.py            # 端口 8080
```

### 5. 启动 React 前端

```bash
cd webapp
npm install
npm run dev                         # 端口 5173
```

访问 **http://localhost:5173** 即可使用 Web 应用：

- **Agent 对话**：选择任意 Agent 直接对话（左栏实时显示各 Agent 在线状态）
- **协作管道**：一键运行「收集信息 → 内容分类 → 生成摘要 → 翻译英文」完整管道，各阶段耗时与结果可视化展示

### 6. 验证服务（可选）

```bash
# 检查网关健康状态
curl http://localhost:8080/api/health

# 查看所有 Agent 状态
curl http://localhost:8080/api/agents

# 查看 Agent Card
curl http://localhost:8001/.well-known/agent-card.json
```

### 7. 运行命令行示例（可选）

```bash
python clients/01_sequential.py    # 串行协作
python clients/02_parallel.py      # 并行协作
python clients/03_conditional.py   # 条件路由
python clients/04_pipeline.py      # 复杂管道
```

---

## 📚 协作模式

| 模式 | 工作流 | 适用场景 |
|------|--------|---------|
| **串行** | A → B → C | 顺序依赖的任务 |
| **并行** | [A, B, C] → Merge | 独立任务并发 |
| **条件路由** | A → Router → [B/C/D] | 根据条件选择路径 |
| **管道** | Multi-stage Pipeline | 企业级复杂工作流 |

---

## 🏗️ Agent 服务说明

| Agent | 端口 | 功能 | AI 模型 | 输入 | 输出 |
|-------|------|------|---------|------|------|
| **Collector** | 8001 | 收集信息 | DeepSeek (deepseek-v4-flash, 请求解析) + SerpAPI/Bocha 搜索 | 主题、数量 | 信息列表（入库 PostgreSQL） |
| **Summarizer** | 8002 | 生成摘要 | DeepSeek (deepseek-v4-flash) | 原始文本 | 摘要文本 |
| **Translator** | 8003 | 文本翻译 | DeepSeek (deepseek-v4-flash) | 文本、语言 | 翻译结果 |
| **Classifier** | 8004 | 内容分类 | DeepSeek (deepseek-v4-flash) | 文本 | 分类标签 |

**所有 Agent 均通过 OpenAI 兼容接口调用 DeepSeek 模型**（`base_url=https://api.deepseek.com`，模型 `deepseek-v4-flash`），API Key 从 `config.env` 的 `DEEPSEEK_API_KEY` 读取。公共客户端封装位于 `agents/llm_client.py`。

### 🔍 Collector Agent 搜索与存储流程

```
用户请求 → DeepSeek 解析主题/数量 → SerpAPI 搜索（失败回退 Bocha）
        → 结果写入 PostgreSQL 表 search_results
        → 返回信息列表（含标题/摘要/链接/日期）
（搜索或数据库不可用时自动降级，服务不中断）
```

---

## 🗄️ 数据库设计（PostgreSQL）

### 概述

Collector Agent 每次执行网络搜索后，将结果记录到 PostgreSQL 的 `search_results` 表中，实现搜索历史持久化。表结构在 Agent 启动时**自动创建**（幂等，无需手动执行 SQL）。

存储模块位于 `agents/db.py`，所有数据库操作均为 best-effort：PostgreSQL 不可用时仅打印告警日志，业务流程不中断（搜索结果照常返回，只是不入库）。

### 表结构：`search_results`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `BIGSERIAL` | 自增主键 |
| `query` | `TEXT NOT NULL` | 搜索关键词（如 `AI 最新信息 2026`） |
| `topic` | `TEXT NOT NULL` | 解析出的主题（`AI` / `科技` / `金融`） |
| `title` | `TEXT NOT NULL` | 搜索结果标题 |
| `url` | `TEXT` | 结果链接 |
| `snippet` | `TEXT` | 结果摘要 |
| `source` | `VARCHAR(32)` | 搜索源（`serpapi` / `bocha`） |
| `raw` | `JSONB` | 原始搜索结果（完整字段） |
| `created_at` | `TIMESTAMPTZ` | 入库时间，默认 `now()` |

索引：
- `idx_search_results_topic_time` — `(topic, created_at DESC)`：按主题查询最新记录
- `idx_search_results_url` — `(url)`：按链接去重/查询

### 建表 SQL（与 `agents/db.py` 中 `INIT_SQL` 一致，仅供了解）

```sql
CREATE TABLE IF NOT EXISTS search_results (
    id         BIGSERIAL PRIMARY KEY,
    query      TEXT NOT NULL,
    topic      TEXT NOT NULL DEFAULT '',
    title      TEXT NOT NULL,
    url        TEXT NOT NULL DEFAULT '',
    snippet    TEXT NOT NULL DEFAULT '',
    source     VARCHAR(32) NOT NULL DEFAULT '',
    raw        JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 安装与初始化（macOS）

```bash
# 1. 安装并启动 PostgreSQL
brew install postgresql@16
brew services start postgresql@16

# 2. 创建数据库（默认以当前系统用户名连接，无需密码）
createdb a2a_news

# 3. 启动 Collector Agent，启动时自动建表
python agents/collector_agent.py
# 控制台出现 "🗄️ PostgreSQL 就绪: True" 即成功
```

`config.env` 中对应的连接配置：

```env
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=a2a_news
POSTGRES_USER=你的系统用户名
POSTGRES_PASSWORD=
```

### 查询数据

**方式一：通过网关 API**

```bash
curl "http://localhost:8080/api/history?limit=10"          # 最近 10 条
curl "http://localhost:8080/api/history?topic=AI&limit=5"  # 按主题过滤
```

**方式二：直接查询数据库**

```sql
-- 最近 10 条搜索记录
SELECT id, topic, left(title, 40) AS title, source, created_at
FROM search_results ORDER BY created_at DESC LIMIT 10;

-- 各主题的记录数统计
SELECT topic, count(*) FROM search_results GROUP BY topic;

-- 某条信息的完整原始数据 (raw JSONB)
SELECT raw FROM search_results WHERE id = 1;
```

### Python 接口（agents/db.py）

| 函数 | 说明 |
|------|------|
| `init_db()` | 建表与索引（幂等），返回是否成功 |
| `save_results(query, topic, source, results)` | 批量写入一次搜索的结果，返回写入条数 |
| `recent_results(topic, limit)` | 按主题查询最近的入库记录 |

---

## 🌐 Web 网关 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 网关健康检查 |
| GET | `/api/agents` | 查询所有 Agent 状态与 Agent Card |
| GET | `/api/history` | 查询 PostgreSQL 中的历史搜索记录（`?topic=AI&limit=20`） |
| POST | `/api/chat` | 与单个 Agent 对话 `{ "agent": "collector", "message": "..." }` |
| POST | `/api/pipeline` | 运行多 Agent 管道 `{ "topic": "AI", "count": 3 }` |

---

## 📖 核心 API 示例

### 创建 Agent 服务端

```python
from a2a.server import A2AServer, create_app
from a2a.types import AgentCard, Skill, Message, Part, TextPart, Role

class MyAgent(A2AServer):
    def __init__(self):
        agent_card = AgentCard(
            name="My Agent",
            description="我的智能代理",
            url="http://localhost:8000",
            skills=[Skill(id="my_skill", name="我的技能")]
        )
        super().__init__(agent_card=agent_card)

    async def handle_message(self, message: Message) -> Message:
        text = message.parts[0].root.text
        return Message(
            role=Role.AGENT,
            parts=[Part(root=TextPart(text=f"处理: {text}"))]
        )
```

### 调用 DeepSeek 模型（OpenAI 兼容接口）

```python
from openai import OpenAI

client = OpenAI(
    api_key="你的 DEEPSEEK_API_KEY",
    base_url="https://api.deepseek.com",
)
resp = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)
```

### 调用 Agent 客户端

```python
from a2a.client import ClientFactory, create_text_message_object

client = await ClientFactory.create_client("http://localhost:8000")
message = create_text_message_object("你好")

async for event in client.send_message(message):
    if hasattr(event, 'parts'):
        print(event.parts[0].root.text)
```

---

## 🔍 A2A 核心概念

### 1. Agent Card
Agent 的"名片"，描述能力和接口，位于 `/.well-known/agent-card.json`

### 2. Message Format
标准化消息格式，包含 `role`、`parts`、`message_id` 等字段

### 3. 服务发现
客户端通过 Agent Card 自动发现和验证 Agent 能力

---

## 📁 项目结构

```
A2A_Agent/
├── README.md
├── requirements.txt        # Python 依赖
├── config.env              # 配置文件（DEEPSEEK_API_KEY 等，不提交到 Git）
├── agents/                 # Agent 服务（使用 A2AServer + DeepSeek）
│   ├── llm_client.py       # DeepSeek 客户端公共封装
│   ├── search_service.py   # 网络搜索服务（SerpAPI / Bocha）
│   ├── db.py               # PostgreSQL 存储模块（记录搜索结果）
│   ├── collector_agent.py  # 信息收集 (8001, 搜索+入库)
│   ├── summarizer_agent.py # 摘要生成 (8002)
│   ├── translator_agent.py # 文本翻译 (8003)
│   └── classifier_agent.py # 内容分类 (8004)
├── server/
│   └── gateway.py          # FastAPI Web 网关 (8080)
├── webapp/                 # React Web 应用 (5173)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx         # 主界面（对话 + 管道）
│       ├── api.js          # 网关 API 封装
│       └── styles.css
└── clients/                # 客户端示例（使用 ClientFactory）
    ├── 01_sequential.py
    ├── 02_parallel.py
    ├── 03_conditional.py
    └── 04_pipeline.py
```

---

## ⚙️ 配置项说明（config.env）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | （必填） | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 使用的模型（可选 `deepseek-v4-flash` / `deepseek-v4-pro`） |
| `SERPAPI_API_KEY` | （选填） | SerpAPI 搜索密钥，https://serpapi.com |
| `BOCHA_API_KEY` | （选填） | 博查搜索密钥，https://open.bochaai.com |
| `POSTGRES_HOST` 等 | `localhost:5432/a2a_news` | PostgreSQL 连接配置（表 `search_results` 自动创建） |
| `COLLECTOR_URL` 等 | `http://localhost:800x` | 各 Agent 服务地址 |
| `GATEWAY_HOST` / `GATEWAY_PORT` | `0.0.0.0` / `8080` | 网关监听配置 |
