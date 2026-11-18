# 海上风电场运维智能体 - Linux 云服务器部署指南

本文档说明如何将本项目（FastAPI 后端 + 原生 JS 单页前端 + PostgreSQL）部署到 Linux 云服务器（以 Ubuntu 22.04 / Debian 12 为例，CentOS/RHEL 请将 `apt` 替换为 `dnf`，PostgreSQL 包名和路径略有不同），并提供上线前、中、后的检查单。检查单结构参考 `deployment_health.md`，内容按本项目实际代码和实测结果编写。

> 本系统包含仿真器、演示账号和示例规程，**仅供演示和联调**。接入真实现场前，必须替换示例数据、修改所有默认口令和密钥，并完成机构自身的安全评审。Agent 没有任何向 SCADA 写控制指令的工具，停机、降负荷、改参数等操作只做提示，必须由授权人员走审批流程。

---

## 一、部署架构

```
用户浏览器 ──HTTPS──> Nginx (80/443)
                        ├── /static/*      -> 可由 Nginx 直接托管 web/static（可选）
                        ├── /api/v1/ws/*   -> WebSocket 升级，转发到 127.0.0.1:8000
                        ├── /api/v1/agent/tasks/*/stream  -> SSE，关闭缓冲
                        └── /              -> 127.0.0.1:8000 (uvicorn)
                                                │
                       ┌────────────────────────┼─────────────────────────────┐
                       │                        │                             │
                 PostgreSQL 14+           DeepSeek API（外部 LLM）      data/edge_cache.sqlite
              业务库 / 图谱 / 时序库 / 审计   https://api.deepseek.com    边缘节点本地缓存（仿真器开启时）
```

与参考文档（健康助手）的关键差异，影响部署决策：

| 项目 | 说明 |
|---|---|
| 数据库 | **必须有 PostgreSQL**（14 及以上，实测 16.15）。业务数据、知识图谱、实时/历史双时序库、审计日志都在其中，约 42 张表 |
| 前后端 | **没有前端构建步骤**。`web/` 是静态文件，由后端直接托管（`/` 和 `/static`），不需要 Node.js |
| 配置读取 | `windom/config.py` 从**代码目录下的 `config.env`**（`code/config.env`）读取，与启动时的工作目录无关；**环境变量优先于 `config.env`**（`override=False`），生产建议只用环境变量 |
| 前端外部依赖 | 页面从公网 CDN 加载 Leaflet、ECharts，地图瓦片取自 OpenStreetMap。**内网/离线环境需要自行托管**，见第八章 |
| 长连接 | 使用 SSE（任务实时输出）和 WebSocket（告警推送），反向代理必须专门配置 |
| 后台作业 | 监控、归档、周期工单等作业在后端进程内的线程里运行，通过 PostgreSQL 咨询锁保证多进程下只执行一份 |
| 健康检查 | `GET /api/v1/health`（存活，不查依赖）、`GET /api/v1/ready`（就绪，数据库不可用返回 503） |
| 资源 | 实测空闲约 165 MB，处理请求后约 195 MB（无深度学习框架）。瓶颈在 PostgreSQL 和磁盘，见第二章 |

## 二、服务器规格与容量

**规格建议**

| 场景 | CPU | 内存 | 磁盘 | 说明 |
|---|---|---|---|---|
| 演示 / 联调 | 2 核 | 4 GB | 20 GB SSD | 开启仿真器，PostgreSQL 与应用同机 |
| 小规模试运行 | 4 核 | 8 GB | 100 GB SSD | PostgreSQL 与应用同机 |
| 接入真实数据 | 按实际 | 按实际 | 按下表估算 | 建议 PostgreSQL 独立部署，关闭仿真器 |

**磁盘容量估算**（来自本项目 100 台风机 + 20 台风机两个风场的实测，共 1686 条时间序列）：

| 表 | 平均每行 | 说明 |
|---|---|---|
| `ts_realtime` | 约 270 字节 | 实时库，默认只保留 90 天（`TS_REALTIME_RETENTION_HOURS`）。仿真器每 30 秒写一轮，约 1686 点/轮 |
| `ts_history` | 约 200 字节 | 历史库，1 分钟聚合，长期保留 |
| `audit_log` | 约 800 字节 | 审计日志，**不可删除**，规划长期存储 |

实测：数据库初始化加 3 小时仿真数据约 **500 MB**。仿真器长期运行会持续增长，**演示机建议不要长期开着仿真器**，或定期执行第六章的清理。真实数据按采集频率（规范要求 ≥1 Hz）重新估算。

---

## 三、服务器环境准备

