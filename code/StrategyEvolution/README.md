# 自进化商业报告生成代理 (React Web + DeepSeek + 谷歌搜索)

一个完整的**自进化商业报告生成代理**项目，包含 **React Web 前端** 与 **FastAPI 后端**，具备以下能力：

- 🤖 使用 **DeepSeek 模型**（`DEEPSEEK_API_KEY`，配置于 `config.env`）生成与修订报告
- 🔍 **多级搜索兜底**：Google Custom Search（配置密钥时优先）→ ddgs 聚合搜索 → Bing 网页抓取，**免费方案开箱即用，无需任何搜索 API 密钥**
- 🔄 迭代修订直到达到目标质量分数，智能搜索策略优化
- 🖥️ **React Web 界面**：实时流式过程输出（SSE）、多维评分可视化、报告与搜索记录展示
- 📟 同时保留命令行（CLI）运行方式

## 📁 项目结构

```
StrategyEvolution/
├── config.env          # API 密钥与运行配置（DeepSeek / Google 搜索 / 服务端口）
├── main.py             # 命令行入口
├── server.py           # FastAPI Web 服务端（SSE 流式接口 + 托管前端）
├── requirements.txt    # Python 依赖
├── agent/              # 自进化代理核心
│   ├── llm_backend.py  # DeepSeek 后端（报告生成 + 反思决策 + 工具调用）
│   ├── pipeline.py     # 自进化迭代流程
│   ├── improver.py     # 参数自进化
│   ├── scorer.py       # 多维度质量评分
│   └── search.py       # Google Custom Search 集成
└── web/                # React 前端（Vite + React 18）
    ├── package.json
    ├── vite.config.js  # 开发时将 /api 代理到后端
    └── src/            # App.jsx / styles.css / main.jsx
```

## 🚀 快速开始

### 1. 配置 API 密钥

编辑项目根目录的 `config.env`：

```env
# 必需：DeepSeek API 密钥（https://platform.deepseek.com 获取）
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
# 可选配置
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# 可选：谷歌搜索（不配置则自动使用免费搜索兜底：ddgs 聚合 + Bing 抓取）
GOOGLE_API_KEY=...
GOOGLE_CSE_ID=...

# 可选：ddgs 搜索引擎列表（默认 auto，多个用逗号分隔）
# SEARCH_BACKENDS=auto

# 可选：Web 服务端口
SERVER_HOST=127.0.0.1
SERVER_PORT=8000
```

### 2. 安装依赖

```bash
# Python 后端依赖
pip install -r requirements.txt

# React 前端依赖（需要 Node.js 18+）
cd web
npm install
```

### 3. 启动 Web 应用

**方式 A：开发模式（前后端分开启动，支持热更新）**

```bash
# 终端 1：启动后端（自动读取 config.env）
uvicorn server:app --reload --port 8000

# 终端 2：启动 React 前端（/api 自动代理到 8000 端口）
cd web && npm run dev
# 打开 http://localhost:5173
```

**方式 B：生产模式（构建前端，由 FastAPI 统一托管）**

```bash
cd web && npm run build    # 生成 web/dist
cd .. && uvicorn server:app --port 8000
# 打开 http://localhost:8000
```

### 4. 命令行运行（可选）

```bash
# 基础运行
python main.py --prompt "研究谷歌最近的情况"

# 自定义参数
python main.py --prompt "分析苹果公司的市场策略" --steps 5 --target-words 1000 --target-score 0.85

python main.py --help
```

## 🌐 Web API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/health` | GET | 健康检查，返回模型名与配置状态 |
| `/api/generate` | POST | 运行代理，SSE 流式返回 `log`（过程日志）与 `result`（最终报告 + 评分）事件 |

请求体示例：

```json
{
  "prompt": "分析特斯拉2025年的发展战略和市场表现",
  "steps": 5,
  "target_words": 800,
  "target_score": 0.86
}
```

## 📊 命令行参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--prompt` | string | 必需 | 报告主题或用户需求 |
| `--steps` | int | 5 | 最大迭代步数 |
| `--target-words` | int | 800 | 目标字数 |
| `--target-score` | float | 0.86 | 目标质量分数 |
| `--out` | string | out.json | 输出文件路径 |

## 🔧 工作原理

### 1. 智能反思决策
每次迭代中，DeepSeek 会分析当前状况并决定：
- **搜索**：通过函数调用（Function Calling）请求谷歌搜索，获取更多相关信息
- **修订**：改进当前草稿内容

### 2. 自适应搜索策略
AI 会根据上下文自动优化搜索查询：
```
步骤 1: "latest news Google 2025"
步骤 2: "Google latest news September 2025"
步骤 3: "Google news September 2025"
```

### 3. 多维度质量评估
- **相关性** (30%)：与用户需求的匹配度
- **完整性** (25%)：报告结构的完整性
- **冗余度** (20%)：内容重复程度
- **长度匹配** (15%)：与目标字数的契合度
- **结构** (10%)：格式和组织结构

### 4. Web 端实时进度
后端通过 SSE 将代理每一步的反思、搜索与评分推送到 React 前端：
```
🚀 开始自进化报告生成流程，目标：3步，800字
📍 步骤 1/3
🤔 正在反思决策...
🔍 决定搜索：Google latest news 2025
📊 找到 5 个搜索结果
✍️  基于搜索结果重新生成报告...
📈 当前得分: 0.754 (目标: 0.86)
```

## 📁 输出文件（CLI 模式）

运行完成后，会生成包含以下信息的 JSON 文件：

```json
{
  "summary": "生成的商业报告内容",
  "best_score": {
    "relevance": 0.975,
    "completeness": 1.0,
    "length_fit": 0.953,
    "structure": 1.0,
    "redundancy": 1.0,
    "total": 0.854
  },
  "search_summary": [
    { "step": 1, "query": "Google latest news 2025", "results": [] }
  ],
  "history": [],
  "learned_params": { "bullet_prob": 0.55, "target_words": 800 }
}
```

## 🌟 特性

- ✅ **DeepSeek 驱动**：使用 `DEEPSEEK_API_KEY` 调用 `deepseek-chat`（支持函数调用）
- ✅ **React Web 界面**：现代深色 UI、流式日志、评分可视化
- ✅ **配置集中**：所有密钥与参数统一在 `config.env` 管理
- ✅ **智能搜索**：根据需要自动搜索最新信息
- ✅ **质量驱动**：基于多维度评分的迭代优化
- ✅ **中文优化**：针对中文内容的字数统计和评分

## 🛠️ 技术栈

- **LLM**: DeepSeek（`deepseek-chat`，OpenAI 兼容协议）
- **搜索**: 多级兜底（Google Custom Search / ddgs 聚合搜索 / Bing 网页抓取），免费方案无需密钥
- **后端**: Python 3.8+ / FastAPI / SSE
- **前端**: React 18 / Vite
- **主要 Python 依赖**: openai, requests, fastapi, uvicorn, python-dotenv

## 📝 使用示例

在 Web 界面输入框中尝试：

- 分析特斯拉2025年的发展战略和市场表现
- 分析人工智能在医疗行业的应用趋势
- 比较苹果和三星在智能手机市场的竞争策略
- 研究DeepSeek最新模型及其对行业的影响
