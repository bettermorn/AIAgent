# 客服机器人 / 代码助手 / 多 Agent 协作系统 —— 数据库设计与技术选型

三个场景虽然都基于 PostgreSQL + pgvector 这个底座，但数据模型差异很大：客服机器人核心是"会话+知识库检索"，代码助手核心是"代码语义索引+工具执行"，多 Agent 系统核心是"任务编排+Agent 间通信"。下面逐一拆解。

---

# 一、客服机器人（Customer Service Bot）

## 1.1 核心需求

- 多轮对话上下文管理
- FAQ / 产品文档语义检索（RAG）
- 工单升级人工客服
- 工具调用（查订单、查物流、发起退款）
- 满意度评分与会话分析
- 意图识别、情绪识别用于路由

## 1.2 技术选型

| 组件 | 选型 | 说明 |
|---|---|---|
| 主数据库 | PostgreSQL + pgvector | 对话、知识库、工单一体化存储 |
| 会话缓存 | Redis | 存当前会话的短期上下文，减少对 PG 的高频读 |
| Embedding 模型 | OpenAI `text-embedding-3-small` 或 BGE 系列（可本地部署） | FAQ 知识库向量化 |
| RAG 框架 | LangChain / LlamaIndex | 封装检索+生成流程 |
| 消息队列（可选） | RabbitMQ / Kafka | 异步处理工单升级、通知客服 |
| 全文检索 | PostgreSQL 内置 `tsvector`（或混合检索） | 辅助关键词精确匹配，弥补语义检索的召回盲区 |

> 为什么不需要专用向量库：客服知识库通常是**万到十万级**文档量，pgvector 完全够用，没必要引入 Pinecone 这类额外组件增加运维复杂度。

## 1.3 数据库 Schema

```sql
-- 客户信息
CREATE TABLE customers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_id   text UNIQUE,              -- 对接业务系统的用户ID
  name          text,
  contact       jsonb,                    -- {phone, email, wechat...}
  vip_level     smallint DEFAULT 0,
  created_at    timestamptz DEFAULT now()
);

-- 会话（一次完整的客服交互）
CREATE TABLE conversations (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id   uuid REFERENCES customers(id),
  channel       text,                     -- web / app / wechat / phone
  status        text DEFAULT 'active',    -- active / escalated / closed
  intent        text,                     -- 识别出的主意图，用于路由统计
  sentiment     text,                     -- positive/neutral/negative
  started_at    timestamptz DEFAULT now(),
  closed_at     timestamptz,
  csat_score    smallint                  -- 结束后的满意度打分
);

-- 消息记录
CREATE TABLE messages (
  id              bigserial PRIMARY KEY,
  conversation_id uuid REFERENCES conversations(id),
  role            text NOT NULL,          -- user / assistant / system / agent(人工)
  content         text,
  tool_calls      jsonb,                  -- 本轮触发的工具调用详情
  tokens_used     int,
  created_at      timestamptz DEFAULT now()
);
CREATE INDEX idx_messages_conv ON messages(conversation_id, created_at);

-- 知识库（FAQ / 产品文档切片）
CREATE TABLE knowledge_base (
  id          bigserial PRIMARY KEY,
  category    text,                        -- 退换货/物流/账户...
  title       text,
  content     text,
  embedding   vector(1536),
  metadata    jsonb,                       -- {product_id, version, source_url}
  updated_at  timestamptz DEFAULT now()
);
CREATE INDEX idx_kb_embedding ON knowledge_base
  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_kb_fulltext ON knowledge_base
  USING gin (to_tsvector('simple', content));

-- 工单（升级人工）
CREATE TABLE tickets (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid REFERENCES conversations(id),
  priority        text DEFAULT 'normal',
  status          text DEFAULT 'open',
  assigned_agent  text,
  summary         text,                    -- AI 生成的会话摘要，给人工客服看
  created_at      timestamptz DEFAULT now()
);

-- 工具调用日志（查订单/退款等外部系统交互）
CREATE TABLE tool_invocations (
  id              bigserial PRIMARY KEY,
  message_id      bigint REFERENCES messages(id),
  tool_name       text,
  input_params    jsonb,
  output_result   jsonb,
  status          text,                    -- success / failed
  latency_ms      int,
  created_at      timestamptz DEFAULT now()
);
```

