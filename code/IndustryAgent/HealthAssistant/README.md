# 参考代码
https://github.com/yh-yao/super_agent_book/tree/main/%E5%8C%BB%E7%96%97%E5%81%A5%E5%BA%B7%E6%99%BA%E8%83%BD%E4%BD%93



# 健康智能助手 (合规优先的 RAG + LLM 系统)

一个专注于**合规性、安全性和可解释性**的参考级**医疗健康助手**。
它提供基于检索增强生成的响应，包含**免责声明、引用来源和审计日志**。
> ⚠️ 仅供教育演示使用。非医疗设备。不能替代专业医疗护理。

## 核心特性

### 🔍 检索增强生成 (RAG)
- 基于可信本地指南进行信息检索（如 `data/` 中的临床指南片段样本）
- 使用向量数据库 (FAISS) 进行高效的语义搜索
- 支持多种医疗文档格式和知识库

### 🤖 LLM 合成响应
- 明确的**免责声明 + 范围控制**
- 基于 DeepSeek 的智能响应生成
- 结构化的提示工程，确保医疗场景下的安全性

### 🛡️ 安全防护机制
- **分诊红旗标识**：自动识别紧急医疗情况
- **限制性声明控制**：防止超出系统能力范围的医疗建议
- **个人健康信息 (PHI) 去标识化**：基础的隐私保护
- **基于角色的提示控制**：确保系统始终保持助手角色

### 📚 引用和追溯
- **JSON 格式的证据包**：返回给调用者完整的引用信息
- **来源标记**：每个建议都有明确的来源标识
- **可追溯性**：确保所有建议都有可验证的依据

### 📋 审计和合规
- **JSONL 格式审计日志**：记录用户ID哈希值和策略决策
- **完整的操作记录**：包括查询、响应和安全策略触发情况
- **合规性追踪**：支持医疗机构的合规要求

### 🌐 多种接口
- **React Web 界面**：现代化聊天式交互界面
- **FastAPI 服务器**：RESTful API 接口
- **命令行界面 (CLI)**：便于测试和开发
- **结构化响应**：支持患者信息、症状描述等结构化输入

## 快速开始

### 环境准备
```bash
# 创建虚拟环境
python -m venv .venv && source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env   # 填入您的 DEEPSEEK_API_KEY

# 安装前端依赖
cd frontend && npm install && cd ..
```

### 启动服务

**方式一：Web 应用（推荐）**

需要两个终端：

```bash
# 终端 1 —— 启动 FastAPI 后端（端口 8000）
uvicorn app.main:app --reload

# 终端 2 —— 启动 React 前端（端口 5173，自动代理 /api 到后端）
cd frontend && npm run dev
```

打开 http://localhost:5173 即可使用聊天式界面：
- 左侧填写用户 ID 与可选的患者信息（年龄、性别、疾病史、用药、过敏史）
- 主区域进行问答，响应中展示**分诊等级徽章**（低/中/高风险）、**安全拦截提示**、**免责声明**与可展开的**引用来源**
- 侧栏底部显示后端健康状态（对应 `/healthz`）

**方式二：仅 API / CLI**

```bash
# 启动 FastAPI 服务器
uvicorn app.main:app --reload

# 使用cli.py访问
python app/cli.py --question "我叫张三先生，身份证号码是123456789，手机号是13812345678，我现在头痛该怎么办？"
```

### 前端生产构建（可选）
```bash
cd frontend
npm run build   # 输出到 frontend/dist，可由任意静态服务器或 FastAPI StaticFiles 托管
npm run preview # 本地预览生产构建
```

### API 使用示例
```bash
# 健康检查
curl http://localhost:8000/healthz

# 提问示例
curl -X POST "http://localhost:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "头痛伴随发烧该如何处理？",
    "user_id": "user_123",
    "patient": {
      "age": 35,
      "gender": "female",
      "medical_history": ["高血压"]
    }
  }'
```

## 项目结构