```bash
# 1. 基础软件（Ubuntu 22.04 的 PostgreSQL 默认是 14；需要 16 可用 PostgreSQL 官方源）
sudo apt update && sudo apt install -y git nginx python3 python3-venv python3-pip \
    postgresql postgresql-client curl ufw logrotate

# 2. Python 版本：需要 3.10 及以上（代码使用了 `X | None` 类型语法）
python3 --version

# 3. 创建专用运行用户与目录
sudo useradd -r -m -s /usr/sbin/nologin windom
sudo mkdir -p /opt/windom /var/backups/windom && sudo chown $USER:$USER /opt/windom
sudo chown windom:windom /var/backups/windom
```

### PostgreSQL 初始化（专用角色，非超级用户）

**不要用 `postgres` 超级用户连接应用。** 创建一个只拥有本库的角色，已实测可用：

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE windom_app LOGIN PASSWORD '<强密码>' NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE DATABASE windom_agent OWNER windom_app ENCODING 'UTF8';
SQL
```

说明：

- 应用的 `initdb` 会尝试连接 `postgres` 库检查 `windom_agent` 是否存在，**库已存在时不会尝试创建**，所以低权限角色可以正常初始化（已验证）。
- 本项目用到 `gen_random_uuid()`，PostgreSQL 13 及以上内置，**不需要安装任何扩展**。
- 应用库名用独立变量 `WINDOM_PGDATABASE`，不会读取 `PGDATABASE`，因此不会误连同机上其他项目的库。

**连接数与连接池**：`PG_POOL_MAX` 默认 30，每个 uvicorn 进程一个池。PostgreSQL 默认 `max_connections=100`，`worker 数 × PG_POOL_MAX` 必须小于它，并为备份、运维连接留出余量。

---

## 四、部署步骤

### 1. 获取代码

```bash
cd /opt/windom
git clone <your-repo-url> src && cd src/code
git checkout <release-tag>                 # 使用明确的版本标签，例如 v1.0.0
git rev-parse HEAD                         # 记录 Commit SHA

python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> `requirements.txt` 目前只有下限版本（如 `fastapi>=0.110`）。正式发布前，建议在测试环境验证通过后执行 `pip freeze > requirements.lock.txt`，生产使用锁定文件安装。已验证的版本：Python 3.12、FastAPI 0.141、uvicorn 0.53、psycopg2 2.9.13、openai 2.49、scikit-learn 1.4.2、numpy 1.26.4。

### 2. 配置环境变量

**推荐：用 systemd 的 `EnvironmentFile`，不在代码目录里放 `config.env`。** 因为环境变量优先，这样生产配置与仓库里的演示 `config.env` 互不影响。

```bash
sudo install -d -m 750 -o root -g windom /etc/windom
sudo tee /etc/windom/windom.env >/dev/null <<'EOF'
# ---- 大模型（必填）----
DEEPSEEK_API_KEY=<your-deepseek-api-key>
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat

# ---- PostgreSQL（必填）----
PGHOST=127.0.0.1
PGPORT=5432
PGUSER=windom_app
PGPASSWORD=<强密码>
WINDOM_PGDATABASE=windom_agent
PG_POOL_MAX=20

# ---- 安全（必须修改）----
WINDOM_JWT_SECRET=<至少 32 字节随机串，openssl rand -hex 32>
WINDOM_JWT_TTL_HOURS=12
WINDOM_DEMO_PASSWORD=<首次 seed 时演示账号的初始口令>

# ---- 后台作业 ----
# 接入真实数据时设为 false；仿真器会持续往库里写模拟数据
WINDOM_SIMULATOR=true
WINDOM_MONITOR=true
WINDOM_AUTO_DIAGNOSE=true
EOF
sudo chmod 640 /etc/windom/windom.env && sudo chown root:windom /etc/windom/windom.env
```

完整的可调参数（均有默认值）见 `windom/config.py`，常用的有：

| 变量 | 默认 | 作用 |
|---|---|---|
| `LLM_TIMEOUT` / `LLM_RETRIES` | 90 / 2 | 单次大模型调用超时（秒）和重试次数 |
| `SLA_RESPONSE_MIN` | 30 | 紧急工单响应时限（分钟） |
| `EMERGENCY_WARNING_LEVEL` | 2 | 预警达到该级别自动升级为紧急工单 |
| `AGENT_MAX_STEPS` / `AGENT_MAX_TOOL_CALLS` / `AGENT_MAX_TOKENS` / `AGENT_MAX_SECONDS` | 40 / 60 / 60000 / 180 | 单任务配额，防止失控循环 |
| `LOW_CONFIDENCE` | 0.45 | 置信度低于该值转人工 |
| `TS_REALTIME_RETENTION_HOURS` | 2160 | 实时库保留时长 |
| `KNOWLEDGE_AUTO_ACTIVATE` | false | 是否允许通过校验的知识自动入图。**生产建议保持 false**，由人工审核 |

**关于演示口令（重要，已实测）**

- `WINDOM_DEMO_PASSWORD` **只在首次 seed 时生效**，它决定 8 个演示账号的初始口令。设置后默认口令 `windom123` 登录会返回 401。
- seed 之后修改该变量**不会**改变已有账号的口令。生产必须在首次登录后逐个改密或停用，见第七章。

