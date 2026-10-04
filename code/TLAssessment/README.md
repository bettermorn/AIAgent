# 技术领导力评测智能体（Technical Leadership Assessment Agent）

基于《技术领导力评测问卷》构建的 AI 评测智能体：填写问卷后，自动计算四维度得分，由 **DeepSeek** 生成**评价结论**，并结合课程知识库与 **Bocha / SerpAPI** 实时搜索的网络资源，生成个性化**学习建议**。

## 功能

1. **在线问卷**：完整还原问卷的 4 个维度 / 12 个子维度 / 81 道评分题（1-5 分 + N/A）、各维度开放题与综合评价。
2. **评价结论**：按问卷第八节的计算方式（N/A 不计入分母、维度权重 30/30/25/15）计算得分，由 DeepSeek 输出总体评价、分维度点评、关键优势、主要短板与认知差异观察。
3. **学习建议**：融合三类知识源生成学习建议与 6-12 个月发展路线图：
   - `data/` 目录的 0-4 系列课程文件（从黑客到技术领袖、团队管理、商业影响力、可持续技术能力、技术贡献与专业贡献）；
   - CSDN 参考文章《【专业发展】技术领导力》：https://blog.csdn.net/weixin_38575258/article/details/124152079
   - Bocha / SerpAPI 网络搜索的最新学习资源（书籍、课程、社区）。
4. **报告管理**：评测记录存入 PostgreSQL，支持历史报告列表与详情查看（雷达图 + 得分明细 + AI 结论 + 学习建议 + 资源链接）。
5. **降级保障**：DeepSeek 或搜索不可用时，自动降级为基于规则/知识库的结论与建议，服务不中断。

## 技术栈


| 层     | 技术                                                     |
| ------ | -------------------------------------------------------- |
| 前端   | React 18 + Vite 5（自绘 SVG 雷达图、轻量 Markdown 渲染） |
| 后端   | Node.js 18+ / Express 4                                  |
| 大模型 | DeepSeek（`/chat/completions`）                          |
| 搜索   | Bocha AI Web Search（优先）+ SerpAPI Google 搜索（备选） |
| 数据库 | PostgreSQL（`pg` 驱动，JSONB 存储）                      |

## 项目结构

```
TLAssessment/
├── config.env                    # 配置（DeepSeek/SerpAPI/Bocha Key + PostgreSQL 连接）
├── data/                         # 问卷 PDF 与 0-4 参考课程文件
├── backend/                      # Node.js 后端
│   ├── package.json
│   └── src/
│       ├── server.js             # Express 入口（默认 :3001）
│       ├── config.js             # 读取根目录 config.env
│       ├── db.js                 # PostgreSQL 连接与建表
│       ├── data/
│       │   ├── questionnaire.js  # 问卷结构（81题/开放题/权重/等级）
│       │   └── knowledge.js      # 学习建议知识库（源自0-4文件与CSDN文章）
│       ├── services/
│       │   ├── scoring.js        # 得分计算与摘要生成
│       │   ├── deepseek.js       # DeepSeek：评价结论 / 学习建议
│       │   └── search.js         # Bocha / SerpAPI 搜索
│       └── routes/
│           └── assessments.js    # API 路由与报告生成编排
└── frontend/                     # React 前端（Vite，默认 :5173）
    └── src/
        ├── App.jsx               # 页面状态机（填写/生成中/报告/历史）
        ├── api.js
        ├── styles.css
        └── components/
            ├── QuestionnaireForm.jsx  # 分步问卷
            └── ReportView.jsx         # 报告（雷达图/Markdown/资源）
```

## 快速开始

### 1. 环境要求

