# AutoGen
## 配置文件 `config.env`
由于当前环境不允许创建以 `.` 开头的文件，因此使用 `config.env`，内容如下：
```env
DEEPSEEK_API_KEY=你的 DeepSeek API Key
```

例如：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

`config.env` 应该放在 Python 脚本所在的目录中。

项目结构可以是：

```text
项目目录/
├── flower_agents.py
├── config.env
└── tasks/
```

其中：

- `IC-Talent-AutoGen.py` 是 Python 主程序；
- `config.env` 保存 API Key；
- `tasks/` 用于保存 AutoGen 运行过程中产生的文件。

**注意**：不要把真实 API Key 直接写到 Python 代码中，也不要将 `config.env` 提交到 Git 仓库。

## 导入模块

```python
import os
import autogen
from dotenv import load_dotenv
```

三个模块的作用如下：

### `os`

Python 的标准库，用于读取操作系统中的环境变量：

```python
os.getenv("DEEPSEEK_API_KEY")
```

### `autogen`

AutoGen 框架，用于创建多个 AI Agent，并让这些 Agent 之间进行对话和协作。

### `dotenv`

`python-dotenv` 提供的模块，可以读取 `config.env` 文件，并将文件中的配置加载为环境变量。

安装命令：

```bash
pip install python-dotenv
```

## 配置 DeepSeek 模型

```python
llm_config = {
    "config_list": [
        {
            "model": "deepseek-chat",
            "api_key": deepseek_api_key,
            "base_url": "https://api.deepseek.com/v1",
        }
    ],
    "temperature": 0.7,
}
```


主要配置项说明：

### `model`

```python
"model": "deepseek-chat"
```

表示使用 DeepSeek 的通用对话模型。

### `api_key`

```python
"api_key": deepseek_api_key
```

使用前面从 `config.env` 读取的 API Key，而不是直接写入明文密钥。

### `base_url`

```python
"base_url": "https://api.deepseek.com/v1"
```

指定 DeepSeek 的 API 服务地址。DeepSeek 提供兼容 OpenAI API 格式的接口，因此 AutoGen 可以通过类似的配置调用。

### `temperature`

```python
"temperature": 0.7
```

控制模型输出的随机性：

- 数值较低，例如 `0.2`：回答更加稳定、严谨；
- 数值较高，例如 `1.0`：回答更加多样、具有创造性；
- `0.7`：适合市场分析和文章创作等任务。

## 任务列表

例如：

```python
inventory_tasks = [
    """查看当前库存中各种鲜花的数量，并报告哪些鲜花库存不足。""",
    """根据过去一个月的销售数据，预测接下来一个月哪些鲜花的需求量会增加。""",
]
```

这里使用 Python 列表保存任务。

目前代码中使用的是第一个库存任务：

```python
inventory_tasks[0]
```

列表下标从 `0` 开始，因此：

- `inventory_tasks[0]` 表示第一个任务；
- `inventory_tasks[1]` 表示第二个任务。

需要注意，当前任务只是文字描述，并没有真正连接库存数据库或销售数据。因此模型只能根据对话中提供的信息进行分析，无法自动获得真实库存和销售记录。

## 创建 Assistant Agent

```python
inventory_assistant = autogen.AssistantAgent(
    name="库存管理助理",
    llm_config=llm_config,
)
```

`AssistantAgent` 表示由大语言模型驱动的 AI 助理。

这里创建了三个不同职责的助理：

### 库存管理助理

负责库存数量和库存不足情况分析。

### 市场研究助理

负责分析市场趋势和受欢迎的鲜花种类。

### 内容创作助理

负责撰写IC人才博客文章。

每个助理都使用同一个 `llm_config`，因此都通过 DeepSeek API 调用模型。

原代码中有一处语法错误：

```python
llm_config llm_config
```

正确写法是：

```python
llm_config=llm_config
```

等号左侧是参数名，右侧是变量名。

## `system_message` 的作用

内容创作助理中有以下设置：

```python
system_message="""
    你是一名专业的写作者，以洞察力强和文章引人入胜著称。
    你能将复杂的概念转化为引人入胜的叙述。
    当一切完成后，请回复“结束”。
"""
```

`system_message` 用于规定助理的角色、写作风格和行为规则。

它会影响模型后续生成的所有回答。例如：

- 将模型设定为专业写作者；
- 要求文章具有吸引力；
- 要求任务完成后回复“结束”。

## 创建用户代理

代码创建了两个 `UserProxyAgent`。

### 自动用户代理

```python
user_proxy_auto = autogen.UserProxyAgent(
    name="用户代理_自动",
    human_input_mode="NEVER",
    ...
)
```

