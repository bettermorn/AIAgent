# Game NPC LangGraph

一个基于 LangGraph + DeepSeek 的多智能体 **Web 应用**，让玩家在浏览器中与多个 NPC（村长、铁匠、药师）进行智能对话。

前端使用 **React**（Vite 构建），后端使用 **FastAPI**，由 **DeepSeek** 模型驱动，配置统一存放在 `config.env` 中。



程序运行演示

[【无声演示】多角色游戏对话智能体](https://www.bilibili.com/video/BV1qXhd6AEu1/)



## 参考代码

https://github.com/yh-yao/super_agent_book/tree/main/%E5%A4%9A%E8%A7%92%E8%89%B2%E6%B8%B8%E6%88%8F%E5%AF%B9%E8%AF%9D%E4%BD%93

## ✨ 特性

- **🌐 Web 界面**：React 聊天界面，深色主题设计，NPC 角色卡片
- **🤖 智能路由**：AI 自动根据对话内容选择最合适的 NPC 回答
- **💬 多轮对话**：支持连续对话，所有 NPC 都能看到完整的聊天历史
- **🎭 角色扮演**：每个 NPC 都有独特的人设和专业领域
- **🔄 上下文感知**：NPC 能够参考之前的对话内容，提供连贯的回复
- **🔑 集中配置**：API Key、模型名称、端口等统一在 `config.env` 中管理

## 🎮 NPC角色

- **🏛️ 村长**：村庄管理、历史故事、一般建议和信息
- **⚔️ 铁匠**：武器装备、打造修理、战斗相关
- **🌿 药师**：草药治疗、健康咨询、医疗相关

## 📦 项目结构

```
GameNPC/
├── config.env                  # 配置文件（DEEPSEEK_API_KEY 等）
├── requirements.txt            # Python 依赖
├── server.py                   # FastAPI 后端服务
├── game_npc_langgraph/         # LangGraph 核心
│   ├── config.py               # 加载 config.env 配置
│   ├── main.py                 # 状态图构建 + CLI 入口
│   ├── npc_agents.py           # NPC 角色定义和对话逻辑
│   └── router.py               # 智能路由器
└── frontend/                   # React 前端（Vite）
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        └── index.css
```

## 🛠️ 安装

### 1. 后端依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

编辑项目根目录的 `config.env`，将 `sk-xxx` 替换为你的 DeepSeek API Key：

```env
DEEPSEEK_API_KEY=sk-你的真实Key
DEEPSEEK_MODEL=deepseek-chat
```

API Key 可在 [DeepSeek 开放平台](https://platform.deepseek.com/) 申请。

### 3. 前端依赖

```bash
cd frontend
npm install
```

## 🚀 运行

需要**两个终端**分别启动后端和前端：

**终端 1：启动后端服务（端口 8000）**

```bash
python server.py
```

**终端 2：启动前端开发服务器（端口 5173）**

```bash

cd frontend
npm install
npm run dev
```

然后打开浏览器访问 **http://localhost:5173** 即可开始与 NPC 对话。

> 前端通过 Vite 代理将 `/api` 请求转发到后端 `127.0.0.1:8000`，无需额外跨域配置。

### API 接口


| 方法 | 路径        | 说明                                      |
| ---- | ----------- | ----------------------------------------- |
| GET  | `/api/npcs` | 获取可用 NPC 列表                         |
| POST | `/api/chat` | 发送消息，返回`{ npc, npc_emoji, reply }` |

请求示例：

```json
POST /api/chat
{
  "message": "我需要一把剑",
  "chat_history": [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "孩子，欢迎来到村落…"}
  ]
}
```

### 生产构建（可选）

```bash
cd frontend
npm run build   # 产物输出到 frontend/dist
```

## 💬 对话示例

```
你: 我需要一把剑
铁匠: 哈！又有人需要武器了！我这里有长剑、短剑，还有最新打造的符文剑…

你: 符文剑多少钱？
铁匠: 符文剑是我的得意之作！用的是上等精钢，镶嵌了火焰符文石，一把要200金币…

你: 谢谢！刚才试剑时不小心割伤了手，有什么药吗？
药师: 哎呀，让我看看伤口…这是愈合草药膏，涂抹后一天换两次药，三天就能愈合…
```

## 🖥️ 保留的 CLI 模式

也可以在终端中直接运行原生命令行版本：

```bash
python -m game_npc_langgraph.main
```

## 🏗️ 技术架构

- **React + Vite**：前端聊天界面与开发构建
- **FastAPI**：Web API 服务（`server.py`）
- **LangGraph**：状态图管理对话流程
- **LangChain**：LLM 调用和提示词管理
- **DeepSeek**（`deepseek-chat`）：驱动 NPC 对话与智能路由的大模型
- **python-dotenv**：从 `config.env` 加载配置
- **TypedDict**：类型安全的状态管理

## 🔧 核心组件

- `server.py` - FastAPI 后端，提供 `/api/npcs` 和 `/api/chat` 接口
- `game_npc_langgraph/config.py` - 配置加载（`config.env`）
- `game_npc_langgraph/main.py` - 状态图构建 + CLI 主循环
- `game_npc_langgraph/npc_agents.py` - NPC 角色定义和对话逻辑
- `game_npc_langgraph/router.py` - 智能路由器，选择合适的 NPC
- `frontend/src/App.jsx` - React 聊天界面

## 🎯 开发说明

- 基于 `requirements.txt` / `package.json` 的依赖管理
- TypedDict 提供类型安全
- 模块化设计，易于扩展新 NPC
- 支持历史记录的上下文对话
