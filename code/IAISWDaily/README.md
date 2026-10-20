# 工业智能 · 工业软件 信息搜索智能体

每天定时检索**国际/国外网站、微信公众号、B站**上与「工业智能 / 工业软件」相关的信息，用 **DeepSeek** 做去重、相关性判定、中文摘要与重要性评分，并自动生成**每日日报**；结果存入 **PostgreSQL**，通过 **React** 前端浏览与检索。



## 一、功能


| 能力          | 说明                                                                                                                                                                                   |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 定时采集      | 默认每天 08:00（Asia/Shanghai）自动执行，cron 表达式可在前端「配置」页修改并热生效                                                                                                     |
| 多渠道检索    | 国际/国外网站（SerpAPI → Google）、微信公众号（搜狗微信，失败回退博查）、B站（官方搜索接口 + WBI 签名，失败回退博查）、中文资讯（博查全网搜索）                                       |
| DeepSeek 检索 | 接入 DeepSeek`POST /v1/tools/search`（自研搜索引擎，支持 `site:` / `lang:` / `after:` 语法），可与现有搜索源兜底、优先或并行合并；并用 `POST /v1/tools/fetch` 抓取原文正文补充过短摘要 |
| 智能总结      | DeepSeek 逐条生成 60-120 字中文摘要、分类（工业智能/工业软件/政策标准…）、标签、0-10 重要性评分，并过滤娱乐、股票等无关噪声                                                           |
| 每日日报      | DeepSeek 基于当日条目生成：总体综述、5-8 条重点信息、3-5 条趋势洞察                                                                                                                    |
| 检索与归档    | 前端按渠道/时间/关键词检索历史信息；日报按日期归档，可切换查看                                                                                                                         |
| 手动触发      | 前端「立即采集」按钮或命令行`npm run run:once`                                                                                                                                         |



## 二、技术栈

- **前端**：React 18 + Vite 5（端口 5173，开发态代理 `/api` 到后端）
- **后端**：Node.js 18+（ESM）+ Express 4 + node-cron
- **模型**：DeepSeek（`deepseek-chat`，OpenAI 兼容 `/chat/completions`）
- **搜索**：DeepSeek Search/Fetch（`POST /v1/tools/search`、`POST /v1/tools/fetch`）、SerpAPI（Google）、博查 Bocha（中文全网）、B站官方搜索接口、搜狗微信
- **数据库**：PostgreSQL（`pg` 驱动）



## 三、目录结构

```
.
├── config.env                 # API Key 与数据库配置（已存在）
├── server/                    # 后端
│   ├── package.json
│   └── src/
│       ├── index.js           # Express 入口（生产态托管前端 dist）
│       ├── config.js          # 配置加载（读取根目录 config.env）
│       ├── db/
│       │   ├── schema.sql     # 表结构：articles / runs / reports / settings
│       │   ├── pool.js        # PostgreSQL 连接池（含启动自动建库）
│       │   ├── migrate.js     # 初始化迁移脚本
│       │   ├── articlesRepo.js
│       │   ├── reportsRepo.js
│       │   └── settingsRepo.js
│       ├── services/
│       │   ├── searchProviders.js  # 渠道分发：international / wechat / bilibili / news
│       │   ├── deepseekTools.js    # DeepSeek Search /v1/tools/search + Fetch /v1/tools/fetch
│       │   ├── wechatProvider.js   # 搜狗微信搜索 + 真实链接解析
│       │   ├── bilibiliWbi.js      # B站 WBI 签名与 Cookie
│       │   ├── summarizer.js       # DeepSeek 摘要 / 相关性判定 / 日报生成
│       │   ├── pipeline.js         # 采集 → 去重入库 → 总结 → 日报
│       │   ├── scheduler.js        # node-cron 定时调度
│       │   └── http.js
│       ├── routes/api.js
│       └── jobs/collectNow.js # 命令行手动采集
└── web/                       # React 前端
    ├── vite.config.js
    ├── dist/                  # 构建产物（npm run build 生成，由后端托管）
    └── src/
        ├── App.jsx
        ├── api.js
        ├── styles.css
        └── components/        # ReportPanel / ArticlesPanel / RunsPanel / SettingsPanel
```