`human_input_mode="NEVER"` 表示不等待人工输入，自动执行任务。

它用于库存管理和市场研究任务：

```python
"sender": user_proxy_auto
```

### 人工用户代理

```python
user_proxy = autogen.UserProxyAgent(
    name="用户代理",
    human_input_mode="ALWAYS",
    ...
)
```

`human_input_mode="ALWAYS"` 表示任务过程中需要人工参与或确认。

它用于内容创作任务：

```python
"sender": user_proxy
```

如果不希望写作任务过程中等待人工输入，可以将其改为：

```python
human_input_mode="NEVER"
```

## 终止条件

```python
is_termination_msg=lambda x: (
    x.get("content", "")
    and x.get("content", "").rstrip().endswith("结束")
)
```

这段代码用于判断对话是否结束。

逻辑如下：

1. 从消息中获取 `content`；
2. 去除末尾空格；
3. 判断内容是否以“结束”结尾；
4. 如果是，则终止当前对话。

例如，模型回复：

```text
博客文章已经完成。结束
```

程序就会认为该任务已经完成。

## 代码执行配置

```python
code_execution_config={
    "last_n_messages": 1,
    "work_dir": "tasks",
    "use_docker": False,
}
```

配置说明：

### `last_n_messages`

```python
"last_n_messages": 1
```

表示代码执行时参考最近的一条消息。

### `work_dir`

```python
"work_dir": "tasks"
```

指定代码执行工作的目录。如果目录不存在，通常需要提前创建：

```bash
mkdir tasks
```

Windows PowerShell 可以使用：

```powershell
New-Item -ItemType Directory tasks
```

### `use_docker`

```python
"use_docker": False
```

表示不使用 Docker 执行代码。

这种配置更容易运行，但安全隔离能力较弱。如果 Agent 需要执行不可信代码，建议使用 Docker 或关闭代码执行功能。

## 发起多个对话

```python
chat_results = autogen.initiate_chats([...])
```

`initiate_chats` 会按照列表中的顺序依次发起任务。

当前执行顺序如下：

1. 用户代理自动向库存管理助理发送库存任务；
2. 用户代理自动向市场研究助理发送市场分析任务；
3. 用户代理向内容创作助理发送博客写作任务。

## 各个对话配置

第一个任务：

```python
{
    "sender": user_proxy_auto,
    "recipient": inventory_assistant,
    "message": inventory_tasks[0],
    "clear_history": True,
    "silent": False,
    "summary_method": "last_msg",
}
```

说明：

- `sender`：发送方；
- `recipient`：接收任务的 Agent；
- `message`：发送的任务内容；
- `clear_history=True`：开始时清除之前的对话历史；
- `silent=False`：显示对话过程；
- `summary_method="last_msg"`：使用最后一条消息作为总结。

第二个任务：

```python
{
    "sender": user_proxy_auto,
    "recipient": market_research_assistant,
    "message": market_research_tasks[0],
    "max_turns": 2,
    "summary_method": "reflection_with_llm",
}
```

其中：

```python
"max_turns": 2
```

表示最多进行两轮对话。

```python
"summary_method": "reflection_with_llm"
```

表示让模型对对话内容进行反思和总结，通常比简单使用最后一条消息更加完整，但会额外调用模型。

第三个任务：

```python
{
    "sender": user_proxy,
    "recipient": content_creator,
    "message": content_creation_tasks[0],
    "carryover": "我希望在博客文章中包含一张数据表格或图表。",
}
```

`carryover` 用于向当前任务补充额外要求。这里要求文章中包含一张数据表格或图表。

## 安装和运行

安装依赖：

```bash
pip install pyautogen python-dotenv
```

如果使用的是特定版本的 AutoGen，也可以按照对应版本的官方安装方式进行安装。

然后确认目录中存在：

```text
IC-Talent-AutoGen.py
config.env
tasks/
```

运行程序：

```bash
python IC-Talent-AutoGen.py
```

如果提示找不到 `config.env`，说明当前运行目录不正确，或者配置文件没有放在 Python 程序所在目录中。可以改成绝对路径，或者确保从项目根目录运行程序。

## 安全注意事项

`config.env` 中包含敏感信息，需要加入 `.gitignore`：

```gitignore
config.env
```

不要在代码中使用以下写法：

```python
"api_key": "sk-xxxxxxxxxxxxxxxx"
```

推荐始终使用：

```python
"api_key": deepseek_api_key
```

这样可以避免 API Key 被提交到 Git、上传到代码仓库或暴露给其他人。