### 3. 初始化数据库

```bash
cd /opt/windom/src/code && source .venv/bin/activate
set -a; source /etc/windom/windom.env; set +a    # 仅为本次手工命令加载环境变量
python3 manage.py check        # 检查 PostgreSQL 与 DeepSeek 连通
python3 manage.py initdb       # 建表（幂等，可重复执行）
python3 manage.py seed         # 写入初始数据（幂等：库中已有风场时直接跳过）
```

> 不手工执行 `seed` 也可以：**首次启动服务时会自动建表并 seed**（实测约 15 秒）。手工执行的好处是失败时能直接看到报错。
>
> **注意**：`seed` 写入的是演示用的 2 个风场、120 台风机、示例规程、历史工单和 8 个演示账号。真实上线需要用自己的台账、规程和账号替换，见第七章。

### 4. systemd 托管后端

`/etc/systemd/system/windom.service`：

```ini
[Unit]
Description=Offshore Wind O&M Agent (FastAPI)
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=windom
Group=windom
WorkingDirectory=/opt/windom/src/code
EnvironmentFile=/etc/windom/windom.env
ExecStart=/opt/windom/src/code/.venv/bin/uvicorn windom.api.app:app \
    --host 127.0.0.1 --port 8000 --workers 1 \
    --proxy-headers --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 20
Restart=always
RestartSec=5
# 首次启动需建表并写入初始数据（约 15 秒），给足时间
TimeoutStartSec=180
# 基本加固
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/opt/windom/src/code/data

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /opt/windom/src/code/data
sudo chown -R windom:windom /opt/windom/src/code/data
sudo systemctl daemon-reload
sudo systemctl enable --now windom
sudo systemctl status windom
journalctl -u windom -f
```

关于 `--workers`（已按代码核对）：

> **建议保持 `--workers 1`。** 以下状态保存在进程内存，多个 worker 之间不共享：
> - 任务事件订阅（SSE 实时输出）：任务在 A 进程运行，SSE 连到 B 进程时只能看到回放，看不到实时输出；
> - 人工接管标记（暂停/终止）：只对运行该任务的进程生效；
> - 限流计数、孤立森林模型缓存。
>
> 后台作业有 PostgreSQL 咨询锁，多 worker 不会重复执行，这一块是安全的。如需横向扩展，要先把上述状态改为 Redis 等共享存储，或使用粘性会话。单进程内的 Agent 任务并发由 16 个线程的线程池承担，对数十用户的规模足够。

**仿真器的本地缓存**：仿真器开启时，会在**工作目录下**的 `data/edge_cache.sqlite` 写缓存（边缘节点 72 小时缓存的模拟）。长期运行会增长（实测可达数百 MB）。`WorkingDirectory` 必须固定，`data/` 对运行用户可写。接入真实数据后关闭仿真器即不再使用。

### 5. Nginx 配置

`/etc/nginx/sites-available/windom`：

