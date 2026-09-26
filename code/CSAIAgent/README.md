# Helpdesk AI

基于 LangChain + Pinecone + FastAPI + React 的企业客服智能体。
支持 FAQ 问答、工单生成、投诉处理与多轮记忆，并提供现代化 Web 聊天界面。

## 项目结构

```
RAG_CustomerService_KQA/
├── app/                # FastAPI 后端
│   ├── main.py         # 应用入口与路由（/chat、/feedback）
│   ├── chains.py       # LangChain 意图路由链
│   ├── tools.py        # 工单创建等工具
│   ├── memory.py       # 多轮会话记忆
│   ├── router_schemas.py  # 请求/响应模型
│   └── config.py       # 配置加载
├── ingest/             # 知识库向量化脚本
├── data/               # 知识库原始数据
├── models/             # 本地模型
└── web/                # React 前端（Vite + React 18）
    └── src/
        ├── App.jsx                 # 主界面（侧边栏 + 聊天区）
        ├── api.js                  # 后端 API 封装
        ├── styles.css              # 全局样式
        └── components/
            ├── ChatInput.jsx       # 输入框与快捷问题
            ├── MessageBubble.jsx   # 消息气泡（意图徽章/工单号）
            └── FeedbackForm.jsx    # 星级评分反馈
```

## 使用方法

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 创建 `.env` 文件：
   在 `helpdesk_agent` 目录下新建 `.env` 文件，内容如下：
   ```env
   OPENAI_API_KEY=your-openai-api-key
   PINECONE_API_KEY=your-pinecone-api-key
   PINECONE_INDEX=helpdesk-knowledge
   ```

3. 登录 Pinecone：
   前往 [Pinecone 官网](https://www.pinecone.io/) 注册并获取 API Key，创建一个index，可以命名为helpdesk-knowledge，填入 `.env` 文件。

4. 向量模型与维度：
   本项目使用 `text-embedding-3-small` 模型，维度为 `512`。请确保 Pinecone Index 创建时维度为 512。

5. 构建向量索引：
   ```bash
   python ingest/index_pinecone.py
   ```

6. 启动后端服务：
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

## 向量索引存储位置

本项目的向量索引**不存储在本地磁盘，而是保存在 Pinecone 云服务中**：

- **索引名**：`helpdesk-knowledge`（由 `config.env` 中的 `PINECONE_INDEX` 变量指定，见 `app/config.py`）
- **云环境**：AWS `us-east-1` 的 Serverless 架构，相似度度量为 cosine
- **向量生成**：本地 Embedding 模型 `./models/AI-ModelScope--bge-small-zh-v1.5`，维度在运行时由模型实际输出决定
- **写入入口**：`ingest/index_pinecone.py` 通过 `PineconeVectorStore.from_texts()` 将 `data/` 中的知识库分块向量化后上传

索引不存在时会自动创建（`ingest/index_pinecone.py`），本地目录中不存在 `.faiss`、`.chroma` 之类的索引文件。

**如何查看已创建的索引**：

1. 登录 [Pinecone 控制台](https://app.pinecone.io)，使用 `PINECONE_API_KEY` 对应的账号，即可看到 `helpdesk-knowledge` 索引及其中的向量数据；
2. 或在脚本中调用 `pc.list_indexes()`（`ingest/index_pinecone.py` 中已有此逻辑）打印现有索引列表。

## 启动 Web 前端（React）

后端启动后，另开一个终端：

```bash
cd web
npm install
npm run dev
```

访问 `http://localhost:5173` 即可使用 Web 聊天界面。

- 开发环境下，前端通过 Vite 代理将 `/api/*` 请求转发到 `http://127.0.0.1:8000`，无需额外配置。
- 生产构建：`npm run build`，产物在 `web/dist/`，可用 `npm run preview` 本地预览。

### Web 界面功能

- 智能对话：消息气泡区分用户/AI，展示意图徽章（FAQ / 工单 / 投诉 / 闲聊）
- 工单创建：AI 创建工单后高亮展示工单号
- 服务反馈：每次回复后可进行星级评分（1-5 星）并填写评论，提交至 `/feedback`
- 快捷提问：内置常见问题一键发送
- 会话管理：侧边栏显示/编辑会话 ID 与用户 ID，支持清空对话
- 响应式布局：桌面与移动端均可正常使用

## 调用示例：

### 1. 能从 data 找到答案的问答
```bash
curl -X POST http://127.0.0.1:8000/chat \
   -H "Content-Type: application/json" \
   -d '{"session_id":"s2","user_id":"u99","query":"你们的服务时间是什么？"}'
```
返回内容示例：
```json
{"intent":"FAQ","answer":"我们的服务时间是周一至周五，上午9点至下午6点（当地时间）【1】。如果您有其他问题或需要进一步的帮助，请随时联系支持团队。","ticket_id":null,"meta":{}}
```

### 2. 未命中知识库时的问答
```bash
curl -X POST http://127.0.0.1:8000/chat \
   -H "Content-Type: application/json" \
   -d '{"session_id":"s1","user_id":"u42","query":"发票要如何开具？"}'
```
返回内容示例：
```json
{"intent":"FAQ","answer":"很抱歉，检索结果中没有关于发票开具的具体信息。如果您需要详细的发票开具流程，建议您转工单或直接联系相关支持部门。您可以通过发送邮件至 support@helpdesk.com 或拨打 1-800-555-1234 来获取帮助。","ticket_id":null,"meta":{}}
```

### 3. 反馈接口（feedback）
```bash
curl -X POST http://127.0.0.1:8000/feedback \
   -H "Content-Type: application/json" \
   -d '{"session_id":"s2","score":5,"comment":"回复很及时，谢谢！"}'
```
返回结果：
```json
{"ok": true}
```
反馈结果仅为 {"ok": true}，用于记录用户评分和评论。

### 4. 创建工单（触发 create_or_update_ticket）
```bash
curl -X POST http://127.0.0.1:8000/chat \
   -H "Content-Type: application/json" \
   -d '{"session_id":"s3","user_id":"u100","query":"我无法登录账号，请帮我创建一个工单"}'
```
返回内容示例：
```json
{"intent":"TICKET","answer":"已为你创建工单 51fb8504（状态：open），我们会尽快处理。","ticket_id":"51fb8504","meta":{}}
```
   
