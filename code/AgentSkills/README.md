# Agent Skills Demo（React Web 应用 · DeepSeek · SKILL.md）

本项目包含两种使用方式：

1. **Web 应用**（React + Express）：在浏览器中输入主题，由 DeepSeek 模型生成结构化 PPT 大纲
2. **命令行版本**（Python）：原有教学基线版本

## 项目结构

```
AgentSkills/
├── web/                    # Web 应用
│   ├── config.env          # 配置文件（DEEPSEEK_API_KEY 等）
│   ├── server.js           # Express 后端：调用 DeepSeek API
│   ├── package.json
│   └── client/             # React 前端（Vite）
│       ├── src/App.jsx     # 主界面
│       └── src/index.css
├── agent/                  # 命令行版 Agent
├── llm/                    # LLM 封装（命令行版）
├── skills/                 # Agent Skills（PPT 生成）
│   └── ppt_generation/
├── main.py                 # 命令行入口
└── requirements.txt
```

## Web 应用

### 特性

- 前端 React 18 + Vite，后端 Express
- 通过 `config.env` 中的 `DEEPSEEK_API_KEY` 调用 DeepSeek 模型（默认 `deepseek-chat`）
- API Key 仅在后端读取，不暴露给浏览器
- 输入主题 → 生成结构化 PPT 大纲（标题 + 幻灯片内容），卡片式展示
- 支持推荐主题快捷选择、加载动画与错误提示

### API 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查，返回模型名与 Key 是否已配置 |
| POST | `/api/generate` | 入参 `{ "topic": "主题" }`，返回 `{ title, slides, model }` |

### 运行

1. 在 `web/config.env` 中配置密钥：

   ```env
   DEEPSEEK_API_KEY=sk-你的密钥
   # 可选：
   # DEEPSEEK_BASE_URL=https://api.deepseek.com
   # DEEPSEEK_MODEL=deepseek-chat
   # PORT=3001
   ```

2. 安装依赖并启动（前后端一键并行）：

   ```bash
   cd web
   npm install
   npm --prefix client install
   npm run dev
   ```

3. 浏览器打开 `http://localhost:5173`，输入主题（如"新的智能家居助手"）点击生成。

### 生产构建

```bash
cd web
npm --prefix client run build   # 产物输出至 web/client/dist
npm start                       # 启动后端 http://localhost:3001
```

## 命令行版本（Python）

本示例展示：
- 使用真实 LLM 进行推理（生成结构化 IR）
- 使用 Agent Skills 执行确定性能力
- Skill 通过 SKILL.md 声明能力
- Agent 读取 SKILL.md 进行能力感知（不参与内容生成）
- 不使用 MCP，作为教学基线版本

### 运行

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=你的Key
python main.py
```