- Node.js ≥ 18
- PostgreSQL ≥ 12（本机运行，默认端口 5432）
- 根目录已提供 `config.env`（含 DeepSeek、SerpAPI、Bocha 的 Key 与 PostgreSQL 连接信息），按需修改：

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash     # 可改为 deepseek-chat 等
SERPAPI_API_KEY=xxx
BOCHA_API_KEY=xxx
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=tl_assessment
POSTGRES_USER=xxx
POSTGRES_PASSWORD=xxx
```

### 2. 准备数据库

```bash
createdb tl_assessment    # 首次运行前创建数据库（表结构由后端自动创建）
```

### 3. 启动后端（端口 3001）

```bash
cd backend
npm install
npm start            # 生产启动；开发模式：npm run dev
# 健康检查
curl http://localhost:3001/api/health
```

### 4. 启动前端（端口 5173）

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 **http://localhost:5173** 即可开始评测。

## 使用流程

1. 填写基本信息（被评价人、评价关系、共事时间等）；
2. 分步完成 4 个维度的评分题（1-5 分或 N/A）与开放题；
3. 填写综合评价（综合评分、最突出/最需改进能力、关键案例、发展建议勾选）；
4. 提交后智能体自动执行：计算得分 → DeepSeek 生成评价结论 → Bocha/SerpAPI 搜索学习资源 → DeepSeek 结合知识库生成学习建议（约 1-2 分钟，页面自动跳转）；
5. 查看报告：总分与等级、四维度雷达图、子维度明细、AI 评价结论、个性化学习建议、网络学习资源清单；
6. 「历史报告」页可随时回看记录。

## API 一览


| 方法 | 路径                   | 说明                                                  |
| ---- | ---------------------- | ----------------------------------------------------- |
| GET  | `/api/health`          | 健康检查（模型与搜索配置状态）                        |
| GET  | `/api/questionnaire`   | 问卷结构（题目/权重/等级/选项）                       |
| POST | `/api/assessments`     | 提交评测，返回记录 ID（报告异步生成）                 |
| GET  | `/api/assessments`     | 历史记录列表                                          |
| GET  | `/api/assessments/:id` | 评测详情（轮询`status`: processing/completed/failed） |

提交示例：

```json
POST /api/assessments
{
  "basicInfo": { "evaluateeName": "张三", "relationship": "直接上级", "...": "..." },
  "answers": { "1": 4, "2": 5, "3": "N/A", "...": "..." },
  "openAnswers": { "teamwork": ["他把新人培养体系搭起来了"], "...": [] },
  "overall": {
    "ratings": { "teamwork": 4, "sustainability": 5, "business": 3, "contribution": 3, "overall": 4 },
    "topStrengths": ["技术深度"],
    "topImprovements": ["商业理解"],
    "keyCase": "主导核心平台重构，性能提升3倍",
    "developmentAreas": ["商业理解能力"]
  }
}
```

## 评分与解释规则（源自问卷）

- **维度得分** = 有效题目总分 ÷ 有效题目数量（N/A 不计入分母）；
- **加权总分** = Σ(维度得分 × 权重)，权重：团队管理 30% / 可持续发展专业能力 30% / 商业影响力 25% / 技术贡献和专业贡献 15%；
- **等级解释**：4.50-5.00 卓越｜3.80-4.49 良好｜3.00-3.79 达标｜2.00-2.99 部分达标｜1.00-1.99 未达标；
- 报告重点关注低于 3 分的题目；4/5 分评价提示需以事实与案例支撑；评测结果主要用于发展与改进，不作为唯一晋升或淘汰依据。

## 参考资料与知识库来源

- `data/技术领导力评测问卷.pdf`：问卷结构与评分规则
- `data/0转换之路：从黑客到技术领袖.pdf`：技术、商业与管理三力合一，35 岁以后如何做技术
- `data/1集结号与亮剑团队-团队管理.pdf`：寻找正确的人、管理人力资源、胶冻团队、技术管理工具
- `data/2 技术赋能商业：商业影响力.pdf`：用技术影响商业、撰写赋能商业的技术创新方案
- `data/3 以不变应万变：发展可持续的技术能力.pdf`：新技术学习方法论（五问）、知识分享、团队技术竞争力
- `data/4见贤思齐：技术贡献与专业贡献.pdf`：ACM 高级/杰出专业人员要求、技术贡献与专业贡献路径
- CSDN《【专业发展】技术领导力》：https://blog.csdn.net/weixin_38575258/article/details/124152079

## 常见问题

- **报告一直"生成中"**：检查 `config.env` 的 Key 是否有效、DeepSeek 模型名是否可用（可改为 `deepseek-chat`）；查看后端日志。
- **数据库连接失败**：确认 PostgreSQL 已启动、`tl_assessment` 库已创建、`config.env` 中连接信息正确。
- **无搜索结果**：Bocha/SerpAPI Key 无效时自动跳过搜索，学习建议仍会基于知识库生成。
- **端口冲突**：后端用 `PORT=xxxx npm start`，前端修改 `vite.config.js` 的 `server.port` 与代理目标。