## 1.4 关键查询示例

```sql
-- 混合检索：语义 + 关键词，召回 FAQ
SELECT title, content,
       1 - (embedding <=> :query_embedding) AS semantic_score,
       ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', :query_text)) AS text_score
FROM knowledge_base
ORDER BY (0.7 * (1 - (embedding <=> :query_embedding))
        + 0.3 * ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', :query_text))) DESC
LIMIT 5;

-- 统计高频升级人工的意图，用于优化机器人话术
SELECT intent, count(*) FROM conversations
WHERE status = 'escalated' AND started_at > now() - interval '7 days'
GROUP BY intent ORDER BY count(*) DESC;
```

## 1.5 架构要点

- Redis 存"当前活跃会话的最近 N 轮对话"，PG 存全量历史（会话结束后异步落库/归档）
- `tickets.summary` 用 LLM 在升级瞬间生成，减轻人工客服阅读历史的负担
- 知识库建议加**版本号**和**生效时间**字段，避免产品文档更新后机器人还在用旧答案

---

# 二、代码助手（Code Assistant）

## 2.1 核心需求

- 代码库语义索引（函数/类级别检索）
- 项目级上下文管理（多文件、多次会话）
- 工具调用全过程留痕（文件读写、命令执行、测试结果）
- Diff / Patch 版本追踪
- 增量索引（代码变更后只重新 embedding 变化部分）

## 2.2 技术选型

| 组件 | 选型 | 说明 |
|---|---|---|
| 主数据库 | PostgreSQL + pgvector | 代码块向量 + 项目元数据 |
| 代码解析 | tree-sitter | 按 AST 切分函数/类，而不是粗暴按行数切块 |
| Embedding 模型 | `text-embedding-3-large` 或专用代码模型（如 CodeBERT / jina-embeddings-v2-code） | 代码语义比自然语言更依赖专用模型 |
| 版本控制集成 | 直接读 git（`libgit2` / `simple-git`） | commit hash 作为索引版本锚点，而非重复存储文件全文 |
| 本地场景 | SQLite + sqlite-vss（轻量级 CLI 工具场景） | 如果是单机 CLI 工具（类似 Cursor/Continue 本地索引），不一定需要重型 PG |
| 大规模场景 | Qdrant / Milvus | 如果要支持企业级多仓库、百万级代码块检索，pgvector 的 HNSW 构建和查询延迟会成为瓶颈 |

> 关键选型判断：**单机 IDE 插件类工具**（本地索引、几十到几百个仓库）用 SQLite 足够，启动快、零运维；**云端多租户代码助手服务**（SaaS，索引大量企业代码库）用 PostgreSQL + pgvector，需要并发、权限隔离、事务。

## 2.3 数据库 Schema（云端 SaaS 场景）

