# Human in the Loop · DeepSeek · PostgreSQL

> 一个使用 **React + Node.js (Express) + PostgreSQL** 实现的「可人工介入」Agent 演示项目。
> 完全复刻 LangGraph 中 `interrupt_before` / 修改状态 / 时间回溯的思想，但底层用 **DeepSeek API** 替代 OpenAI，
> 状态持久化使用 **PostgreSQL (PostGreP)**，前端是现代化的 **React 18** 单页应用。

---

## ✨ 功能特性


| 模块                    | 说明                                                                                                            |
| ----------------------- | --------------------------------------------------------------------------------------------------------------- |
| 🧠**DeepSeek 模型**     | 通过`DEEPSEEK_API_KEY` 调用 OpenAI 兼容协议的 DeepSeek 接口（默认 `deepseek-chat`，可切换 `deepseek-reasoner`） |
| 🛠**工具调用**          | 内置`web_search` 工具，支持 Tavily 真实搜索；未配置 Tavily 时降级为模型内置回答                                 |
| ⏸**人工审批**          | 在执行工具前中断，支持**同意 / 拒绝 / 修改参数** 三种人工决策                                                   |
| ✏️**修改状态**        | 类似 LangGraph`update_state`，可编辑待执行的 tool_call 参数后再执行                                             |
| ⏪**时间回溯**          | 所有 AgentState 持久化为`checkpoint`，可一键回到任意 checkpoint 重新执行                                        |
| 💾**PostgreSQL 持久化** | 线程、消息、检查点全部存到 PostgreSQL，重启服务后历史仍在                                                       |
| 💬**现代化前端**        | React 18 + 深色 UI，聊天式交互 + 检查点时间线面板                                                               |

---

## 📂 项目结构

```
HumanIntheLoop/
├── config.env                 # 统一配置文件（DEEPSEEK_API_KEY / PostgreSQL 等）
├── README.md                  # 本文件
├── backend/                   # Node.js + Express 后端
│   ├── package.json
│   └── src/
│       ├── server.js          # Express 入口
│       ├── config.js          # 加载 config.env
│       ├── deepseek.js        # DeepSeek API 客户端
│       ├── tools.js           # 工具定义与执行（Tavily + 降级）
│       ├── agent.js           # LangGraph 风格的 Agent 状态机
│       └── db/
│           ├── pool.js        # PostgreSQL 连接池
│           ├── schema.sql     # 表结构
│           ├── init.js        # 初始化脚本
│           └── store.js       # 数据访问层（DAO）
└── frontend/                  # React 前端
    ├── package.json
    ├── public/index.html
    └── src/
        ├── index.js
        ├── App.js             # 主应用
        ├── App.css            # 样式
        ├── api.js             # REST API 封装
        └── components/
            ├── Sidebar.js
            ├── MessageBubble.js
            ├── ToolCallCard.js
            └── CheckpointList.js
```

---

## 🚀 快速开始

### 1. 准备环境

