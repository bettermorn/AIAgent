# 海上风电场运维智能体（Offshore Wind O&M Agent）

按《海上风电场运维智能体 技术设计方案 V2.0》实现的可运行系统：
**知识图谱（可信底座） + DeepSeek 大模型（理解与生成） + 总控/专业多 Agent（规划、工具调用、闭环执行）**，数据库为 **PostgreSQL**。

## 快速开始

前置：Python 3.10+，本机 PostgreSQL（默认 `localhost:5432`，用户 `postgres`），`config.env` 中已配置 `DEEPSEEK_API_KEY`。

```bash
cd code
pip install -r requirements.txt
python3 manage.py check        # 检查 PostgreSQL 与 DeepSeek 连通
python3 manage.py restock      # 演示复位（可选）：恢复备件库存、停止故障、取消未结工单
python3 manage.py serve        # 首次启动自动建库(windom_agent)/建表/写入初始化数据，然后监听 :8000
```

浏览器打开 <http://localhost:8000>（API 文档：`/docs`）。演示账号密码均为 `windom123`：

| 账号 | 角色 | 说明 |
| --- | --- | --- |
| operator1 | 值班运维 | 问答/诊断，可见两个风场 |
| operator2 | 值班运维 | 仅二号场（演示 ABAC 风场隔离） |
| engineer1 | 检修工程师 | 执行/关闭工单 |
| approver1 / approver2 | 授权审批人 | L2/L3 审批（L3 须两人双签+作业票）、故障注入、模型迭代 |
| kadmin1 / expert1 | 知识管理员 / 领域专家 | 知识审核（涉及安全/新故障模式须专家） |
| admin | 管理员 | 全部 |

> 配置：`config.env` 读取 `DEEPSEEK_API_KEY`、`PGHOST/PGPORT/PGUSER/PGPASSWORD`。业务库名默认 `windom_agent`（可用 `WINDOM_PGDATABASE` 覆盖），**不会触碰** `PGDATABASE` 指向的其他项目库。

## 演示

完整的分角色演示手册见 **[DEMO.md](DEMO.md)**（约 25 分钟，覆盖 operator / engineer / approver 双人 / 知识管理员 / 领域专家 / admin 共 8 个账号，并含自动化自检 `tests/demo_walkthrough.py`）。

## 目录

```
code/
├── manage.py                  # 管理入口: initdb/seed/serve/check/inject/restock/reset
├── DEMO.md                    # 分角色演示手册
├── config.env                 # 密钥与数据库配置
├── windom/
│   ├── config.py db.py schema.sql   # 配置 / PostgreSQL 访问层 / 数据模型
│   ├── ontology.py seed*.py         # 本体与故障因果知识 / 初始化数据
│   ├── llm.py                       # DeepSeek(OpenAI 兼容) 封装: JSON 重试、流式、token 计量
│   ├── security.py                  # RBAC+ABAC、JWT、输入/输出护栏、风险分级、哈希链审计(WORM)
│   ├── services/                    # 图谱/文档检索/时序双库/规则/诊断/能效/资源/工单/知识工程/改进/报表
│   ├── tools/                       # 工具注册中心(MCP 风格): Schema 校验、最小权限、配额、熔断、审计
│   ├── agents/                      # 总控 Agent + 7 个专业 Agent（六层内部结构）
│   ├── edge/                        # 边缘节点(72h 缓存/断链续传/校验和幂等) + SCADA 仿真器
│   ├── jobs.py                      # 后台作业（Temporal 的单机等价实现）
│   └── api/app.py                   # FastAPI: REST + SSE + WebSocket
├── web/                             # 单页前端（无需构建）
└── tests/                           # 单元 / API 端到端 / 前端冒烟
```

## 设计要点与落地对应

| 文档要求 | 实现 |
| --- | --- |
| 知识图谱：时态、版本、溯源、约束校验 | PostgreSQL `kg_entities/kg_relations`（`valid_from/valid_to/source/version/confidence/status`），递归多跳查询；部件更换保留履历；规程新版本使旧引用失效 |
| LLM 抽取 + 5 层校验 | `services/knowledge_eng.py`：Schema → 术语归一化 → 图谱约束 → 台账/工单交叉验证 → 专家审核；LLM 输出不直接入图 |
| 总控 + 专业 Agent | `agents/orchestrator.py`；工具白名单见 `tools/defs.py`（总控无任何业务工具） |
| 状态机 / Checkpoint / HITL | `agent_tasks` 状态流转、`agent_checkpoints`、`WaitingApproval`；暂停/终止/恢复/回滚 |
| 风险分级 L0–L4 | `security.classify_task_risk`；L3 仅提示，工单需作业票 + 两名不同审批人；L4 低置信转人工 |
| 多级预警、紧急工单、30min 响应 | `services/rules.py`、`workorders.py`；≥二级自动紧急工单，响应时长计入 KPI，超时升级通知 |
| 实时/历史双时序库、边缘 72h 缓存 | `ts_realtime`/`ts_history` + 归档作业；`edge/node.py` 断链缓存、优先级补传、校验和幂等 |
| GraphRAG 混合检索 | 向量(哈希嵌入) + BM25 → RRF → 重排，默认只取 `status=active` 规程 |
| 持续改进闭环 | `services/improve.py`：反馈收集 → RCA → 参数校准 → 黄金集门禁（≥85%）→ 灰度/全量，≤30 天周期 |
| 审计与追溯 | `audit_log` 哈希链 + 触发器禁止 UPDATE/DELETE；`/audit/verify` 校验 |
| 规范指标达标表 | `/api/v1/kpi/compliance` 与「报表中心」 |

## 与设计文档的差异（诚实说明）

以下按文档选型需外部基础设施，本实现用可直接运行的等价方案替代，接口已隔离，可平滑替换：

- **图数据库 Neo4j / 向量库 Milvus / 时序库 TDengine / ES / Kafka / MinIO / Redis**：统一用 PostgreSQL 实现（图用关系表+递归查询；向量用哈希 n-gram 嵌入；时序用双表；对象存储仅记录元数据）。
- **bge-m3 / bge-reranker、vLLM 私有化 Qwen**：按要求使用 DeepSeek 云端 API；嵌入替换点为 `services/embedding.py::embed`。
- **LangGraph / Temporal / MCP / A2A / Keycloak / OPA / Vault**：用自研的等价最小实现（状态机+Checkpoint、`jobs.py` 调度、工具注册中心、JWT+RBAC/ABAC）。
- **SCADA、EAM、AIS、气象**：由仿真器与种子数据提供；真实对接时替换 `edge/` 与 `seed.refresh_weather`。
- 场站网络、IP65、等保三级等属场站建设范畴，仅在达标表中标注。

## 测试

```bash
python3 -m pytest tests/test_unit.py -q                 # 32 项单元测试（含 WORM、边缘缓存、护栏、贝叶斯排序）
python3 manage.py serve &                               # 另开终端
python3 -m pytest tests/test_e2e_api.py -q              # 19 项端到端（真实 PostgreSQL + DeepSeek）
node tests/frontend_smoke.js                            # 前端全部视图冒烟
```

## 注意事项

- Agent **没有任何向 SCADA 写控制指令的工具**；停机/降负荷/改参数等 L3 操作只给提示。
- `reset` 命令会清空 `windom_agent` 库，仅用于开发。
- 生产使用前请修改 `WINDOM_JWT_SECRET` 与演示账号密码（`WINDOM_DEMO_PASSWORD`），并将 `config.env` 移出版本库。