```
health_agent/
├── app/
│   ├── __init__.py          # 包初始化
│   ├── main.py              # FastAPI 主应用（含 CORS）
│   ├── cli.py               # 命令行界面
│   ├── config.py            # 配置管理
│   ├── models.py            # Pydantic 数据模型
│   ├── rag.py               # 检索增强生成核心逻辑
│   ├── llm.py               # LLM 交互接口
│   ├── guardrails.py        # 安全防护机制
│   ├── privacy.py           # 隐私保护功能
│   ├── citations.py         # 引用管理
│   ├── audit.py             # 审计日志
│   ├── prompts.py           # 提示模板
│   └── data/                # 医疗指南和知识库
├── frontend/                # React (Vite) Web 前端
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js       # 开发代理 /api -> localhost:8000
│   └── src/
│       ├── App.jsx          # 主界面（聊天 + 侧栏）
│       ├── api.js           # 后端 API 封装
│       ├── styles.css       # 全局样式
│       └── components/
│           ├── PatientForm.jsx      # 用户ID + 患者信息表单
│           └── AssistantMessage.jsx # 回答 + 分诊徽章 + 引用
├── requirements.txt         # Python 依赖
├── .env.example            # 环境变量模板
└── README.md               # 项目文档
```

## 核心依赖

- **FastAPI**: 现代、高性能的 Web 框架
- **OpenAI SDK**: 调用 DeepSeek API（OpenAI 兼容协议），模型默认 `deepseek-chat`
- **Sentence Transformers**: 文本嵌入和语义搜索
- **FAISS**: 高效的向量相似度搜索
- **Pydantic**: 数据验证和序列化
- **Uvicorn**: ASGI 服务器

## 技术架构详解

### 系统流程图
```
用户输入 -> 隐私清洗 -> 安全防护 -> RAG检索 -> LLM生成 -> 引用标记 -> 审计记录 -> 返回结果
```

### 核心组件说明

#### 1. 隐私保护模块 (`privacy.py`)
- **PHI 检测**：识别和标记个人健康信息
- **数据脱敏**：自动清理敏感信息
- **匿名化处理**：用户ID哈希化

#### 2. 安全防护模块 (`guardrails.py`)
- **紧急情况识别**：胸痛、呼吸困难、意识不清等
- **风险分级**：低风险、中风险、高风险分类
- **自动转诊**：高风险情况自动建议就医

#### 3. RAG 检索模块 (`rag.py`)
- **文档索引**：医疗指南的向量化存储
- **语义搜索**：基于查询相关性的文档检索
- **上下文提取**：相关段落的智能提取

#### 4. LLM 交互模块 (`llm.py`)
- **提示优化**：医疗场景专用的提示模板
- **响应控制**：确保输出符合医疗助手规范
- **token 管理**：优化API调用成本

## 安全和合规注意事项

### ⚠️ 重要免责声明
- 本代码包含**安全阻断机制**，会**拒绝诊断**并在出现红旗症状时建议**寻求医疗护理路径**
- 您必须用您机构的**已审核、已授权指南**替换 `data/` 中的示例数据
- 部署前必须添加您自己的 **DPO/IRB/合规性审查**

### 🔒 隐私保护
- 基础的个人健康信息 (PHI) 去标识化
- 用户ID哈希化存储
- 敏感信息过滤和清理

### 🛡️ 安全机制
- 紧急情况自动识别和转诊建议
- 超出能力范围的查询自动拒绝
- 医疗建议的明确范围限制

### 📊 审计功能
- 完整的查询和响应日志
- 策略决策追踪
- 合规性报告支持


## 许可证和法律

本项目仅供教育和研究目的。在任何医疗环境中使用前，请确保：
- 符合当地医疗法规（如HIPAA、GDPR等）
- 通过必要的合规审查（IRB、DPO等）
- 获得适当的医疗许可
- 遵守隐私保护法规
- 进行充分的安全测试

### 法律责任
- 开发者和部署者负责确保合规性
- 系统不提供诊断，仅提供教育信息
- 用户需要寻求专业医疗建议

---

**再次提醒：这不是医疗设备，不能替代专业医疗建议。如有医疗紧急情况，请立即联系急救服务（中国：120，美国：911）。**
