# Sample code
一个完整的 **DeepSeek + LangChain 天气与计算器 Agent** 示例。它支持：

- “北京今天适合出差吗？”
- “如果机票是 1280 元，酒店是 860 元，总费用是多少？”
- “上海天气怎么样？需要带伞吗？”

示例中：

- 使用 **DeepSeek** 作为大语言模型；
- 使用 **LangChain Tool Calling Agent**；
- 使用 `wttr.in` 获取天气，不需要天气 API Key；
- 使用安全的 AST 解析器完成计算，不直接使用 `eval`。

---

## 1. 安装依赖

```bash
pip install -U \
  langchain \
  langchain-openai \
  langchain-core \
  requests \
  python-dotenv
```

建议使用较新的 LangChain 版本：

```bash
pip install -U "langchain>=0.2" "langchain-openai>=0.1"
```

---

## 2. 配置 DeepSeek API Key

创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=你的_deepseek_api_key
```

DeepSeek API 兼容 OpenAI 接口，因此可以通过 `ChatOpenAI` 调用，只需要修改：

```python
base_url="https://api.deepseek.com"
```

## 3. 运行

```bash
python weather_calculator_agent.py
```
## 4. 调用示例
### 示例一：天气与出差建议

输入：

```text
北京今天适合出差吗？
```

Agent 大致执行流程：

```text
用户问题
  ↓
调用 get_weather("北京")
  ↓
获取北京今天的天气
  ↓
DeepSeek 根据温度、风力和降雨概率进行分析
  ↓
输出出差建议
```

可能输出：

```text
北京今天整体温度适中，但有一定降雨概率，建议携带折叠伞。若出差涉及户外活动，建议关注实时天气变化。总体来看可以出差，但需要做好防雨准备。
```

---

### 示例二：计算总费用

输入：

```text
如果机票是 1280 元，酒店是 860 元，总费用是多少？
```

Agent 会调用：

```python
calculate("1280 + 860")
```

输出：

```text
总费用是 2140 元。
```

---

### 示例三：上海天气与雨伞建议

输入：

```text
上海天气怎么样？需要带伞吗？
```

Agent 会调用：

```python
get_weather("上海")
```

然后根据天气工具返回的降雨概率回答，例如：

```text
上海今天当前温度为 22°C，天气为多云，今日最高降雨概率为 70%。建议带伞，尤其是需要长时间户外活动时。
```
## 6. 使用真实天气 API

上面的代码使用 `wttr.in`，优点是不需要 API Key，但生产环境建议使用正式天气服务，例如：

- 和风天气；
- OpenWeatherMap；
- WeatherAPI；
- 中国气象数据服务。

以和风天气为例，需要将 `get_weather` 工具替换为调用和风天气 API 的实现。整体 Agent 代码不需要改变，因为 LangChain 只关心工具的名称、参数和返回结果。

---

## 7. 代码结构说明

核心部分是下面三类组件：

### 天气工具

```python
@tool
def get_weather(city: str) -> str:
    ...
```

通过 `@tool` 装饰器后，DeepSeek 能够理解这个工具的名称、参数和功能。

### 计算器工具

```python
@tool
def calculate(expression: str) -> str:
    ...
```

Agent 可以把自然语言中的金额转换成数学表达式：

```text
机票 1280 元 + 酒店 860 元
```

调用：

```text
1280 + 860
```

### Tool Calling Agent

```python
agent = create_tool_calling_agent(
    llm=llm,
    tools=tools,
    prompt=prompt,
)
```

DeepSeek 会根据用户问题自动判断：

- 是否需要查询天气；
- 是否需要进行计算；
- 应该调用哪个工具；
- 工具调用完成后如何组织最终答案。

---

## 8. 生产环境建议

如果用于真实项目，建议进一步增加：

1. **天气 API Key 和请求限流**
2. **天气查询缓存**
3. **城市名称标准化**
4. **多轮对话记忆**
5. **工具调用日志**
6. **请求超时和重试机制**
7. **金额计算的货币单位处理**
8. **对 DeepSeek API 异常进行重试**
9. **使用结构化输出，避免天气结果格式变化导致解析失败**
10. **对用户输入进行更严格的安全校验**

需要注意，天气信息属于实时数据，返回结果可能存在几分钟到几十分钟的延迟，重要出行计划仍应结合官方天气预警信息。