```sql
-- 项目/仓库
CREATE TABLE projects (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL,              -- 多租户隔离
  repo_url    text,
  default_branch text DEFAULT 'main',
  last_indexed_commit text,               -- 增量索引的锚点
  created_at  timestamptz DEFAULT now()
);

-- 代码块（函数/类级别切分，而非整文件）
CREATE TABLE code_chunks (
  id            bigserial PRIMARY KEY,
  project_id    uuid REFERENCES projects(id),
  file_path     text NOT NULL,
  symbol_name   text,                      -- 函数名/类名
  symbol_type   text,                      -- function/class/method
  language      text,
  start_line    int,
  end_line      int,
  content       text,
  embedding     vector(1536),
  commit_hash   text,                      -- 该代码块对应的 commit
  updated_at    timestamptz DEFAULT now()
);
CREATE INDEX idx_chunks_embedding ON code_chunks
  USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_chunks_project_file ON code_chunks(project_id, file_path);

-- 符号依赖关系（谁调用谁，便于"查找引用"类问题）
CREATE TABLE symbol_references (
  id              bigserial PRIMARY KEY,
  project_id      uuid REFERENCES projects(id),
  from_chunk_id   bigint REFERENCES code_chunks(id),
  to_symbol_name  text,
  reference_type  text                     -- calls / imports / extends
);

-- 开发会话（一次 Agent 辅助编码的交互）
CREATE TABLE coding_sessions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  uuid REFERENCES projects(id),
  user_id     uuid,
  task_desc   text,                        -- 用户的初始需求描述
  status      text DEFAULT 'running',      -- running/completed/failed
  started_at  timestamptz DEFAULT now()
);

CREATE TABLE messages (
  id          bigserial PRIMARY KEY,
  session_id  uuid REFERENCES coding_sessions(id),
  role        text,
  content     text,
  created_at  timestamptz DEFAULT now()
);

-- 工具执行日志（文件读写、shell命令、测试运行）
CREATE TABLE tool_executions (
  id            bigserial PRIMARY KEY,
  session_id    uuid REFERENCES coding_sessions(id),
  tool_name     text,                      -- read_file/write_file/run_shell/run_tests
  input_params  jsonb,
  output_result text,
  exit_code     int,
  duration_ms   int,
  created_at    timestamptz DEFAULT now()
);

-- 代码变更（Agent 生成的 diff/patch）
CREATE TABLE code_changes (
  id            bigserial PRIMARY KEY,
  session_id    uuid REFERENCES coding_sessions(id),
  file_path     text,
  diff_content  text,                      -- unified diff 格式
  applied       boolean DEFAULT false,
  applied_at    timestamptz,
  created_at    timestamptz DEFAULT now()
);
```

## 2.4 关键查询示例

```sql
-- 检索与用户问题语义相关的代码块（限定项目+分支）
SELECT file_path, symbol_name, content,
       1 - (embedding <=> :query_embedding) AS score
FROM code_chunks
WHERE project_id = :project_id
ORDER BY embedding <=> :query_embedding
LIMIT 10;

-- 增量索引：只处理 commit diff 中涉及的文件
-- （应用层逻辑：git diff --name-only old_commit new_commit，再对这些文件重新切块+embedding）

-- 追踪某次会话的完整操作轨迹（用于回放/审计）
SELECT tool_name, input_params, exit_code, created_at
FROM tool_executions
WHERE session_id = :session_id
ORDER BY created_at;
```

## 2.5 架构要点

- **按函数/类切分而非固定字符数切分**：代码助手的检索精度高度依赖 chunk 的语义完整性，tree-sitter 解析 AST 后按符号边界切，效果远好于简单滑动窗口
- **commit_hash 作为索引失效依据**：文件变更后，只需比对 commit diff 决定哪些 chunk 要重新 embedding，避免全量重建
- **工具执行要留痕且可回滚**：`code_changes` 表记录 diff 而非直接覆盖文件，方便用户审查后再 apply，也便于失败时回滚
- **多租户隔离**：`org_id`/`project_id` 做行级权限控制，可以用 PostgreSQL 的 Row Level Security（RLS）在数据库层强制隔离，而不只依赖应用层过滤

---

# 三、多 Agent 协作系统（Multi-Agent Collaboration）

## 3.1 核心需求

- 多个具备不同角色的 Agent（Planner / Executor / Reviewer / Tool-Agent...）
- 任务拆解与依赖管理（DAG / 树形结构）
- Agent 间消息传递（不是简单的线性对话，是多对多通信）
- 共享记忆 vs 私有记忆的隔离
- 完整的编排执行轨迹，便于调试"为什么 Agent A 的输出传给了 Agent B"

## 3.2 技术选型

