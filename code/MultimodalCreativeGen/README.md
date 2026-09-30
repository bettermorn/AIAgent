# ✨ AI 多模态创意工坊（React Web 版）

基于 **React + Express + DeepSeek** 的多 Agent 创意生成 Web 应用。输入产品与目标受众，三个 Agent 自动协作完成广告创作：

| Agent | 职责 | 实现 |
| --- | --- | --- |
| 📝 文案 Agent | 生成广告文案初稿 | DeepSeek `deepseek-chat` |
| ✅ 校对 Agent | 润色优化文案 | DeepSeek `deepseek-chat` |
| 🎨 设计 Agent | 生成 SVG 广告海报 | DeepSeek `deepseek-chat` |


程序运行演示

[【无声演示】多模态创意生成智能体](https://www.bilibili.com/video/BV1DPho6REU5/)

## 参考代码
https://github.com/yh-yao/super_agent_book/tree/main/%E5%A4%9A%E6%A8%A1%E6%80%81%E5%88%9B%E6%84%8F%E7%94%9F%E6%88%90

## 项目结构

```
2MultimodalCreativeGen/
├── config.env            # API Key 配置文件（不提交到 git）
├── config.env.example    # 配置模板
├── package.json          # 根启动脚本
├── server/               # Express 后端（Agent 逻辑）
│   ├── index.js          # 三个 Agent 的 API 端点
│   └── package.json
├── frontend/             # React (Vite) 前端
│   ├── src/App.jsx       # 主界面：表单 + Agent 流程可视化 + 海报展示
│   └── src/styles.css
├── agents/               # （旧版 Python CLI，可忽略）
├── workflows/
└── main.py
```

## 快速开始

### 1. 配置 API Key

在项目根目录创建 `config.env`（可直接复制模板）：

```bash
cp config.env.example config.env
```

编辑 `config.env`，填入你的 Key（在 [DeepSeek 开放平台](https://platform.deepseek.com/) 获取）：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

可选配置：

```env
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# DEEPSEEK_MODEL=deepseek-chat
# PORT=3001
```

> 说明：API Key 仅在服务端读取和使用，不会暴露到浏览器。

### 2. 安装依赖

需要 Node.js ≥ 18。

```bash
npm run install:all   # 安装 server 与 frontend 依赖
npm install           # 安装根目录启动工具
```

### 3. 启动应用

```bash
npm start
```

该命令会并行启动：

- 后端：<http://localhost:3001>（Express，调用 DeepSeek API）
- 前端：<http://localhost:5173>（React + Vite，开发服务器）

浏览器打开 **http://localhost:5173**，输入产品名称与目标受众，点击「开始创作」即可看到三个 Agent 依次工作并输出最终文案与 AI 生成的 SVG 海报。

## API 说明

| 端点 | 方法 | 参数 | 返回 |
| --- | --- | --- | --- |
| `/api/copywriter` | POST | `{ product, audience }` | `{ draft }` 文案初稿 |
| `/api/reviewer` | POST | `{ text }` | `{ final }` 润色后文案 |
| `/api/designer` | POST | `{ text }` | `{ svg }` SVG 海报代码 |
| `/api/health` | GET | - | 服务与配置状态 |

前端开发服务器已将 `/api` 代理到 `http://localhost:3001`。

## 工作原理

1. **文案 Agent**：根据产品与受众，让 DeepSeek 写一句 ≤15 字的广告文案；
2. **校对 Agent**：以创意总监口吻对初稿润色，使其更有感染力；
3. **设计 Agent**：让 DeepSeek 以纯 SVG 代码绘制一张 800×1000 的扁平风海报（DeepSeek 无图像生成接口，故用 SVG 实现可视化海报），前端直接渲染该 SVG。

## 旧版 Python CLI（可选）

原始的 LangChain 命令行版本仍保留：

```bash
pip install -r requirements.txt
python main.py --product "夏日柠檬饮料" --audience "年轻人"
```
