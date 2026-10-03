# 计算思维测试智能体（CT Assessment Agent）

基于《高中生计算思维能力评测问卷》开发的计算思维测试智能体。学生在线完成测评后，AI 智能体自动判分、给出**评价结论**，并结合本地知识库（《用不同语言训练计算思维》《日常任务练习计算思维》）与互联网搜索，生成**个性化学习建议**。

## 功能

### 1. 在线测评

- **第一部分 基本信息**：年级、编程经历、接触过的编程语言、使用图表整理问题的习惯。
- **第二部分 自评量表**：20 道李克特五点量表题（分解问题 / 模式识别 / 抽象 / 算法设计各 5 题，第 4、9、14、19 题为反向题，自动反向计分）。
- **第三~五部分 情境与能力测试**：14 道情境题共 85 分（分解问题 20 / 模式识别 13 / 抽象 16 / 算法设计 16 / 综合开放题 12 / 人工智能问题 8）。

### 2. 评价结论

- 自评量表按问卷评分方法逐维度计分并分级（较强 / 中等 / 需要进一步培养）。
- **DeepSeek 大模型**按问卷中每题的评分标准与参考答案逐题判分，给出每题点评、六维度教师点评、优势与不足。
- 按百分制换算并划分能力水平：85—100 较强、70—84 良好、60—69 中等、60 以下需要加强。
- 生成 300—500 字的综合性评价结论（对比自评与实测的一致性，指出最需提升的维度）。
- 报告页展示维度得分条形图、逐题评分明细、自评 vs 实测对比。

### 3. 个性化学习建议

- 针对薄弱维度（得分率 < 70%），结合两份本地知识库生成建议：
  - **《用不同语言训练计算思维》**：按学生接触过的编程语言（Python / Java / C/C++）匹配对应的四维度理论知识与学习行为建议；
  - **《日常任务练习计算思维》**：购物算法、学习算法、整理房间、旅行规划等日常训练方法，以及每天 10—15 分钟的可执行训练计划。
- **互联网搜索补充资源**：优先使用 SERPAPI，失败时自动回退到 BOCHA（博查），搜索结果缓存于 PostgreSQL，推荐资源附真实链接。
- 建议内容包含：总体建议、分维度行动建议（含日常练习 + 编程练习）、四周训练计划、推荐资源、效果检验方法。

## 技术栈


| 层     | 技术                                     |
| ------ | ---------------------------------------- |
| 前端   | React 18 + Vite 5                        |
| 后端   | Node.js + Express                        |
| 大模型 | DeepSeek Chat API（`deepseek-v4-flash`） |
| 数据库 | PostgreSQL（测评记录 + 搜索缓存）        |
| 搜索   | SERPAPI / BOCHA API（自动回退）          |

## 项目结构

```
CTAssessment/
├── config.env                     # API Key 与数据库配置（项目已提供）
├── data/                          # 原始 PDF 资料
│   ├── 高中生计算思维能力评测问卷.pdf
│   ├── 用不同语言训练计算思维.pdf
│   └── 日常任务练习计算思维.pdf
├── server/                        # Node.js 后端
│   ├── package.json
│   └── src/
│       ├── index.js               # 入口（Express 应用）
│       ├── config.js              # 读取 config.env / .env 配置
│       ├── db.js                  # PostgreSQL 连接与建表
│       ├── routes/
│       │   └── assessments.js     # REST API 路由
│       ├── services/
│       │   ├── deepseek.js        # DeepSeek API 封装（含 JSON 稳健解析）
│       │   ├── assessment.js      # 自评计分 + AI 判分 + 评价结论生成
│       │   ├── advice.js          # 学习建议生成（知识库 + 搜索）
│       │   └── search.js          # SERPAPI / BOCHA 搜索（带缓存与回退）
│       └── data/
│           ├── questionnaire.js   # 问卷结构化数据（题目/评分标准/参考答案）
│           └── knowledge.js       # 学习建议知识库（两份 PDF 内容）
└── client/                        # React 前端
    ├── package.json
    ├── vite.config.js             # 开发代理 /api → localhost:3001
    └── src/
        ├── App.jsx                # 页面路由（首页/答题向导/报告/历史）
        ├── api.js                 # 后端接口封装
        ├── styles.css             # 全局样式
        └── components/
            ├── BasicInfoStep.jsx  # 第一步：基本信息
            ├── SelfRatingStep.jsx # 第二步：自评量表
            ├── TasksStep.jsx      # 第三步：情境测试
            ├── ReportView.jsx     # 测评报告 + 学习建议展示
            └── HistoryView.jsx    # 历史记录
```