| 组件 | 选型 | 说明 |
|---|---|---|
| 主数据库 | PostgreSQL + pgvector | 任务状态、Agent 配置、共享记忆 |
| Agent 间消息总线 | Redis Streams 或 Kafka | 高频率的 Agent 间通信，PG 直接写可能成为瓶颈，用消息队列削峰+解耦 |
| 编排框架 | LangGraph / AutoGen / CrewAI | 定义 Agent 协作的图结构和状态流转，底层仍落库到 PostgreSQL 做持久化 |
| 工作流引擎（复杂场景） | Temporal / Prefect | 需要长时间运行、支持重试和人工审批节点的场景（而不是简单的进程内编排） |
| 分布式追踪 | OpenTelemetry + Jaeger（可选） | 多 Agent 调用链路复杂，建议接入链路追踪便于调试 |

> 关键选型判断：Agent 之间如果只是**偶尔几条消息**的协作（比如 Planner 分配任务给 2-3 个 Executor），直接用 PostgreSQL 表 + 应用层轮询/LISTEN-NOTIFY 就够。如果是**高频、大规模并发**的 Agent 群体（比如几十个 Agent 实时协同），引入 Redis Streams/Kafka 做消息总线更合适，PostgreSQL 只做最终状态持久化。

## 3.3 数据库 Schema

```sql
-- Agent 定义（角色、能力配置）
CREATE TABLE agents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text,
  role          text,                      -- planner/executor/reviewer/researcher
  model         text,                      -- 使用的底层模型
  system_prompt text,
  tools_allowed jsonb,                     -- 该 Agent 可用的工具白名单
  created_at    timestamptz DEFAULT now()
);

-- 一次完整的多 Agent 协作运行
CREATE TABLE runs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  goal          text,                      -- 用户最初的目标描述
  status        text DEFAULT 'running',    -- running/completed/failed/paused
  started_at    timestamptz DEFAULT now(),
  ended_at      timestamptz
);

-- 任务（支持树形/DAG结构，parent_task_id 做拆解关系）
CREATE TABLE tasks (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id          uuid REFERENCES runs(id),
  parent_task_id  uuid REFERENCES tasks(id),  -- 自引用，形成任务树
  assigned_agent  uuid REFERENCES agents(id),
  description     text,
  status          text DEFAULT 'pending',    -- pending/in_progress/done/failed/blocked
  result          jsonb,
  depends_on      uuid[],                     -- 任务依赖，支持 DAG（非纯树）
  created_at      timestamptz DEFAULT now(),
  completed_at    timestamptz
);
CREATE INDEX idx_tasks_run ON tasks(run_id, status);
CREATE INDEX idx_tasks_parent ON tasks(parent_task_id);

-- Agent 间消息（多对多通信，不是简单线性对话）
CREATE TABLE agent_messages (
  id            bigserial PRIMARY KEY,
  run_id        uuid REFERENCES runs(id),
  task_id       uuid REFERENCES tasks(id),
  from_agent    uuid REFERENCES agents(id),
  to_agent      uuid REFERENCES agents(id),   -- NULL 表示广播到共享黑板
  message_type  text,                         -- request/response/broadcast/handoff
  content       text,
  metadata      jsonb,
  created_at    timestamptz DEFAULT now()
);
CREATE INDEX idx_agent_msg_run ON agent_messages(run_id, created_at);

-- 共享记忆（跨 Agent 可见的长期记忆，向量检索）
CREATE TABLE shared_memory (
  id            bigserial PRIMARY KEY,
  run_id        uuid REFERENCES runs(id),
  scope         text DEFAULT 'global',        -- global(全局共享) / agent_id(私有)
  content       text,
  embedding     vector(1536),
  importance    float DEFAULT 1.0,            -- 记忆重要性评分，用于遗忘机制
  metadata      jsonb,
  created_at    timestamptz DEFAULT now()
);
CREATE INDEX idx_memory_embedding ON shared_memory
  USING hnsw (embedding vector_cosine_ops);

-- 工具调用（任一 Agent 发起的外部工具调用）
CREATE TABLE tool_calls (
  id            bigserial PRIMARY KEY,
  task_id       uuid REFERENCES tasks(id),
  agent_id      uuid REFERENCES agents(id),
  tool_name     text,
  input_params  jsonb,
  output_result jsonb,
  status        text,
  created_at    timestamptz DEFAULT now()
);

-- 审批/人工介入节点（Human-in-the-loop）
CREATE TABLE approvals (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id       uuid REFERENCES tasks(id),
  requested_by  uuid REFERENCES agents(id),
  status        text DEFAULT 'pending',       -- pending/approved/rejected
  reviewer      text,
  comment       text,
  created_at    timestamptz DEFAULT now(),
  resolved_at   timestamptz
);
```