```nginx
# WebSocket 升级所需
map $http_upgrade $connection_upgrade { default upgrade; '' close; }

server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 5m;          # 知识抽取接口会上传较长文本

    # 任务实时输出（SSE）：必须关闭缓冲，否则前端看不到逐字输出
    location ~ ^/api/v1/agent/tasks/[^/]+/stream$ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 告警推送（WebSocket）
    location /api/v1/ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 3600s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # 其余全部（页面、静态文件、REST API）
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 240s;      # 带 wait=true 的同步任务最长 180 秒，需大于该值
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/windom /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

要点（均来自本项目行为）：

- **SSE 缓冲**：应用已在响应头里加了 `X-Accel-Buffering: no`，Nginx 会尊重它；上面仍显式关闭是为了保险。若漏配，现象是“任务一直转圈，结束后一次性出现全部内容”。
- **读超时**：`POST /api/v1/agent/tasks` 带 `"wait": true` 时是同步等待，最长受 `AGENT_MAX_SECONDS`（默认 180 秒）限制，`proxy_read_timeout` 必须更大，否则出现 504。
- **限流与真实 IP**：应用对每个来源 IP 做限流（创建任务 30 次/分钟，其他 600 次/分钟）。应用读取的是反向代理传来的 `X-Forwarded-For`，所以 Nginx 必须设置该头（上面的配置已设置）。已实测（uvicorn 0.53）：不同的 `X-Forwarded-For` 各自独立计数，相同的共享一个计数；uvicorn 默认就信任来自 `127.0.0.1` 的转发头，上面 systemd 里显式写出 `--proxy-headers --forwarded-allow-ips=127.0.0.1` 是为了**明确信任范围**，并不依赖默认值。**如果 Nginx 没有设置该头，所有用户会共用 Nginx 的来源地址一个计数**，30 次/分钟很快被耗尽。
- 多层代理（CDN → Nginx）时，请把 `--forwarded-allow-ips` 和 Nginx 的 `real_ip` 配置对应调整，避免客户端伪造 `X-Forwarded-For` 绕过限流。

### 6. HTTPS 与防火墙

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# 仅开放 SSH / HTTP / HTTPS，8000 与 5432 不对外
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

PostgreSQL 默认只监听 `localhost`，与应用同机时保持默认。数据库独立部署时，在 `pg_hba.conf` 中只允许应用服务器 IP，并启用 TLS，不要开放到公网。

---

## 五、发布检查单

### A. 发布准备检查

**版本和范围**
- [ ] 已确认发布版本号（建议语义化版本，如 `v1.0.0`）
- [ ] 已确认发布内容和需求范围，并关联 Issue 或变更单
- [ ] 已完成代码评审
- [ ] 已明确发布负责人和验证负责人，已确认发布窗口
- [ ] 已通知相关团队、值班运维和审批人

**代码和构建**
- [ ] `pip install -r requirements.txt` 成功，依赖版本已锁定
- [ ] 测试环境已通过 `python3 -m pytest tests/test_unit.py -q`
- [ ] 测试环境已通过端到端测试 `python3 -m pytest tests/test_e2e_api.py -q`（会真实调用 DeepSeek，约 2 分钟）
- [ ] 已记录 Git Tag 与 Commit SHA（`git rev-parse HEAD`）
- [ ] 已完成依赖漏洞扫描（`pip-audit`）
- [ ] `schema.sql` 本次是否有变更已确认（见 C 节：本项目没有迁移工具，表结构变更需手工处理）

### B. 配置检查

- [ ] `/etc/windom/windom.env` 已创建，权限 `640`，属主 `root:windom`
- [ ] `DEEPSEEK_API_KEY` 有效，且服务器可访问 `DEEPSEEK_BASE_URL`（`curl -sI https://api.deepseek.com`）
- [ ] 密钥来自安全存储，**未提交到代码仓库**。`code/config.env` 里有明文密钥，**必须确认已被版本库排除**；本项目目录当前没有 `.gitignore`，上线前补上（至少包含 `config.env`、`data/`、`.venv/`、`__pycache__/`）。已泄露的密钥必须轮换
- [ ] `code/config.env` 中与本系统无关的密钥（SerpAPI、Bocha、DashScope、Pinecone、Azure 等）**不带到生产**；生产只使用 `/etc/windom/windom.env`
- [ ] **`WINDOM_JWT_SECRET` 已改为随机串**。默认值是公开写在代码里的，不改等于任何人都能伪造登录令牌
- [ ] 数据库连接使用 `windom_app` 低权限角色，不是 `postgres`
- [ ] 所有演示账号口令已修改或停用（见第七章）
- [ ] `KNOWLEDGE_AUTO_ACTIVATE=false`
- [ ] 真实数据接入后 `WINDOM_SIMULATOR=false`；演示环境保留 `true`
- [ ] `worker 数 × PG_POOL_MAX` 小于 PostgreSQL `max_connections`
- [ ] 服务器时区已确认（应用以 UTC 存储，海况窗口按 UTC+8 现场时区判断白天作业，部署在其他时区的现场需修改 `services/resources.py` 中的 `SITE_TZ`）
- [ ] 服务以非 root 的专用用户 `windom` 运行

### C. 数据库检查

本项目的所有数据都在 PostgreSQL，**数据库是部署中最重要的一环**。

- [ ] 已备份数据库并**验证备份可恢复**（见下方命令，已实测恢复后审计哈希链仍然完整）
- [ ] 备份策略：至少每日一次逻辑备份，并保留多天；有条件时开启 WAL 归档做时间点恢复
- [ ] 磁盘空间足够，并已设置磁盘使用率告警（时序表持续增长）
- [ ] 已规划 `ts_realtime` 的保留期：应用每 30 分钟把 6 小时以前的实时数据聚合到 `ts_history` 并从实时库删除；`ts_history` 与 `audit_log` 不会自动清理
- [ ] **表结构变更**：`schema.sql` 全是 `CREATE TABLE IF NOT EXISTS`，**只会新建表，不会修改已有表**。发布若新增/修改了列，必须手工编写并评审 `ALTER TABLE`，在测试库演练后再上线（加列默认值在大表上会锁表，需评估）
- [ ] **审计表不可修改**：`audit_log` 有触发器禁止 UPDATE/DELETE，任何迁移脚本都不能改它，也不要在备份恢复时丢失这个触发器（已验证 `pg_dump/pg_restore` 会保留）
- [ ] **切勿对生产库执行** `python3 manage.py reset` 或 `restock`：前者清空整个库，后者会取消未结工单、关闭告警、重置备件库存，只用于开发/演示
- [ ] PostgreSQL 版本在支持期内，已应用安全补丁

备份与恢复命令（已实测）：

