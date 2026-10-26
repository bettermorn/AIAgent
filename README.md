# AIAgent

AI Agent 教学与实战项目集：围绕 **DeepSeek 大模型**，从 ReAct、工具调用、RAG、MCP、A2A 到多智能体编排与人在回路，用一系列可运行的示例覆盖 AI Agent 开发的核心技术。

主要技术栈：**Python（LangChain / LangGraph / FastAPI）+ React（Vite）+ DeepSeek**，各项目均配有 B 站无声演示视频。

## 项目结构

```
AIAgent/
├── code/          # 各类 AI Agent 示例项目（详见下文）
├── docs/          # 科普文章、视频讲解、参考书籍等学习资料
└── courseware/    # 「从0到1构建 AI Agent」实战课程课件（AI4Edu 幻灯片）
```

## code/ 项目一览

| 项目 | 一句话介绍 |
| --- | --- |
| [A2A_Agent](code/A2A_Agent/) | 基于 Google A2A SDK + DeepSeek + React 的多 Agent 协作平台，支持 Agent Card 服务发现与串行、并行、路由、管道等协作模式。 |
| [AgentSkills](code/AgentSkills/) | 智能体技能（SKILL.md）演示，通过 React Web 应用或命令行输入主题，由 DeepSeek 生成结构化 PPT 大纲。 |
| [CSAIAgent](code/CSAIAgent/) | 基于 LangChain + Pinecone + FastAPI + React 的企业智能客服，支持 FAQ 问答、工单生成、投诉处理与多轮记忆。 |
| [CTAssessment](code/CTAssessment/) | 高中生计算思维在线测评智能体，AI 自动逐题判分并给出评价结论与个性化学习建议。 |
| [CodeAgent](code/CodeAgent/) | LLM 驱动的自主编程助手，可分析本地代码库、生成逐步执行计划并自我修正地完成代码修改。 |
| [EduAgent](code/EduAgent/) | 英语学习智能助手，基于 CEFR 课纲驱动，结合学习记忆追踪与自适应选题（间隔复习 + 薄弱点强化）。 |
| [EssayWriter](code/EssayWriter/) | 基于 LangGraph 的多 Agent 作文写作系统，串联「大纲规划 → 资料检索 → 草稿撰写 → 教师批改 → 修订迭代」完整流程。 |
| [GameNPC](code/GameNPC/) | 基于 LangGraph + DeepSeek 的多角色游戏 NPC 对话 Web 应用，AI 自动路由并支持多轮上下文感知的角色扮演。 |
| [HumanIntheLoop](code/HumanIntheLoop/) | 人在回路 Agent 演示，支持工具调用前人工审批、修改状态与时间回溯，检查点持久化于 PostgreSQL。 |
| [IAISWDaily](code/IAISWDaily/) | 工业智能/工业软件信息搜索智能体，定时检索网站、公众号、B 站等多渠道信息，自动去重摘要并生成每日日报。 |
| [IndustryAgent](code/IndustryAgent/) | 行业智能体集，包含辅助诊断与健康管理的医疗健康助手、以及法律助手两个子项目。 |
| [KBAgent](code/KBAgent/) | 基于 LangChain + FAISS + DashScope（通义千问）+ Gradio 的知识库 RAG 问答智能体。 |
| [MCPSevClient](code/MCPSevClient/) | MCP（Model Context Protocol）教学级实现，含 FastMCP 服务器、STDIO 客户端与 React 聊天界面。 |
| [MultiAgent](code/MultiAgent/) | 基于 AutoGen 多智能体框架的演示项目，包含芯片人才调研智能体与会议助手。 |
| [MultimodalCreativeGen](code/MultimodalCreativeGen/) | AI 多模态创意工坊，由文案、校对、设计三个 Agent 协作生成广告文案与 SVG 海报。 |
| [ReActAgent](code/ReActAgent/) | ReAct（推理 + 行动）循环的教学示例，包含 Bing 搜索决策与经典 ReAct 中文智能助手两个脚本。 |
| [StrategyEvolution](code/StrategyEvolution/) | 自进化商业报告生成代理，多级搜索兜底 + 迭代修订直至达到目标质量分数。 |
| [SuperAgent](code/SuperAgent/) | Manus 风格超级智能体，具备意图检测、LangGraph DAG 编排（规划/研究/写作/反思）、轻量 RAG 与安全策略检查。 |
| [TLAssessment](code/TLAssessment/) | 技术领导力评测智能体，在线问卷自动计分、AI 生成评价结论，并结合课程知识库与网络搜索输出学习路线图。 |
| [TradingStrategies](code/TradingStrategies/) | 金融交易策略教学演示，提供规则、LLM、混合三种策略 Agent 及带回测与实时决策的 React Web 应用。 |
| [enterprise_policy_agent.py](code/enterprise_policy_agent.py) | 企业制度问答 Agent（LangGraph + DeepSeek），基于制度知识库实现防幻觉的制度条款问答。 |

## docs/ 参考资料

- **科普文**：AI 工程的提示词工程、上下文工程、驾驭层工程与循环工程；AI Agent 与 Agentic AI 的区别、联系与应用边界；开发 AI 智能体的实战步骤等（见 docs/readme.md 中的 CSDN 链接）。
- **视频讲解**：台大李宏毅教授《机器学习》2026 春季课程（含 B 站链接）。
- **参考书籍**：《AI Agent 智能体开发实践》、《Agent 设计模式》、《动手学大模型智能体》等。

## 参考代码

- 黄佳《新手入门》：https://github.com/huangjia2019/ai-agents
- 黄佳《设计 AI Agent》：https://github.com/huangjia2019/designing-ai-agents
- 黄佳《知识库》：https://github.com/huangjia2019/ai-knowledge-base
- 姚宇航《从零构建 AI Agent：大模型驱动的智能体设计与实战》：https://github.com/yh-yao/super_agent_book

## 在线访问

- GitHub Pages：https://bettermorn.github.io/AIAgent/

