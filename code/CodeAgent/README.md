# 参考来源

https://github.com/yh-yao/super_agent_book/tree/main/%E7%BC%96%E7%A8%8B%E6%99%BA%E8%83%BD%E4%BD%93



# 程序运行演示

[【无声演示】智能编程助手：分析代码质量给出修改建议](https://www.bilibili.com/video/BV1hxaT6HEMx/)
# 智能编程助手

**智能编程助手**是一个完全自主的AI智能体，能够理解并执行本地代码库中的复杂编程任务。它由大型语言模型（LLM）驱动，可以分析、规划和执行代码修改。

## 功能特点

- **自主操作**：只需提供一条指令，智能编程助手就能处理剩下的所有工作。
- **代码分析**：自动分析您的代码库以理解上下文。
- **LLM驱动的规划**：生成逐步执行计划来实现您的需求。
- **自我修正**：如果计划失败，智能编程助手将重新分析问题并尝试修正自己的计划。
- **安全的试运行**：在实际修改任何文件之前，所有更改都会在试运行模式下测试。

## 快速开始

### 1. 安装

```bash
pip install -e .
```

### 2. 设置您的 DeepSeek API 密钥

智能编程助手使用 DeepSeek 模型。复制 `config.env.example` 为 `config.env` 并填入密钥：

```bash
cp config.env.example config.env
# 编辑 config.env: DEEPSEEK_API_KEY=your-deepseek-api-key
```

### 3. 运行智能体

使用 `auto` 命令给智能编程助手一个指令。您需要提供项目路径和要执行任务的清晰指令。

```bash
smartcoder auto -p /path/to/your/project -i "你的指令"
```

例如，要在演示项目中将函数 `old_function` 重命名为 `new_function`，可以运行：

```bash
smartcoder auto -p ./examples/demo_project -i "将函数 'greeting' 重命名为 'say_hello'"
```

要直接将更改应用到文件，使用 `--apply` 标志：

```bash
smartcoder auto -p ./examples/demo_project -i "添加一个新函数用于说再见" --apply
```

## 工作原理

`auto` 命令协调一系列步骤：

1.  **分析**：扫描您的项目以建立对代码的上下文理解。
2.  **规划**：将分析结果和您的指令发送给 LLM，生成详细的执行计划。
3.  **执行（试运行）**：执行计划的试运行以验证更改，而不修改任何文件。如果计划失败，它将循环回到规划步骤，将错误作为附加上下文提供给 LLM。
4.  **应用（可选）**：如果试运行成功且您使用了 `--apply` 标志，智能体将把更改写入您的文件。
5.  **验证**：对修改后的文件执行最终语法检查，以确保代码完整性。

每次运行的所有日志都保存在项目内的 `.smartcoder/logs` 目录中。

## Web 应用（React + DeepSeek）

除了 CLI，本项目还提供了一个基于 **React** 的 Web 界面，使用 **DeepSeek** 模型驱动智能规划。

### 1. 设置 DeepSeek API 密钥

复制 `config.env.example` 为 `config.env`，填入你的密钥：

```bash
cp config.env.example config.env
# 编辑 config.env，设置 DEEPSEEK_API_KEY=your-deepseek-api-key
```

`config.env` 支持的配置项（也可用同名环境变量覆盖）：
- `DEEPSEEK_API_KEY`：必填，你的 DeepSeek API 密钥
- `DEEPSEEK_BASE_URL`：默认 `https://api.deepseek.com`
- `DEEPSEEK_MODEL`：默认 `deepseek-chat`（可切换为 `deepseek-reasoner`）

### 2. 启动后端（FastAPI，端口 8000）

```bash
cd webapp/backend
pip install -r requirements.txt
python app.py
```

### 3. 启动前端（Vite + React，端口 5173）

```bash
cd webapp/frontend
npm install
npm run dev
```

然后浏览器打开 `http://localhost:5173`。

### Web 界面功能

- 输入项目路径和指令，一键执行完整流程（分析 → 规划 → 试运行 → 应用 → 验证）
- 实时 SSE 流式展示执行进度（阶段时间线 + 运行日志）
- 可视化代码库分析结果（函数、类、潜在问题）
- 展示 DeepSeek 生成的执行计划及替换前/后代码
- 失败自动重新规划（最多 3 次）；默认试运行，勾选「应用更改」才写入磁盘

```