关键路径：

- 密钥与数据库配置：**仓库根目录 `config.env`**（非 `server/config.env`）
- 后端入口：`server/src/index.js`；路由：`server/src/routes/api.js`
- 检索实现：`server/src/services/searchProviders.js`、`deepseekTools.js`
- 表结构：`server/src/db/schema.sql`；迁移：`server/src/db/migrate.js`



## 四、安装与启动

### 0. 前置条件


| 依赖       | 要求                                   | 说明                                     |
| ---------- | -------------------------------------- | ---------------------------------------- |
| Node.js    | 18+（推荐 20/22，本项目实测 v22.23.2） | 后端使用 ESM，前端需 Vite 5              |
| npm        | 随 Node.js 安装（实测 10.9.8）         |                                          |
| PostgreSQL | 已安装且服务运行中                     | 只需有可建库权限的账号，**库会自动创建** |

确认 PostgreSQL 已启动：

```bash
pg_isready            # 期望输出：/tmp:5432 - accepting connections
```

### 1. 进入项目根目录

`config.env`、`package.json` 都位于仓库根目录（即 `server/` 与 `web/` 的上一级）。**除特别说明外，所有命令都在这里执行**


### 2. 安装依赖（两步，缺一不可）

```bash
npm install          # 根目录：安装 concurrently（npm run dev 并行启动依赖它）
npm run install:all  # 子项目：等价于 (cd server && npm install) && (cd web && npm install)
```

> 只跑后端时 `npm run install:all` 可省略，改为 `cd server && npm install`。

### 3. 配置密钥与数据库

编辑**仓库根目录**的 `config.env`（已内置可用密钥，按需改）。服务启动时会检查 `PGDATABASE` 指定的库是否存在：不存在则自动创建（账号需 `CREATEDB` 权限），已存在则跳过。

```env
DEEPSEEK_API_KEY=sk-xxx               # 必填：总结 / 日报生成 + Search / Fetch 工具
PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=
PGDATABASE=iaisw_daily
PG_AUTO_CREATE=true                   # 关闭自动建库则设为 false，并手动 createdb iaisw_daily
DEEPSEEK_SEARCH_MODE=supplement       # DeepSeek 检索协作方式：off/fallback/primary/supplement
```