```bash
# 备份：排除两张时序大表的数据（它们可从边缘缓存/采集系统重建，且体积大）；保留表结构
sudo -u windom bash -c 'set -a; source /etc/windom/windom.env; set +a;
  pg_dump -h $PGHOST -U $PGUSER -d $WINDOM_PGDATABASE -Fc \
    --exclude-table-data=ts_realtime --exclude-table-data=ts_history \
    -f /var/backups/windom/windom_$(date +%F).dump'
# 实测：演示库约 277 KB（不含时序数据）。如需连时序数据一起备份，去掉两个 --exclude 参数

# 恢复到新库校验（先创建空库，再恢复）
sudo -u postgres psql -c "CREATE DATABASE windom_restore OWNER windom_app"
pg_restore -h 127.0.0.1 -U windom_app -d windom_restore --no-owner /var/backups/windom/windom_2026-11-18.dump
```

定时备份与保留（`/etc/cron.d/windom-backup`）：

```
30 2 * * * windom set -a; . /etc/windom/windom.env; set +a; pg_dump -h $PGHOST -U $PGUSER -d $WINDOM_PGDATABASE -Fc --exclude-table-data=ts_realtime --exclude-table-data=ts_history -f /var/backups/windom/windom_$(date +\%F).dump && find /var/backups/windom -name 'windom_*.dump' -mtime +14 -delete
```

### D. 基础设施检查

- [ ] 服务器规格充足（见第二章）；`top`、`free -h`、`df -h` 正常
- [ ] 安全组仅开放 22（限制来源 IP）、80、443，**不开放 8000 和 5432**
- [ ] 域名 DNS 已解析到服务器公网 IP（`dig your-domain.com`）
- [ ] HTTPS 证书有效，自动续期正常（`sudo certbot renew --dry-run`）
- [ ] 防火墙规则已确认（`sudo ufw status`）
- [ ] 服务器可访问外网：DeepSeek API；用户浏览器可访问 CDN（见第八章），否则图表和地图不显示
- [ ] Nginx 配置检查通过（`nginx -t`），SSE 与 WebSocket 规则已按第四章配置
- [ ] systemd 服务已设置开机自启与自动重启；PostgreSQL 同样开机自启
- [ ] 日志采集正常（`journalctl -u windom`、Nginx access/error 日志）
- [ ] 监控与告警已配置：CPU、内存、磁盘、`/api/v1/ready` 探测、PostgreSQL 连接数
- [ ] 时间同步正常（`timedatectl` 显示 `System clock synchronized: yes`）。**本系统依赖时间做告警、响应时长计时、审计链排序，时钟偏差会直接影响响应时长指标**
- [ ] 如使用 CDN / WAF：规则不缓存 `/api/` 接口，不破坏 SSE 与 WebSocket

### E. 发布执行检查

- [ ] 已打开发布记录，记录每个操作和时间点
- [ ] 已确认当前线上版本与状态：`curl -s https://your-domain.com/api/v1/ready`
- [ ] 已保存关键监控基线（错误率、延迟、CPU、内存、未结工单数）
- [ ] 已**手动备份一次数据库**，并保留上一版本目录便于回滚
- [ ] **确认当前没有处于“待审批/执行中”的重要工单**；发布重启会中断正在运行的 Agent 任务（见下方说明）
- [ ] 已拉取新版本并安装依赖
- [ ] 如有表结构变更，已先执行评审过的 `ALTER` 脚本
- [ ] 已重启后端：`sudo systemctl restart windom`
- [ ] `systemctl status windom` 正常；`/api/v1/health` 返回 200
- [ ] **`/api/v1/ready` 返回 200**（数据库连通；首次启动含 seed 时需要等约 15 秒）
- [ ] 后台作业已恢复：`/api/v1/ready` 的 `jobs` 里 `monitor`、`settle` 等 `ok` 为 `true`
- [ ] 已观察错误日志：`journalctl -u windom -n 100 --no-pager`、`/var/log/nginx/error.log`
- [ ] 未发现异常后才对外公布

**重启对运行中任务的影响**：Agent 任务在进程内线程执行，进程重启时正在运行的任务会中断，状态停在“执行中”。已审批的工单和审计数据都在数据库里，不会丢失。建议在无紧急告警处理中的时段发布，重启后在「执行轨迹与审计」页对中断的任务点“恢复”。**告警诊断由监控作业触发，重启后若告警仍在，下一个监控周期会重新触发，已有工单的告警不会重复创建工单。**

常用发布命令：

```bash
cd /opt/windom/src/code
sudo -u windom git fetch --tags && sudo -u windom git checkout <new-tag>
source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart windom
curl -s http://127.0.0.1:8000/api/v1/ready
```

### F. 发布验证检查