## 快速开始

### 前置条件

- Node.js ≥ 18
- PostgreSQL 已安装并运行

### 1. 配置

项目根目录已提供 `config.env`（包含 DeepSeek、SERPAPI、BOCHA 的 Key 与 PostgreSQL 连接信息）。如需修改：

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

SERPAPI_API_KEY=xxx
BOCHA_API_KEY=sk-xxx

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ct_assessment
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
```

> 数据库无需手动建表，应用启动时自动创建 `assessments` 和 `search_cache` 表；但需要先创建数据库：
>
> ```bash
> createdb ct_assessment        # 或 psql -c "CREATE DATABASE ct_assessment;"
> ```

### 2. 启动后端（端口 3001）

```bash
cd server
npm install
npm start          # 生产模式
# 或
npm run dev        # 开发模式（文件变更自动重启）
```

### 3. 启动前端（端口 5173）

```bash
cd client
npm install
npm run dev
```

打开浏览器访问 [http://localhost:5173](http://localhost:5173) 即可开始使用。

## API 接口


| 方法 | 路径                             | 说明                                                    |
| ---- | -------------------------------- | ------------------------------------------------------- |
| GET  | `/api/health`                    | 健康检查                                                |
| GET  | `/api/assessments/questionnaire` | 获取问卷结构（题目，不含参考答案）                      |
| POST | `/api/assessments/submit`        | 提交答卷：自评计分 → DeepSeek 判分 → 生成结论 → 存库 |
| POST | `/api/assessments/:id/advice`    | 生成/重新生成学习建议（搜索互联网 + 知识库）            |
| GET  | `/api/assessments/:id`           | 获取测评详情                                            |
| GET  | `/api/assessments`               | 历史记录列表（最近 50 条）                              |

### 提交示例

```bash
curl -X POST http://localhost:3001/api/assessments/submit \
  -H "Content-Type: application/json" \
  -d '{
    "studentName": "小明",
    "basicInfo": { "grade": "高一", "programmingExp": "学习过少量编程", "languages": ["Python"], "chartsUsage": "有时" },
    "selfRating": { "s1": 4, "s2": 3, "...": "共20题" },
    "tasks": { "t1": "我先把任务分为...", "...": "共14题" }
  }'
```

## 工作流程

```
学生作答（基本信息 → 自评量表 → 14道情境题）
        │
        ▼
POST /submit
        ├─ ① 自评量表计分（反向题 6-x 转换，逐维度汇总 ≤25 分）
        ├─ ② DeepSeek 按每题评分标准+参考答案逐题判分（JSON 输出，服务端钳制分数上限）
        ├─ ③ DeepSeek 综合自评+实测生成评价结论
        └─ ④ 结果写入 PostgreSQL
        │
        ▼
报告页查看（总分/等级、六维度得分、逐题明细、自评vs实测对比）
        │
        ▼
点击"生成学习建议" POST /:id/advice
        ├─ ① 识别薄弱维度（得分率<70%）
        ├─ ② SERPAPI 搜索（失败回退 BOCHA，结果缓存）
        ├─ ③ DeepSeek 结合《用不同语言训练计算思维》+《日常任务练习计算思维》知识库
        │     与搜索结果，生成结构化建议（总体/分维度/四周计划/资源/检验方法）
        └─ ④ 建议存入 PostgreSQL，报告页渲染
```

## 评分依据

- 自评量表：每个维度 5 题、满分 25 分；21—25 较强，16—20 中等，5—15 需要进一步培养。
- 情境测试总分 85 分，按 `百分制 = 实际得分 / 85 × 100` 换算；85—100 较强，70—84 良好，60—69 中等，60 以下需要加强。
- AI 判分遵循问卷的评分原则：重视过程不只看最终答案、允许多种合理答案、未作答记 0 分。

## 说明

- 本系统主要用于学习和教学诊断，不作为学生能力或成绩的唯一评价依据。
- AI 判分结果可能存在一定随机性，可通过"重新生成建议"、教师复核等方式校准。
- 搜索缓存表 `search_cache` 可定期清理以刷新资源推荐。
