# 参考代码

https://github.com/yh-yao/super_agent_book/tree/main/%E6%B3%95%E5%BE%8B%E6%99%BA%E8%83%BD%E4%BD%93



# 法律合规助手 (React Web 应用)

一个可运行的**法律合规助手** Web 应用，用于法规问答（RAG）、基础合规差距分析和轻量级合同审查演示。
后端使用 **FastAPI**，前端使用 **React (Vite)**，大语言模型调用 **DeepSeek**（`DEEPSEEK_API_KEY`）。

> ⚠️ 此工具**不**提供法律建议。它是一个辅助系统，必须由合格的法律顾问审查。

## 功能特性 (MVP)
- 基于示例 GDPR/CCPA 文本的 RAG 问答，包含**引用**与**置信度**
- 基于演示政策集（YAML → 控制措施）的合规差距分析
- 合同审查：提取关键条款并与基线条款（`standard_clauses/baseline_dpa.txt`）比较
- 审计日志：记录提示/响应哈希与时间戳（`reports/audit_log.jsonl`）

## 技术说明
- **LLM**：DeepSeek `deepseek-chat`（通过 OpenAI 兼容 SDK 调用）
- **检索**：DeepSeek 不提供 Embedding API，演示语料采用本地字符二元组 TF-IDF 检索，无需 FAISS 与外部嵌入服务
- **前端**：React 18 + Vite，开发时经代理访问后端；执行 `npm run build` 后由 FastAPI 托管 `web/dist`

## 快速开始

### 1) 后端（Python）
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入您的 DEEPSEEK_API_KEY
```

### 2) 前端（React）
```bash
cd web
npm install
```

### 3) 启动

开发模式（两个终端）：
```bash
# 终端 1：启动后端 API（项目根目录）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：启动前端开发服务器（web 目录）
npm run dev
```

然后访问 **http://localhost:5173** 使用 Web 界面。

生产模式（单服务）：
```bash
cd web && npm run build && cd ..
uvicorn app.main:app --host 0.0.0.0 --port 8000
# 访问 http://127.0.0.1:8000 （FastAPI 直接托管前端构建产物）
```

API 文档：http://127.0.0.1:8000/docs

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/healthz` | 健康检查（含 API Key 配置状态） |
| GET | `/api/meta` | 政策与司法辖区元数据 |
| POST | `/api/qa` | 法规问答（RAG） |
| POST | `/api/compliance/gap` | 合规差距分析 |
| POST | `/api/contracts/review` | 合同审查（文件或文本） |

### 使用示例
```bash
# 法规问答
curl -X POST http://127.0.0.1:8000/api/qa \
  -H "Content-Type: application/json" \
  -d '{"question":"GDPR对处理记录有什么规定？","jurisdictions":["EU"]}'

# 合规差距分析
curl -X POST http://127.0.0.1:8000/api/compliance/gap \
  -H "Content-Type: application/json" \
  -d @fact_example.json

# 合同审查（上传文件）
curl -X POST http://127.0.0.1:8000/api/contracts/review \
  -F "file=@sample_contract.txt"
```

## 自定义语料与政策
- 在 `ingest/corpus/` 中添加 `.txt` / `.md` 法规文本，重启后端即可（无需重建索引）
- 将 `policies/` 中的示例 YAML 替换为您组织的控制措施映射
- 修改 `standard_clauses/baseline_dpa.txt` 以调整合同审查基线

## 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API 密钥 |
| `DEEPSEEK_BASE_URL` | 否 | 默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 否 | 默认 `deepseek-chat` |
| `DEEPSEEK_TEMPERATURE` | 否 | 默认 `0.2` |
| `DEEPSEEK_MAX_TOKENS` | 否 | 默认 `1500` |

## 故障排除
- **前端提示“缺少 DEEPSEEK_API_KEY”**：检查 `.env` 是否配置并已重启后端
- **后端未连接**：确认 8000 端口后端已启动，前端开发服务器代理指向 `127.0.0.1:8000`
- **答案为空**：说明检索未命中语料，可在 `ingest/corpus/` 添加相关法规文本
