# 健康智能助手 - Linux 云服务器部署指南

本文档说明如何将本项目（FastAPI 后端 + React/Vite 前端）部署到 Linux 云服务器（以 Ubuntu 22.04 / Debian 为例，CentOS 请将 `apt` 替换为 `yum/dnf`），并提供上线前、中、后的检查单。检查单结构参考 [part5deploy.md](https://github.com/bettermorn/IntelligentSWEPractice/blob/main/courseware/pages/part5deploy.md)。

> 仅供教育演示使用，非医疗设备。生产使用前必须完成机构自身的 DPO/IRB/合规审查，并替换 `app/data/` 中的示例指南。

---

## 一、部署架构

```
用户浏览器 ──HTTPS──> Nginx (80/443)
                        ├── /        -> frontend/dist（静态文件）
                        └── /api/*   -> 127.0.0.1:8000 (uvicorn, 去掉 /api 前缀)
                                              │
                                              ├── DeepSeek API（外部 LLM）
                                              ├── HuggingFace 嵌入模型（首次启动下载并缓存）
                                              └── app/data/*.txt -> 启动时构建内存 FAISS 索引
                                                  app/logs/audit.jsonl（审计日志）
```

项目特点（影响部署决策）：

| 项目 | 说明 |
|---|---|
| 数据库 | 无传统关系型数据库。向量索引由 `app/rag.py` 在启动时从 `app/data/*.txt` 构建到内存；审计日志写入 `app/logs/audit.jsonl` |
| 配置 | `app/config.py` 通过 `load_dotenv("config.env")` 读取**相对当前工作目录**的 `config.env`，因此必须在项目根目录启动服务 |
| 前端请求 | `frontend/src/api.js` 默认请求 `/api`，开发环境由 Vite 代理，生产环境由 Nginx 反向代理并去掉 `/api` 前缀 |
| 健康检查 | 后端提供 `GET /healthz`，暂无 `/ready` 接口 |
| 资源 | `sentence-transformers` 依赖 PyTorch，建议 2 核 4GB 内存及以上，磁盘 10GB 以上 |

---

## 二、服务器环境准备

```bash
# 1. 基础软件
sudo apt update && sudo apt install -y git nginx python3 python3-venv python3-pip curl ufw

# 2. Node.js（仅构建前端使用，也可在本地/CI 构建后上传 dist）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 3. 创建专用运行用户与目录
sudo useradd -r -m -s /usr/sbin/nologin healthassistant
sudo mkdir -p /opt/healthassistant && sudo chown $USER:$USER /opt/healthassistant
```

## 三、部署步骤

### 1. 获取代码与构建

```bash
cd /opt/healthassistant
git clone <your-repo-url> app_src && cd app_src
git checkout <release-tag>           # 使用明确的版本标签，例如 v1.0.0

# 后端
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 前端
cd frontend && npm ci && npm run build && cd ..   # 产物位于 frontend/dist
```

### 2. 配置环境变量

在项目根目录创建 `config.env`（**不要提交到 Git**，权限设为 600）：

```bash
cat > config.env <<'EOF'
DEEPSEEK_API_KEY=<your-deepseek-api-key>
DEEPSEEK_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-chat
EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
# 海外服务器可改为 https://huggingface.co，国内默认使用 hf-mirror.com
# HF_ENDPOINT=https://huggingface.co
EOF
chmod 600 config.env
sudo chown -R healthassistant:healthassistant /opt/healthassistant/app_src
```

### 3. systemd 托管后端

`/etc/systemd/system/healthassistant.service`：

```ini
[Unit]
Description=Health Assistant FastAPI Service
After=network.target

[Service]
User=healthassistant
Group=healthassistant
WorkingDirectory=/opt/healthassistant/app_src
ExecStart=/opt/healthassistant/app_src/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5
# 首次启动需下载嵌入模型，给予足够启动时间
TimeoutStartSec=300
Environment=HF_HOME=/opt/healthassistant/hf_cache

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now healthassistant
sudo systemctl status healthassistant
journalctl -u healthassistant -f
```

> `--workers 1`：每个 worker 都会在内存中各建一份 FAISS 索引并加载模型，小内存机器不要增加 worker 数。

### 4. Nginx 配置

`/etc/nginx/sites-available/healthassistant`：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    root /opt/healthassistant/app_src/frontend/dist;
    index index.html;

    # 前端 SPA 路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 后端 API：去掉 /api 前缀后转发
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;   # LLM 响应可能较慢
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/healthassistant /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 5. HTTPS 与防火墙

```bash
# Let's Encrypt 证书
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# 防火墙：仅开放 SSH / HTTP / HTTPS，8000 端口不对外暴露
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw enable
```

> 前端与 API 通过 Nginx 同域访问，不触发跨域。如需跨域访问，须修改 `app/main.py` 中 `CORSMiddleware` 的 `allow_origins`（当前仅允许 `localhost:5173`）为生产域名。

---

## 四、发布检查单

### A. 发布准备检查

**版本和范围**
- [ ] 已确认发布版本号（建议语义化版本，如 `v1.0.0`）
- [ ] 已确认发布内容和需求范围
- [ ] 已关联 Issue、需求或变更单
- [ ] 已完成代码评审
- [ ] 已明确发布负责人和验证负责人
- [ ] 已确认发布窗口
- [ ] 已通知相关团队和客服

**代码和构建**
- [ ] 已通过静态检查与测试
- [ ] 后端 `pip install -r requirements.txt` 成功，依赖已锁定版本
- [ ] 前端 `npm ci && npm run build` 成功，`frontend/dist` 已生成
- [ ] 已记录 Git Tag 与 Commit SHA（`git rev-parse HEAD`）
- [ ] 已完成依赖漏洞扫描（`pip-audit`、`npm audit`）
- [ ] `app/data/` 中为已审核、已授权的医疗指南，而非示例数据
- [ ] 已完成合规审查（DPO/IRB）

### B. 配置检查

- [ ] `config.env` 已在服务器上创建，权限为 `600`
- [ ] `DEEPSEEK_API_KEY` 有效，且可从服务器访问 `DEEPSEEK_BASE_URL`
- [ ] `HF_ENDPOINT` 与服务器网络匹配（国内镜像 / 官方源），嵌入模型可下载或已离线缓存
- [ ] 密钥来自安全存储，未提交到代码仓库（**检查 `config.env` 是否被 `.gitignore` 排除，已泄露的密钥必须轮换**）
- [ ] 本地开发用的多余密钥（SerpAPI、Bocha、Pinecone、Azure 等）未带到生产环境，仅保留实际使用的
- [ ] CORS：`app/main.py` 的 `allow_origins` 已收紧为生产域名，或使用 Nginx 同域代理
- [ ] 前端 API 地址正确（默认 `/api`，或构建时设置 `VITE_API_BASE`）
- [ ] 未在日志中输出敏感信息（API Key、原始 PHI）
- [ ] 服务器时区与时间格式已确认（建议 UTC 或 Asia/Shanghai，统一即可）
- [ ] 服务以非 root 的专用用户运行

### C. 数据库（数据与索引）检查

本项目无关系型数据库，以下针对知识库数据、向量索引和审计日志：

- [ ] 已备份 `app/data/` 知识库文件与 `app/logs/audit.jsonl`
- [ ] 已验证备份可恢复
- [ ] 知识库文件为 UTF-8 编码 `.txt`，修改后已在测试环境验证索引构建正常
- [ ] 已评估索引构建时间（启动时构建，文档越大启动越慢）并设置合理的 `TimeoutStartSec`
- [ ] 新旧版本数据格式兼容（审计日志字段变更不破坏历史分析）
- [ ] `app/logs/` 目录对运行用户可写，磁盘空间足够
- [ ] 已配置审计日志轮转（`logrotate`）与保留期，满足合规要求
- [ ] 已确认数据回滚方案（恢复上一版本 `app/data/`）
- [ ] 若后续引入外部数据库（如 PostgreSQL、向量库）：已完成迁移脚本评审、测试环境演练、锁表影响评估与人工审批

`/etc/logrotate.d/healthassistant` 示例：

```
/opt/healthassistant/app_src/app/logs/audit.jsonl {
    weekly
    rotate 52
    compress
    missingok
    notifempty
    copytruncate
}
```

### D. 基础设施检查

- [ ] 服务器规格充足（建议 ≥2 核 4GB，磁盘 ≥10GB）
- [ ] CPU、内存、磁盘使用率正常（`top`、`free -h`、`df -h`）
- [ ] 安全组仅开放 22（限制来源 IP）、80、443，不开放 8000
- [ ] 域名 DNS 已解析到服务器公网 IP（`dig your-domain.com`）
- [ ] HTTPS 证书有效且自动续期正常（`sudo certbot renew --dry-run`）
- [ ] 防火墙规则已确认（`sudo ufw status`）
- [ ] 服务器可访问外网：DeepSeek API、HuggingFace（或镜像）
- [ ] Nginx 配置检查通过（`nginx -t`）
- [ ] systemd 服务已设置开机自启与自动重启
- [ ] 备份策略正常（云盘快照或定时备份）
- [ ] 日志采集正常（`journalctl`、Nginx access/error 日志）
- [ ] 监控与告警正常（云监控：CPU、内存、磁盘、带宽、端口探测）
- [ ] 时间同步正常（`timedatectl` 显示 `System clock synchronized: yes`）
- [ ] 如使用 CDN / WAF，规则已确认且不会缓存 `/api/` 接口

### E. 发布执行检查

- [ ] 已打开发布记录，记录每个操作和时间点
- [ ] 已确认当前线上版本与健康状态（`curl https://your-domain.com/api/healthz`）
- [ ] 已保存关键监控基线（错误率、延迟、CPU、内存）
- [ ] 已保留上一版本目录或制品，便于回滚
- [ ] 已拉取新版本代码并完成构建（见第三章）
- [ ] 已重启后端：`sudo systemctl restart healthassistant`
- [ ] 已检查进程状态：`systemctl status healthassistant`
- [ ] 已检查 `/healthz` 返回 `{"ok": true}`
- [ ] 已确认嵌入模型与 FAISS 索引加载完成（服务启动日志无报错，首个 `/ask` 请求正常）
- [ ] 已重载 Nginx：`sudo nginx -t && sudo systemctl reload nginx`
- [ ] 已观察错误日志：`journalctl -u healthassistant -n 100 --no-pager`、`/var/log/nginx/error.log`
- [ ] 未发现异常后才对外公布

常用发布命令参考：

```bash
cd /opt/healthassistant/app_src
git fetch --tags && git checkout <new-tag>
source .venv/bin/activate && pip install -r requirements.txt
(cd frontend && npm ci && npm run build)
sudo systemctl restart healthassistant
curl -s http://127.0.0.1:8000/healthz
```

### F. 发布验证检查

**技术验证**
- [ ] 首页可以正常访问（HTTPS，无证书告警）
- [ ] 静态资源（JS/CSS）加载正常
- [ ] 刷新页面不出现 404（`try_files` 生效）
- [ ] 侧栏底部显示后端健康状态正常
- [ ] `POST /api/ask` 返回正常，包含 `answer`、`disclaimer`、`citations`、`policy`
- [ ] 前端控制台无严重错误
- [ ] 无明显 404、500、超时（含 Nginx 504）
- [ ] 审计日志 `app/logs/audit.jsonl` 正常追加写入

验证命令：

```bash
curl https://your-domain.com/api/healthz
curl -X POST https://your-domain.com/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"头痛伴随发烧该如何处理？","user_id":"deploy_check"}'
```

**业务与合规验证**
- [ ] 普通健康问题能返回带引用来源的教育性回答
- [ ] 红旗症状（如“胸痛、呼吸困难”）触发高风险分诊与就医提示
- [ ] 诊断/处方类问题被安全拦截并返回拒答提示
- [ ] 含姓名、身份证号、手机号的问题已被 PHI 脱敏
- [ ] 每个回答均带免责声明和引用来源
- [ ] 审计日志中用户 ID 为哈希值，不含明文 PHI

**监控验证**
- [ ] 5xx 错误率正常
- [ ] P95 延迟正常（主要取决于 DeepSeek 响应时间）
- [ ] CPU、内存使用率正常（无内存持续增长）
- [ ] 磁盘使用率正常，日志增长速度可控
- [ ] DeepSeek API 调用成功率与额度正常
- [ ] 告警没有异常增长，用户反馈没有集中异常

### G. 发布完成检查

- [ ] 已确认发布成功
- [ ] 已记录最终版本号与 Commit SHA
- [ ] 已更新变更日志（CHANGELOG）
- [ ] 已通知相关人员发布结果
- [ ] 已关闭发布窗口
- [ ] 已保留上一版本代码/制品
- [ ] 已确认回滚路径仍然可用
- [ ] 已归档发布记录与验证结果
- [ ] 如有问题，已创建复盘任务

---

## 五、回滚方案

触发条件：`/healthz` 持续失败、5xx 明显上升、核心问答不可用、安全拦截或免责声明失效、出现 PHI 泄露风险。

```bash
cd /opt/healthassistant/app_src
git checkout <previous-tag>
source .venv/bin/activate && pip install -r requirements.txt
(cd frontend && npm ci && npm run build)
sudo systemctl restart healthassistant
curl -s http://127.0.0.1:8000/healthz
```

如涉及知识库变更，同时恢复备份的 `app/data/`，再重启服务。

## 六、常见问题

| 现象 | 可能原因 | 处理 |
|---|---|---|
| 启动很慢或超时 | 首次下载嵌入模型 | 检查 `HF_ENDPOINT` 网络连通性；预先下载并设置 `HF_HOME`；增大 `TimeoutStartSec` |
| 页面刷新 404 | Nginx 缺少 `try_files` | 参考第三章 Nginx 配置 |
| 前端请求 `/api` 返回 404 | `proxy_pass` 末尾缺少 `/` | 使用 `proxy_pass http://127.0.0.1:8000/;` 以去掉 `/api` 前缀 |
| 浏览器报 CORS 错误 | 跨域访问且 `allow_origins` 仅含 localhost | 使用同域 Nginx 代理，或修改 `app/main.py` |
| `/ask` 返回 500 | `DEEPSEEK_API_KEY` 缺失/无效，或服务器无法访问外网 | 检查 `config.env` 与出口网络；`journalctl` 查看详情 |
| 读取不到 `config.env` | 工作目录不在项目根目录 | 确认 systemd 的 `WorkingDirectory` |
| 审计日志写入失败 | `app/logs/` 权限不足 | `chown` 给运行用户 |
| 内存不足被 OOM Kill | 模型加载占用内存大 | 升级内存、保持 `--workers 1`、增加 swap |
| 504 Gateway Timeout | LLM 响应慢 | 调大 `proxy_read_timeout` |

## 七、最终发布检查卡

- **发布前**：代码已评审、测试已通过、构建已完成、配置已确认、数据已备份、监控已准备、回滚方案已验证
- **发布中**：发布负责人在线、发布记录已开启、`/healthz` 正常、错误率正常、延迟正常
- **发布后**：核心问答与安全拦截验证通过、日志无异常、告警无异常、相关人员已通知、发布结果已归档

> 发布不是一次操作，而是一套可重复、可验证、可回滚的工程流程。