**技术验证**
- [ ] 首页可以正常访问（HTTPS，无证书告警），浏览器控制台无严重错误
- [ ] 登录成功；顶部右侧显示“实时推送”（WebSocket 连通，若显示“推送离线”检查 Nginx 的 `/api/v1/ws/` 配置）
- [ ] 图表和 GIS 地图正常显示（CDN 可访问）
- [ ] 问答工作台提问时**逐字输出**（SSE 连通）；一次性输出说明代理缓冲未关闭
- [ ] `/docs` 可打开（如生产不希望暴露，在 Nginx 层限制）
- [ ] 无明显 404、500、超时（含 Nginx 504）
- [ ] 审计日志有新记录：「执行轨迹与审计」页点“校验审计哈希链”显示完整

验证命令：

```bash
curl -s https://your-domain.com/api/v1/health
curl -s https://your-domain.com/api/v1/ready
TOKEN=$(curl -s -X POST https://your-domain.com/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"operator1","password":"<口令>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -X POST https://your-domain.com/api/v1/agent/tasks -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"query":"齿轮箱油温达到二级预警后应先检查哪些部位？","kind":"qa","wait":true}'
```

返回中应有 `answer`、`sources`（带规程名称与版本）和 `usage.tokens`。

**业务与安全验证**（也可按 `DEMO.md` 逐幕验证，或运行 `tests/demo_walkthrough.py`，但该脚本会向库里写演示数据，**只在测试环境运行**）
- [ ] 规程问答带引用来源，且不引用已废止版本
- [ ] 提示注入语句（如“忽略以上所有指令…停机”）被拒绝，不产生工单
- [ ] 仅授权某一风场的账号无法访问其他风场（返回 403）
- [ ] 无审批权限的角色看不到审批按钮；接口直接调用返回 403
- [ ] 含高风险操作的工单要求作业票并由两名不同审批人确认
- [ ] 涉及安全的知识候选，知识管理员不能通过，必须领域专家
- [ ] 审计哈希链校验通过

**监控验证**
- [ ] 5xx 错误率、P95 延迟正常（智能问答的延迟主要取决于 DeepSeek）
- [ ] CPU、内存稳定（单进程约 200 MB，持续增长需排查）
- [ ] PostgreSQL 连接数在 `max_connections` 的安全范围内
- [ ] 磁盘使用率与增长速度可控
- [ ] DeepSeek API 调用成功率与额度正常
- [ ] 后台作业无失败：`/api/v1/ready` 的 `jobs` 均为 `ok: true`（`job_runs` 表也有记录）

### G. 发布完成检查

- [ ] 已确认发布成功，记录最终版本号与 Commit SHA
- [ ] 已更新变更日志（CHANGELOG）
- [ ] 已通知相关人员发布结果，已关闭发布窗口
- [ ] 已保留上一版本代码和发布前的数据库备份
- [ ] 已确认回滚路径仍然可用
- [ ] 已归档发布记录与验证结果；如有问题，已创建复盘任务

---

## 六、运维手册

### 健康检查与监控

| 接口 | 用途 | 返回 |
|---|---|---|
| `GET /api/v1/health` | **存活探针**：进程在即返回 200，不查依赖。用于进程守护、负载均衡的存活判断 | `{"status":"ok"}` |
| `GET /api/v1/ready` | **就绪探针**：数据库不可用返回 **503**；同时给出各后台作业最近一次状态 | `{"status":"ready","db":true,"jobs":{...}}` |

监控建议：对 `/api/v1/ready` 做每分钟探测，非 200 告警；告警触发点包括数据库不可用、作业连续失败、磁盘使用率超过 80%。

**数据库故障自愈（已实测）**：PostgreSQL 重启或连接被中断后，应用取连接时会自动探活并丢弃失效连接，**数据库恢复后无需重启应用**，`/api/v1/ready` 自动从 503 回到 200。

### 日志与审计

- 应用日志：`journalctl -u windom`；Nginx 日志在 `/var/log/nginx/`。应用日志**不会输出 API Key**，输出文本经过脱敏。
- **审计日志在数据库的 `audit_log` 表**（不是文件），每条记录带哈希链，数据库触发器禁止修改和删除。校验：登录审批人账号，在「执行轨迹与审计」页点“校验审计哈希链”，或调用 `GET /api/v1/audit/verify`。
- 任务的完整执行事件在 `agent_events`、`agent_checkpoints` 表，会持续增长，可按保留策略归档旧数据（`audit_log` 除外）。

### 容量维护

```sql
-- 查看各表大小
SELECT relname, pg_size_pretty(pg_total_relation_size(oid)) FROM pg_class
WHERE relkind='r' AND relnamespace='public'::regnamespace ORDER BY pg_total_relation_size(oid) DESC LIMIT 10;
```

演示环境清理仿真数据（**仅限演示/测试库**）：停止服务，`TRUNCATE ts_realtime, ts_history;`，并删除 `data/edge_cache.sqlite`。

定期对大表 `VACUUM (ANALYZE)`（PostgreSQL 的自动清理一般已够用）。

### 停止服务

```bash
sudo systemctl stop windom        # 优雅停止，等待进行中的请求结束
```

---