- Node.js **>= 18**
- 一个可访问的 **PostgreSQL** 实例（>= 12）
- 一个 **DeepSeek API Key**（在 [platform.deepseek.com](https://platform.deepseek.com) 申请）

### 2. 填写配置

编辑项目根目录的 [`config.env`](./config.env)：

```ini
# DeepSeek
DEEPSEEK_API_KEY=sk-你的真实密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=human_in_the_loop

# 可选：Tavily 搜索
TAVILY_API_KEY=
```

> ⚠️ 数据库如果不存在，后端首次启动时会自动创建（使用 `postgres` 超级库连接）。

### 3. 安装依赖

```bash
# 后端
cd backend
npm install

# 前端
cd ../frontend
npm install
```

> 如果你还想运行根目录的原始 Python 教程 `Lesson_5_Student.py`：
>
> ```bash
> pip install -r requirements.txt
> jupyter notebook Lesson_5_Student.py
> ```

### 4. 初始化数据库（可选）

后端启动时会自动建库建表。如需手动初始化：

```bash
cd backend
npm run db:init
```

### 5. 启动服务

```bash
# 终端 A：启动后端 (默认端口 3001)
cd backend
npm start

# 终端 B：启动前端 (默认端口 3000)
cd frontend
npm start
```

打开浏览器访问 [http://localhost:3000](http://localhost:3000)，即可看到 UI。

### 6. 生产部署（可选）

```bash
# 构建前端
cd frontend && npm run build

# 启动后端（会自动托管 build 产物）
cd ../backend && npm start
```

之后只需访问后端端口（默认 3001）。

---

## 🎬 使用示例：从问候到「时间回溯」

下面通过一个完整的故事，把所有关键能力串起来演示一遍。

### 场景 1：与助手对话

1. 浏览器打开 [http://localhost:3000](http://localhost:3000)，左下角点击「**＋ 新建**」。
2. 在底部输入框敲入：`你好，请自我介绍`，回车。
3. 前端展示你的消息和 DeepSeek 的回复（一个完整的 checkpoint 已经被持久化到 PostgreSQL）。

```
[你]          你好，请自我介绍
[助手]        你好！我是基于 DeepSeek 的研究助手，可以调用 web_search 工具…
```

> 这一刻 PostgreSQL 里多出一条记录：`threads` 一行 + `messages` 一行 + `checkpoints` 一行。

### 场景 2：触发人工审批（核心流程）

4. 输入：`旧金山现在天气怎么样？` 回车。
5. Agent 想调用 `web_search("San Francisco weather today")`，**自动暂停**：

```
⏸ Agent 请求执行以下工具，请审核：

┌──────────────────────────────────────────┐
│ 🔧 工具调用 #1                           │
│ web_search                                │
│ { "query": "San Francisco weather today" }│
│                                            │
│ [✅ 同意执行]  [❌ 拒绝]  [✏️ 修改参数]    │
└──────────────────────────────────────────┘
```

6. 三个选择会发生不同的分支（见下方"决策矩阵"）。

### 场景 3：修改工具参数

7. 点击「**✏️ 修改参数**」，编辑器打开，把 query 改成 `"San Francisco weather this weekend, in Celsius"`。
8. 点击「**💾 保存修改并执行**」。前端会用 `POST /api/threads/:id/modify` 提交，后端基于修改后的参数执行工具、再次调用 LLM。

### 场景 4：拒绝工具调用

9. 回到第 6 步，如果点「**❌ 拒绝**」，后端会插入一条"用户拒绝"消息，强制 DeepSeek 基于已有上下文直接回答（不再调用工具）。

### 场景 5：时间回溯

10. 看右侧面板「**🕒 Checkpoints**」，你已积累了一棵 checkpoint 树：
    - step 0：用户首次发言
    - step 1：LLM 返回自我介绍
    - step 2：用户问天气
    - step 3：LLM 决定调 web_search（pending）
    - step 4：同意执行后的工具结果
    - step 5：LLM 最终回答
11. 想重新走一次？把鼠标移到 step 2 上，点「**⏪ 时间回溯到此**」——后端会在原 checkpoint 下创建新分支，从那一刻重新执行 LLM。
12. 这正是 LangGraph 中 `get_state_history` + `update_state(as_node=...)` 的等价物。

### 决策矩阵

每个分支会写入若干个 `checkpoint`，并在分支起点用 `decision` 字段打标签（`approve` / `reject` / `modify`），形成下表中的树状结构。


| 用户选择     | 后端入口                        | 检查点树                              | decision 标签      |
| ------------ | ------------------------------- | ------------------------------------- | ------------------ |
| ✅**同意**   | `POST /api/threads/:id/approve` | `interrupt →[允 → tool → llm(终)]` | 第 1 个标`approve` |
| ❌**拒绝**   | `POST /api/threads/:id/reject`  | `interrupt →[拒 → llm(终)]`         | 第 1 个标`reject`  |
| ✏️**修改** | `POST /api/threads/:id/modify`  | `interrupt →[改 → tool → llm(终)]` | 第 1 个标`modify`  |

完整的 checkpoint 树形图：

```
                       ┌─ cp0 (input) ───────────────────────────────────┐
                       │ cp1 (LLM 提议)                                   │
                       │ cp2 (interrupt, next=['action']) ◀── 决策分叉点    │
                       │     │                                            │
                       │     ├─ cp3 (decision='approve')                  │
                       │     │    ├─ cp5 (tool result)                    │
                       │     │    └─ cp6 (LLM final, next=[])              │
                       │     │                                            │
                       │     ├─ cp4 (decision='reject')  ← 拒绝时不调工具    │
                       │     │    └─ cp7 (LLM direct answer, next=[])      │
                       │     │                                            │
                       │     └─ cp8 (decision='modify')                   │
                       │          ├─ cp9 (tool result, 用的是新参数)        │
                       │          └─ cp10 (LLM final, next=[])             │
                       └──────────────────────────────────────────────────┘
```

每个分支的 invariants（断言式约束）：


| 分支      | `decision` 字段 | 写入消息数                             | 工具是否执行           | LLM 是否被再次调用 |
| --------- | --------------- | -------------------------------------- | ---------------------- | ------------------ |
| ✅ 同意   | `'approve'`     | +2 (tool + final assistant)            | ✅                     | ✅                 |
| ❌ 拒绝   | `'reject'`      | +2 (rejection human + final assistant) | ❌                     | ✅ (禁用工具)      |
| ✏️ 修改 | `'modify'`      | +2 (tool + final assistant)            | ✅ (使用改写后的 args) | ✅                 |

三个分支写入的消息数都是 **+2**，但消息内容完全不同——这正是「同一状态下选择不同路径」的本质。

### 一个完整的 curl 调用链

不想用浏览器？直接走 REST API 也行：

```bash
# 1) 创建会话
TID=$(curl -s -X POST http://localhost:3001/api/threads \
  -H 'Content-Type: application/json' \
  -d '{"title":"demo"}' | jq -r .thread_id)

# 2) 提问
curl -s -X POST http://localhost:3001/api/threads/$TID/invoke \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"今天上海天气怎么样？"}]}'
# 返回：{ status: "interrupt", pending_tool_calls: [...], ... }

# 3) 同意执行（注意：本例中若 args 有改动，请用 /modify 接口）
curl -s -X POST http://localhost:3001/api/threads/$TID/continue \
  -H 'Content-Type: application/json' -d '{}'
# 返回：{ status: "end", messages: [...], ... }

# 4) 看 checkpoint 树
curl -s http://localhost:3001/api/threads/$TID/checkpoints | jq
```

---

## 🧠 Human-in-the-Loop 核心流程

本项目的 Agent 状态机复刻了 LangGraph 的关键能力：

```
  ┌─────────┐    tool_calls      ┌────────────┐
  │  LLM    │ ─────────────────▶ │  Action    │ ──▶ 工具执行
  └─────────┘                    └────────────┘
       ▲                              │
       │  AIMessage                   │ interrupt_before
       └──────────────────────────────┘
              ⏸ 等待人工决策
```

后端在以下时机各写入一条 `checkpoint`：

1. 用户输入加入到 state 时
2. LLM 节点完成后
3. Action 节点执行前后
4. 拒绝 / 修改 / 时间回溯分支

每个 checkpoint 都记录：

- `parent_id`：形成树状分支结构
- `step`：步骤编号
- `next_nodes`：当前可执行的下一节点
- 完整的 `messages` 列表（实现 LangGraph 的 reducer 合并语义）

---

## 🔌 REST API 速查


| 方法   | 路径                           | 说明                       |
| ------ | ------------------------------ | -------------------------- |
| GET    | `/api/health`                  | 健康检查                   |
| POST   | `/api/threads`                 | 新建会话                   |
| GET    | `/api/threads`                 | 列出全部会话               |
| GET    | `/api/threads/:id`             | 获取当前状态               |
| PATCH  | `/api/threads/:id`             | 修改会话标题               |
| DELETE | `/api/threads/:id`             | 删除会话                   |
| POST   | `/api/threads/:id/invoke`      | 发送用户消息并执行 Agent   |
| POST   | `/api/threads/:id/continue`    | 审批通过，继续执行工具     |
| POST   | `/api/threads/:id/reject`      | 拒绝当前工具调用           |
| POST   | `/api/threads/:id/modify`      | 修改工具参数后再执行       |
| POST   | `/api/threads/:id/replay`      | 从指定 checkpoint 重新执行 |
| GET    | `/api/threads/:id/checkpoints` | 列出所有 checkpoint        |
| GET    | `/api/checkpoints/:id`         | 获取单个 checkpoint 详情   |

---

## 🗄️ PostgreSQL 数据模型

```sql
threads       (thread_id PK, title, created_at, updated_at)
messages      (id, thread_id, msg_id, role, content, tool_calls JSONB, position, ...)
checkpoints   (checkpoint_id PK, thread_id, parent_id, step, next_nodes TEXT[], scratch)
thread_state  (thread_id PK, current_cp_id, lnode, count, scratch)
```

详细 DDL 见 [`backend/src/db/schema.sql`](./backend/src/db/schema.sql)。

---

## 🔁 从原始 Python 教程迁移的差异


| 原 Python 教程 (`Lesson_5_Student.py`)     | 本项目                                        |
| ------------------------------------------ | --------------------------------------------- |
| `ChatOpenAI(model="gpt-3.5-turbo")`        | `deepseek.chat(...)` 调用 DeepSeek            |
| `SqliteSaver.from_conn_string(":memory:")` | `pg` Pool 持久化到 PostgreSQL                 |
| `TavilySearchResults(max_results=2)`       | `tools.web_search`（可走 Tavily 或降级）      |
| `interrupt_before=["action"]`              | 后端`agent.invoke` 返回 `status: 'interrupt'` |
| `abot.graph.get_state_history(thread)`     | `GET /api/threads/:id/checkpoints` + UI 面板  |
| `abot.graph.update_state(...)`             | `POST /api/threads/:id/modify`                |
| `for event in abot.graph.stream(...)`      | 前端 React 流式状态更新                       |
| LangGraph 内核                             | 自己实现的 100+ 行 JavaScript 状态机          |

---

## 🐞 常见问题

**Q1：前端提示「后端未连接」？**
确认后端是否启动在 `3001`，并且 `frontend/package.json` 中 `"proxy": "http://localhost:3001"` 正确。

**Q2：报错 `password authentication failed for user "postgres"`？**
修改 `config.env` 中的 `POSTGRES_USER` / `POSTGRES_PASSWORD`，使其与本地 PostgreSQL 配置一致。

**Q3：DeepSeek 返回 401？**
检查 `DEEPSEEK_API_KEY` 是否正确，是否含有空格或换行。

**Q4：想用 DeepSeek-R1 推理模型？**
修改 `DEEPSEEK_MODEL=deepseek-reasoner` 即可（注意 R1 的 tool calling 支持有限，建议复杂场景下保留 `deepseek-chat`）。

**Q5：想让搜索工具真正联网？**
去 [tavily.com](https://tavily.com) 申请一个 API Key，填入 `TAVILY_API_KEY`。

---

## 📜 License

MIT