完整变量说明见 [五、配置说明](#五配置说明)。

### 4. 初始化表结构

```bash
npm run migrate       # 建库（如需）→ 执行 server/src/db/schema.sql → 写入默认配置
```

输出 `[migrate] 完成，数据库: iaisw_daily` 即成功。

### 5. 启动开发环境

```bash
npm run dev           # 并行启动：后端 http://localhost:8787，前端 http://localhost:5173
```

打开 [http://localhost:5173](http://localhost:5173)；后端健康检查：[http://localhost:8787/api/health](http://localhost:8787/api/health)。

手动触发一次采集（也可用前端「立即采集」按钮）：

```bash
npm run run:once
```

### 6. 生产模式

```bash
npm run build         # 构建前端产物到 web/dist
npm start             # 后端 8787 直接托管 web/dist，访问 http://localhost:8787
```

### 7. 命令速查


| 命令                                | 执行位置  | 说明                         |
| ----------------------------------- | --------- | ---------------------------- |
| `npm install`                       | 根目录    | 安装`concurrently` 等根依赖  |
| `npm run install:all`               | 根目录    | 安装`server/` 与 `web/` 依赖 |
| `npm run migrate`                   | 根目录    | 自动建库 + 建表 + 默认配置   |
| `npm run dev`                       | 根目录    | 后端 8787 + 前端 5173        |
| `npm run run:once`                  | 根目录    | 立即执行一次采集             |
| `npm run build`                     | 根目录    | 构建前端到`web/dist`         |
| `npm start`                         | 根目录    | 生产模式启动后端并托管前端   |
| `npm run dev`                       | `server/` | 仅启动后端（node --watch）   |
| `npm run migrate`                   | `server/` | 同上，仅后端视角的迁移       |
| `npm run collect`                   | `server/` | 同根目录`run:once`           |
| `npm run dev` / `build` / `preview` | `web/`    | 仅前端开发 / 构建 / 预览     |

端口：后端 `PORT`（默认 8787），前端 Vite（`web/vite.config.js` 固定 5173，并将 `/api` 代理到 8787）。



## 五、配置说明

`config.env` 中已提供密钥，可按需增补：


| 变量                                         | 说明                                                                                            | 默认值                                         |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `DEEPSEEK_API_KEY`                           | 必填，总结与日报生成                                                                            | 已配置                                         |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`       | 模型地址与名称                                                                                  | `https://api.deepseek.com` / `deepseek-chat`   |
| `SERPAPI_API_KEY`                            | 国际站点检索（Google）                                                                          | 已配置                                         |
| `BOCHA_API_KEY`                              | 中文全网检索 / 回退方案                                                                         | 已配置                                         |
| `DEEPSEEK_SEARCH_ENABLED`                    | 是否启用 DeepSeek Search（`true`/`false`）                                                      | `true`                                         |
| `DEEPSEEK_SEARCH_MODE`                       | 与现有搜索源的协作方式：`off` 不使用 / `fallback` 兜底 / `primary` 优先 / `supplement` 并行合并 | `supplement`                                   |
| `DEEPSEEK_SEARCH_NEED_CONTENT`               | Search 是否同时返回网页正文                                                                     | `false`                                        |
| `DEEPSEEK_SEARCH_AFTER`                      | 是否在 query 中追加`after:` 限定时间窗口                                                        | `true`                                         |
| `DEEPSEEK_FETCH_ENABLED`                     | 是否用 DeepSeek Fetch 抓取原文补充摘要                                                          | `true`                                         |
| `DEEPSEEK_FETCH_LIMIT`                       | 每轮最多抓取正文的条数                                                                          | `12`                                           |
| `DEEPSEEK_FETCH_MIN_SNIPPET`                 | 摘要短于该字符数才抓取正文                                                                      | `200`                                          |
| `PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE` | PostgreSQL 连接                                                                                 | localhost / 5432 / postgres / 空 / iaisw_daily |
| `PG_AUTO_CREATE`                             | 启动时库不存在则自动创建（需 CREATEDB 权限）                                                    | `true`                                         |
| `PG_MAINTENANCE_DB`                          | 用于检查 / 建库的维护库                                                                         | `postgres`                                     |
| `DAILY_CRON`                                 | 定时表达式                                                                                      | `0 8 * * *`（每天 8:00）                       |
| `CRON_TIMEZONE`                              | 时区                                                                                            | `Asia/Shanghai`                                |
| `COLLECT_WINDOW_DAYS`                        | 只保留最近 N 天发布的内容                                                                       | 3                                              |
| `COLLECT_PER_KEYWORD_LIMIT`                  | 每个关键词每个渠道最多取几条                                                                    | 8                                              |
| `RUN_ON_BOOT`                                | 服务启动即执行一次采集                                                                          | false                                          |
| `SEARCH_MOCK`                                | true 时不调用真实搜索，返回演示数据（用于无 Key 联调）                                          | false                                          |

### 前端可配置项（存于 `settings` 表）

- 检索渠道开关
- 中文关键词（公众号 / B站 / 中文资讯）与英文关键词（国际站点）
- Cron 表达式、时区、时间窗口、每关键词条数



## 六、数据库表


| 表         | 用途                                                                                                       |
| ---------- | ---------------------------------------------------------------------------------------------------------- |
| `articles` | 采集到的信息条目：标题、来源、渠道、摘要、DeepSeek 总结、分类、标签、评分、`relevant` 相关性标记、发布时间 |
| `reports`  | 每日日报：综述、重点信息（JSONB）、趋势（JSONB）、渠道统计                                                 |
| `runs`     | 每次采集任务：状态、渠道、关键词、检索数、新增数、错误信息                                                 |
| `settings` | 系统配置（JSONB）                                                                                          |



## 七、REST API


| 方法     | 路径                                                             | 说明                                      |
| -------- | ---------------------------------------------------------------- | ----------------------------------------- |
| GET      | `/api/health`                                                    | 数据库 / 模型 / 搜索源 / 调度状态         |
| GET      | `/api/channels`                                                  | 渠道列表                                  |
| GET/PUT  | `/api/settings`                                                  | 读取 / 保存配置（保存后自动重载定时任务） |
| GET      | `/api/articles?channel=&q=&days=&onlySummarized=&limit=&offset=` | 信息检索                                  |
| GET      | `/api/stats?days=7`                                              | 渠道统计                                  |
| GET      | `/api/reports/latest`、`/api/reports/:date`、`/api/reports`      | 日报                                      |
| GET/POST | `/api/runs`                                                      | 采集记录 / 手动触发采集                   |



## 八、采集流程

1. 读取配置 → 生成「渠道 × 关键词」检索任务（并发 4）
2. 各渠道检索并解析标题、来源、发布时间；按时间窗口过滤
3. 按 URL + 标题归一化去重，写入 `articles`
4. DeepSeek 批量处理新条目：`relevant` 相关性、摘要、分类、标签、评分
5. 过滤无关条目后，DeepSeek 生成日报 → 写入 `reports`
6. 记录 `runs`，前端可查看每次采集的耗时与结果



## 九、常见问题

### 安装与启动

- **`npm run dev` 报 `concurrently: not found`**：根目录的 `npm install` 没执行。`npm run dev` 依赖根目录 devDependency `concurrently` 来并行拉起前后端。
- **命令必须在正确目录执行**：`config.env` 只在**仓库根目录**（`server/config.js` 通过 `../../config.env` 读取）。在 `server/` 里直接改 `config.env` 不会生效；子项目单独启动时用 `cd server && npm install && npm run dev`。
- **自动建库失败（`permission denied to create database`）**：当前 `PGUSER` 缺少 `CREATEDB` 权限。可 `psql -c "ALTER ROLE <user> CREATEDB"`，或手动 `createdb iaisw_daily` 并设 `PG_AUTO_CREATE=false`。
- **忘记执行迁移**：只启动服务不会建表，`/api/health` 的 `db` 为 `true` 但接口会报表不存在，请先 `npm run migrate`。
- **端口被占用**：后端改 `config.env` 的 `PORT`；前端改 `web/vite.config.js` 的 `server.port`（同时保持 `/api` 代理目标与新端口一致）。

### 检索

- **B站返回 412**：已内置 WBI 签名与 Cookie 获取；若仍被限流会自动回退博查检索。
- **微信公众号**：列表页来自搜狗微信搜索；真实 `mp.weixin.qq.com` 地址需再解析一次跳转页，若被搜狗限流（验证码）则保留搜狗跳转链接并在 30 分钟后自动重试；列表检索失败时回退博查检索。
- **微信搜狗触发验证码**：本轮自动停止真实链接解析（保留搜狗跳转链接），并回退博查检索。
- **日报为空**：检查 `COLLECT_WINDOW_DAYS` 是否过小，或关键词是否过窄；可在「配置」页放宽。
- **未配置 DEEPSEEK_API_KEY**：系统会使用规则式摘要与清单式日报，流程仍可跑通。
- **想只用 DeepSeek 检索**：设置 `DEEPSEEK_SEARCH_MODE=primary`（优先 DeepSeek，无结果时再走 SerpAPI / 博查 / B站）；关闭搜索与抓取则设 `DEEPSEEK_SEARCH_ENABLED=false`、`DEEPSEEK_FETCH_ENABLED=false`。
- **Search 返回 429 / 5xx**：已内置退避重试（默认 2 次）；Search 与 Fetch 账号级 QPS 分别为 100 / 25，可下调 `DEEPSEEK_FETCH_CONCURRENCY`。
- **想零成本联调**：设置 `SEARCH_MOCK=true`，各渠道返回演示数据。