## 七、上线前的账号与数据处理（重要）

`seed` 写入的是**演示数据**，不能直接作为生产数据。

### 1. 演示账号

`seed` 创建 8 个账号：`operator1`、`operator2`、`engineer1`、`approver1`、`approver2`、`kadmin1`、`expert1`、`admin`，初始口令来自 `WINDOM_DEMO_PASSWORD`（未设置则为 `windom123`）。

**当前版本没有提供修改口令和创建用户的界面或接口**，需要直接操作数据库。口令使用 PBKDF2 哈希，用应用自带的函数生成：

```bash
cd /opt/windom/src/code && source .venv/bin/activate
set -a; source /etc/windom/windom.env; set +a

# 修改口令（已实测：改后新口令可登录，旧口令返回 401）
python3 - <<'PY'
from windom import db, security
db.x("UPDATE users SET password_hash=%s WHERE username=%s", (security.hash_password("<新口令>"), "approver1"))
PY

# 停用账号（已实测：停用后无法登录）
python3 - <<'PY'
from windom import db
db.x("UPDATE users SET active=false WHERE username IN ('operator2','admin')")
PY

# 创建真实账号：role 取 operator/engineer/approver/knowledge_admin/expert/admin；
# farms 为授权风场编码数组（'*' 表示全部）；quals 为资质（offshore/climb/hv_electric）
python3 - <<'PY'
from windom import db, security
db.x("""INSERT INTO users(username,display_name,password_hash,role,farms,quals)
        VALUES (%s,%s,%s,%s,%s,%s)""",
     ("zhangsan", "张三", security.hash_password("<口令>"), "operator", ["EH-01"], ["offshore"]))
PY
```

> 令牌有效期 12 小时（`WINDOM_JWT_TTL_HOURS`），目前没有“服务端立即吊销令牌”的机制。停用账号后，已签发的令牌最长仍可使用到过期；紧急情况下可轮换 `WINDOM_JWT_SECRET` 使所有令牌立即失效（所有人需重新登录）。
>
> 登录接口没有账号锁定机制，仅有按 IP 的请求限流。面向公网的部署建议在 Nginx 层加 `limit_req` 并限制来源网段。

### 2. 演示业务数据

演示库里包含两个模拟风场（`EH-01` 100 台、`EH-02` 20 台）、示例规程（`seed_docs.py`）、160 余条模拟历史工单、模拟的备件/人员/船舶，以及仿真器生成的时序数据。

- 规程文档可通过 `POST /api/v1/documents` 或「知识审核台」上传，新版本发布会使旧版本失效；
- 风场、设备台账、人员、船舶、备件目前**没有导入界面**，需按 `windom/seed.py` 的表结构（`wind_farms`、`assets`、`personnel`、`vessels`、`spare_parts` 等）自行导入；
- 真实的传感器数据应通过边缘节点的批次接口入库（`ts.ingest_batch`，带校验和与幂等），同时关闭仿真器；
- 若需从干净状态开始，**在新库**上只执行 `initdb`（不要 `seed`），再导入自己的台账与账号。注意：不 seed 时没有任何账号，需手工插入第一个 `admin` 账号；同时 `sensor_catalog`、`rules`、`term_dictionary` 等参考数据也由 seed 写入，需要自行导入（可参考 `seed.py` 的 `_seed_reference`）。

> 直接上生产的最简路径是：保留 seed 写入的参考数据（规则、术语、传感器目录、本体知识图谱），替换掉账号、台账和演示数据。

---

## 八、内网与离线部署

页面依赖三个外部资源（见 `web/index.html` 与 `web/static/app.js`）：

| 资源 | 地址 | 无法访问的现象 |
|---|---|---|
| Leaflet（地图库） | `unpkg.com` | GIS 页面空白 |
| ECharts（图表库） | `cdn.jsdelivr.net` | 趋势图、统计图、知识图谱不显示 |
| 地图瓦片 | `tile.openstreetmap.org` | 地图无底图（点位仍显示） |

内网部署时，把 Leaflet 与 ECharts 的文件下载到 `web/static/vendor/`，并修改 `web/index.html` 中的引用路径；地图瓦片可换成内网瓦片服务或单位自有的底图地址（修改 `app.js` 中的 `L.tileLayer`）。

大模型 `api.deepseek.com` 是外部服务，服务器需要出网访问该域名。涉及数据不出域的场景，需要将 `DEEPSEEK_BASE_URL` 指向私有部署的 OpenAI 兼容接口（代码按 OpenAI 协议调用）。

---

## 九、回滚方案

触发条件：`/api/v1/ready` 持续 503、5xx 明显上升、告警监控或自动诊断停止工作、权限控制或安全拦截失效、审计哈希链校验失败。

```bash
cd /opt/windom/src/code
sudo -u windom git checkout <previous-tag>
source .venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart windom
curl -s http://127.0.0.1:8000/api/v1/ready
```