## 3.4 关键查询示例

```sql
-- 查看一次 run 的完整任务树（递归 CTE）
WITH RECURSIVE task_tree AS (
  SELECT *, 0 AS depth FROM tasks
  WHERE run_id = :run_id AND parent_task_id IS NULL
  UNION ALL
  SELECT t.*, tt.depth + 1
  FROM tasks t
  JOIN task_tree tt ON t.parent_task_id = tt.id
)
SELECT * FROM task_tree ORDER BY depth, created_at;

-- 检查某任务的所有依赖是否已完成，决定是否可以执行（任务调度核心逻辑）
SELECT id FROM tasks
WHERE run_id = :run_id AND status = 'pending'
  AND NOT EXISTS (
    SELECT 1 FROM unnest(depends_on) dep
    WHERE dep NOT IN (
      SELECT id FROM tasks WHERE status = 'done' AND run_id = :run_id
    )
  );

-- 检索某 Agent 可见的共享记忆（语义检索 + 作用域过滤）
SELECT content, importance
FROM shared_memory
WHERE run_id = :run_id AND (scope = 'global' OR scope = :agent_id)
ORDER BY embedding <=> :query_embedding
LIMIT 8;
```

## 3.5 架构要点

- **任务表用 `depends_on` 数组而非纯 `parent_task_id`**：多 Agent 协作常常是 DAG 而非严格树形（比如任务 C 需要等 A 和 B 都完成），纯父子关系表达不了这种依赖
- **`agent_messages` 和 `shared_memory` 分开**：前者是"过程性"的通信记录（调试、审计用），后者是"结果性"的知识沉淀（给后续任务复用），语义不同，混在一起会导致检索噪音
- **用 PostgreSQL 的 `LISTEN/NOTIFY` 做轻量级事件通知**：如果不想引入 Kafka，中小规模场景可以直接用 PG 自带的发布订阅机制触发任务调度，减少组件数量
- **`importance` 字段支持记忆衰减/遗忘机制**：避免 shared_memory 无限增长导致检索噪声变大，可以定期跑一个清理任务，低重要性且长期未被检索命中的记忆做归档或删除

---

## 四、三个场景的技术选型横向对比

| 维度 | 客服机器人 | 代码助手 | 多 Agent 协作系统 |
|---|---|---|---|
| 核心存储复杂度 | 低-中 | 中-高（符号关系、增量索引） | 高（任务图、消息总线） |
| 向量检索规模 | 万~十万级 | 万~百万级（企业代码库） | 中等，更关注记忆的"重要性筛选"而非纯规模 |
| 是否需要消息队列 | 可选（工单异步通知） | 不太需要 | 建议引入（Agent 间高频通信） |
| 是否需要工作流引擎 | 不需要 | 不需要 | 复杂场景建议（Temporal/LangGraph） |
| 多租户隔离 | 中等重要 | 非常重要（企业代码隐私） | 视产品形态而定 |
| 事务一致性要求 | 中 | 中（diff/apply 需要原子性） | 高（任务状态流转不能脏读） |