# MCP 演示项目 (Python + React)

这是一个**教学级别**的 **Model Context Protocol (MCP)** 实现，使用官方 Python SDK 构建，并附带一个基于 **React** 的 Web 聊天应用（使用 **DeepSeek** 模型）。它包含：

- 一个 **FastMCP** 服务器，暴露了几个工具和资源
- 一个**小型本地客户端**，通过 STDIO 使用类似 LSP 的 `Content-Length` 帧格式与 MCP 通信
- 一个 **React + FastAPI Web 应用**，通过 `config.env` 中的 `DEEPSEEK_API_KEY` 调用 DeepSeek 模型
- 不含硬编码的密钥；所有配置通过 `config.env` 或环境变量提供

程序运行演示

[【无声演示】MCP服务端和客户端](https://www.bilibili.com/video/BV17eah6AEU5/)



## 参考代码
https://github.com/yh-yao/super_agent_book/tree/main/mcp%E6%9C%8D%E5%8A%A1%E7%AB%AF%E4%B8%8E%E5%AE%A2%E6%88%B7%E7%AB%AF


## 项目结构

```
MCPSevClient/
├── config.env              # 配置文件（DeepSeek API Key 等）
├── requirements.txt        # Python 依赖
├── src/mcp_demo/server.py  # FastMCP 服务器
├── client/                 # MCP 命令行客户端示例
├── sample_data/            # 演示数据（read_file 工具沙箱目录）
└── web/                    # React Web 应用
    ├── backend/main.py     # FastAPI 后端（读取 config.env，代理 DeepSeek API）
    └── frontend/           # React (Vite) 前端聊天界面
```

---

## 一、DeepSeek Web 聊天应用（React）

基于 **React + Vite + FastAPI** 的聊天应用。API Key 保存在服务端 `config.env` 中，前端不接触密钥。

### 1. 配置 `config.env`

编辑项目根目录的 `config.env`，填入你的 DeepSeek API Key：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx        # 必填，申请地址: https://platform.deepseek.com
DEEPSEEK_BASE_URL=https://api.deepseek.com  # 可选，默认官方地址
DEEPSEEK_MODEL=deepseek-chat                # 可选，deepseek-chat / deepseek-reasoner
PORT=8000                                   # 可选，后端监听端口
```

### 2. 安装依赖

```bash
# Python 后端依赖
pip install -r requirements.txt

# React 前端依赖
cd web/frontend
npm install
```

### 3. 启动方式

**方式 A：开发模式（前后端分离，支持热更新）**

```bash
# 终端 1：启动 FastAPI 后端（读取 config.env）
python web/backend/main.py

# 终端 2：启动 Vite 开发服务器（自动代理 /api 到后端）
cd web/frontend
npm run dev
```

浏览器打开 http://localhost:5173

**方式 B：生产模式（单进程，后端直接托管前端构建产物）**

```bash
# 先构建前端
cd web/frontend
npm run build

# 回到项目根目录启动后端
cd ../..
python web/backend/main.py
```

浏览器打开 http://localhost:8000

### 4. 功能特性

- 💬 流式对话（SSE），逐字输出，打字机效果
- 🔧 **工具调用（共 10 个）**：模型可智能决定调用工具，前端以“🔧 AI 决定调用工具”气泡展示工具名、参数与执行结果
  - **原生工具（后端内置 7 个）**：
    - `calculate(expression)` — 精确计算数学表达式（基于 AST 安全求值）
    - `get_current_time(timezone)` — 获取指定时区的当前日期时间
    - `generate_password(length, include_symbols)` — 生成加密安全的随机密码
    - `get_weather(city)` — 查询城市实时天气（Open-Meteo 公开 API，无需 Key）
    - `get_exchange_rate(base, target, amount)` — 实时汇率查询与换算（open.er-api.com，无需 Key）
    - `read_url(url, max_chars)` — 抓取网页并提取正文文本（自动去除 HTML 标签）
    - `web_search(query, count)` — **真实网络搜索**（后端直接调用博查/SerpAPI，不依赖 MCP；优先博查，失败自动切换 SerpAPI）
  - **MCP 工具（3 个）**：`add`、`search_http`、`read_file`（来自 `src/mcp_demo/server.py`）
    - `search_http` 支持**真实搜索引擎**：
      - **博查 Bocha**（`BOCHA_API_KEY`，中文搜索推荐，申请地址: https://open.bochaai.com）
      - **SerpAPI**（`SERPAPI_API_KEY`，支持百度/Google/Bing/DuckDuckGo，申请地址: https://serpapi.com）
      - `engine` 参数：`auto`（默认，优先博查）/ `bocha` / `baidu` / `google` / `bing` / `duckduckgo`
      - 首选引擎失败自动切换备用引擎；两个 Key 都未配置时返回演示数据
- 🤖 通过 `config.env` 的 `DEEPSEEK_MODEL` 切换 `deepseek-chat` / `deepseek-reasoner`
- 🧑‍💻 现代化聊天 UI：消息气泡、建议问题、清空对话、点击“发送”按钮发送
- 🔐 API Key 仅保存在服务端 `config.env`，前端零密钥暴露
- ⚠️ 未配置 Key 时页面顶部会给出友好提示

### 5. API 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查，返回模型名与 Key 配置状态 |
| POST | `/api/chat` | 对话接口，请求体 `{"messages": [{"role","content"}], "stream": true}`，默认 SSE 流式返回 |

---

## 二、MCP 快速开始（原有功能）

```bash
# 1) 安装依赖
pip install -r requirements.txt

# 2) 运行服务器（前台运行）
python src/mcp_demo/server.py
```

在另一个终端（使用相同的虚拟环境），运行演示客户端，它会为你启动服务器并通过 MCP 调用工具：

```bash
python client/demo_client.py
```

你应该会看到：
- 协议 `initialize` 握手
- 工具列表
- 成功调用 `add`、`search_http` 和 `read_file` 工具

### OpenAI 集成示例

运行 OpenAI 集成客户端，演示如何让 AI 智能调用 MCP 工具：

```bash
# 设置 OpenAI API 密钥
export OPENAI_API_KEY='your-api-key-here'

# (可选) 设置 SerpAPI 密钥以启用真实搜索功能（支持百度、Google 等）
export SERPAPI_API_KEY='your-serpapi-key-here'

# 运行 OpenAI 集成示例
python client/openai_client.py
```

这个示例展示了：
- 将 MCP 工具自动转换为 OpenAI 函数格式
- OpenAI 模型智能决定何时调用哪些工具
- 工具调用结果反馈给 AI 生成最终回答
- 完整的对话流程（用户 → AI → 工具 → AI → 用户）

**关于搜索功能：**
- 默认使用演示数据（无需 API Key）
- 设置 `SERPAPI_API_KEY` 后可使用真实搜索（支持百度、Google、Bing 等）
- SerpAPI 申请地址: https://serpapi.com （有免费额度）

## 内容说明

### 服务器

- `src/mcp_demo/server.py` — FastMCP 服务器，暴露：
  - `add(a, b)` — 数字加法工具
  - `search_http(query, engine="baidu")` — 网络搜索工具
    - 支持多个搜索引擎：百度（baidu）、谷歌（google）、必应（bing）等
    - 默认使用演示数据，设置 `SERPAPI_API_KEY` 后使用真实搜索
  - `read_file(path)` — 文件读取工具
    - 读取 `sample_data` 文件夹下的文件（沙箱化）
    - 防止路径遍历攻击
  - 一个示例 **resource**：`sample://hello.txt`

### 客户端

- `client/demo_client.py` — 基础 MCP 客户端：
  - 通过 STDIO 以子进程方式启动服务器
  - 发送带有协议版本的 `initialize` 消息
  - 通过 `tools/list` 列出工具
  - 通过 `tools/call` 调用工具
  - 适合学习 MCP 协议的基本工作流程

- `client/openai_client.py` — OpenAI 集成客户端：
  - 演示如何将 MCP 工具与 OpenAI 的函数调用功能集成
  - 自动将 MCP 工具转换为 OpenAI 函数格式
  - 让 AI 模型智能决定何时调用哪些工具
  - 展示完整的 AI Agent 工作流程

### Web 应用

- `web/backend/main.py` — FastAPI 后端：
  - 启动时自动加载项目根目录的 `config.env`
  - 通过 OpenAI 兼容接口代理调用 DeepSeek（`api.deepseek.com`）
  - `/api/chat` 支持 SSE 流式输出
  - 生产模式下直接托管 `web/frontend/dist` 构建产物，单进程即可运行完整应用

- `web/frontend/` — React (Vite) 前端：
  - `src/App.jsx` — 聊天主界面（消息列表、输入框、建议问题）
  - `src/api.js` — 封装 `/api/chat` 的 SSE 流式请求
  - `src/index.css` — 现代化 UI 样式（含移动端适配）

## 说明

- 使用**官方 MCP SDK**（PyPI 上的 `mcp` 包）和 FastMCP 辅助工具。
- 传输方式是 **STDIO + Content-Length** 帧格式（LSP 风格），符合当前 MCP 规范。
- Web 应用使用 **React 18 + Vite 5 + FastAPI**，DeepSeek 调用走 OpenAI 兼容接口。
- 本项目避免硬编码外部令牌/密钥。HTTP 工具仅使用公共端点。

## 配置说明

### config.env（Web 应用）

- `DEEPSEEK_API_KEY` - DeepSeek API 密钥（**必填**，运行 Web 应用时需要）
  - 申请地址: https://platform.deepseek.com
- `BOCHA_API_KEY` - 博查 AI 搜索密钥（可选，推荐中文搜索）
  - 申请地址: https://open.bochaai.com
- `SERPAPI_API_KEY` - SerpAPI 密钥（可选，支持百度/Google/Bing 等）
  - 申请地址: https://serpapi.com
- `DEEPSEEK_BASE_URL` - DeepSeek API 地址（可选，默认 `https://api.deepseek.com`）
- `DEEPSEEK_MODEL` - 模型名称（可选，默认 `deepseek-chat`，可改为 `deepseek-reasoner`）
- `PORT` - 后端监听端口（可选，默认 `8000`）

> 配置 `BOCHA_API_KEY` 或 `SERPAPI_API_KEY` 任意一个即可启用真实搜索；都不配置时 `search_http` 返回演示数据。

### 环境变量（MCP 示例）

- `OPENAI_API_KEY` - OpenAI API 密钥（运行 `openai_client.py` 时必需）
- `SERPAPI_API_KEY` - SerpAPI 密钥（可选，用于真实搜索功能）
  - 不设置时使用演示数据
  - 设置后支持百度、Google、Bing 等多个搜索引擎
  - 申请地址: https://serpapi.com

## 安全性

- 文件工具被**沙箱化**到 `sample_data/` 目录，拒绝该目录外的路径访问
- 搜索工具使用可信的第三方 API（SerpAPI），避免直接网页爬取
- 所有外部请求都有超时和错误处理机制
- Web 应用的 `DEEPSEEK_API_KEY` 仅保存在服务端 `config.env`，不会下发到浏览器
- 有关生产级别的安全指南，请参阅 MCP 官方规范和最新的安全文档