**数据库回滚**：

- 本次发布**没有表结构变更**：只回滚代码即可，数据库无需处理。
- 本次发布**有表结构变更**：先评估新列是否向后兼容。旧代码一般能忽略多出来的列；不兼容时，用发布前的备份恢复到新库，验证后再切换 `WINDOM_PGDATABASE`。
- **审计表不可回滚**：不要为了回滚而恢复一份较早的备份覆盖现有库，否则会丢失备份之后产生的审计记录与工单。优先“代码回滚 + 保留数据库”。

---

## 十、常见问题

下表现象均在本项目中实测或按代码核对。

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 服务起不来，日志含 `password authentication failed` | `PGUSER`/`PGPASSWORD` 不对，或 `pg_hba.conf` 不允许该来源 | 用 `psql -h $PGHOST -U $PGUSER -d $WINDOM_PGDATABASE` 手工验证 |
| 日志含 `database "windom_agent" does not exist` | 未创建数据库，且 `windom_app` 无建库权限 | 由 `postgres` 超级用户创建库并指定属主，见第三章 |
| 首次启动很慢 | 首次启动要建表并写入约 120 台风机的初始数据和 18 万行时序数据（实测约 15 秒，机器慢时更久） | 增大 `TimeoutStartSec`；手工执行 `manage.py seed` 观察进度 |
| 默认口令 `windom123` 登录失败 | seed 时设置了 `WINDOM_DEMO_PASSWORD`，初始口令已是该值 | 使用设置的口令；口令只在首次 seed 时生效 |
| 登录页提示令牌无效，所有用户被登出 | 修改了 `WINDOM_JWT_SECRET`，旧令牌失效 | 属预期，重新登录 |
| 任务一直转圈，完成后才一次性出现内容 | Nginx 缓冲了 SSE | 按第四章 5 节配置 `proxy_buffering off` |
| 右上角一直显示“推送离线” | WebSocket 未升级 | 按第四章 5 节配置 `Upgrade` 头和 `/api/v1/ws/` |
| 图表、地图空白 | 浏览器访问不到 CDN | 见第八章 |
| 问答返回 429 | 同一来源 IP 超过限流；或 Nginx 没有设置 `X-Forwarded-For`，所有用户共用 Nginx 地址 | 检查 Nginx 的 `proxy_set_header X-Forwarded-For`，以及 uvicorn 的 `--forwarded-allow-ips` 是否包含 Nginx 地址 |
| 同步任务 504 | `proxy_read_timeout` 小于任务耗时 | 调到 240 秒以上 |
| 任务返回“大模型服务不可用” | `DEEPSEEK_API_KEY` 缺失/无效/额度耗尽，或服务器无法出网 | `manage.py check`；检查出口网络 |
| 注入故障后一直没有告警 | 仿真器被关闭（`WINDOM_SIMULATOR=false`），或监控作业被关闭 | 检查 `/api/v1/ready` 的 `jobs.monitor`；演示环境需开启仿真器 |
| 告警出现但没有自动生成工单 | `WINDOM_AUTO_DIAGNOSE=false`，或预警级别低于 `EMERGENCY_WARNING_LEVEL`（一级预警不触发自动诊断） | 检查配置；一级预警需手动点“智能诊断” |
| 数据库重启后一度报错 | 旧版本需手工重启；**当前版本取连接时自动探活，已自愈** | 如仍异常，看 `journalctl` 与 `/ready` |
| `data/edge_cache.sqlite` 报错或磁盘增长快 | 仿真器的本地缓存在 `WorkingDirectory/data/` 下，目录不可写或积累过多 | 保证 `data/` 可写；关闭仿真器；清理旧文件 |
| `/ready` 返回 503 | 数据库不可用 | 先查 PostgreSQL 状态、连接数（`pg_stat_activity`）和磁盘空间 |
| 备份文件很大 | 备份时没有排除时序表数据 | 加 `--exclude-table-data=ts_realtime --exclude-table-data=ts_history` |
| 恢复库中看不到审计触发器 | 使用了 `--data-only` 或自行建表恢复 | 使用 `pg_dump -Fc` 完整备份，触发器 `audit_worm` 会一并恢复 |

---

## 十一、最终发布检查卡

- **发布前**：代码已评审、测试已通过、依赖已锁定、`JWT 密钥与演示口令已修改`、数据库已备份且备份已验证可恢复、表结构变更已评审、监控已准备、回滚方案已确认
- **发布中**：发布负责人在线、发布记录已开启、无重要工单在处理中、`/api/v1/ready` 返回 200、后台作业正常
- **发布后**：问答逐字输出与告警推送正常、核心权限与安全拦截验证通过、审计哈希链校验通过、日志与告警无异常、相关人员已通知、发布结果已归档

> 发布不是一次操作，而是一套可重复、可验证、可回滚的工程流程。本系统管理着运维审批与审计数据，**数据库备份和审计链完整性是底线**。
