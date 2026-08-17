# 1 天气与计算器Agent
一个完整的 **DeepSeek + LangChain 天气与计算器 Agent** 示例。它支持：

- “北京今天适合出差吗？”
- “如果机票是 1280 元，酒店是 860 元，总费用是多少？”
- “上海天气怎么样？需要带伞吗？”

示例中：

- 使用 **DeepSeek** 作为大语言模型；
- 使用 **LangChain Tool Calling Agent**；
- 使用 `wttr.in` 获取天气，不需要天气 API Key；
- 使用安全的 AST 解析器完成计算，不直接使用 `eval`。



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

# 2 企业制度问答 Agent
这个 Agent 具备以下能力：

1. 先判断用户问题属于哪一类制度；
2. 根据问题类型调用对应的制度知识工具；
3. 只依据制度内容回答；
4. 制度中没有明确规定时，不进行猜测；
5. 对无法归类的问题直接说明暂无相关制度依据；
6. 最终给出简洁回答。

示例制度包括：

- 出差报销标准；
- 请假制度；
- 加班申请流程；
- 采购审批规则。

## 1. 安装依赖

```bash
pip install -U \
  langchain \
  langchain-openai \
  langgraph \
  langchain-core \
  python-dotenv
```



## 2. 配置 DeepSeek Key

在项目目录下创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=你的DeepSeek_API_Key
```

DeepSeek API 兼容 OpenAI 接口，因此使用 `ChatOpenAI`，但需要配置：

```python
base_url="https://api.deepseek.com"
```

## 3. 运行方式

```bash
python enterprise_policy_agent.py
```



## 4. 调用示例

### 示例 1：出差报销

输入：

```text
去上海出差，住宿每天最多可以报销多少？
```

处理过程：

```text
用户问题
  ↓
分类：business_trip
  ↓
调用 get_business_trip_policy
  ↓
根据制度原文回答
```

可能输出：

```text
北京、上海、广州、深圳的住宿标准为每人每天 500 元以内。超过该标准的部分，除非事前获得部门负责人书面批准，否则不予报销。

相关制度：出差报销标准。
```



### 示例 2：请假审批

输入：

```text
请假两天需要谁审批？
```

可能输出：

```text
连续请假超过 1 个工作日且不超过 3 个工作日，需要直属主管和部门负责人审批。

相关制度：请假制度。
```



### 示例 3：加班申请

输入：

```text
加班应该提前多久申请？
```

制度原文没有明确规定“提前多久”，因此 Agent 应该回答：

```text
现有制度未明确规定加班申请需要提前多久，无法根据现有制度确认。制度仅规定，确需加班的，应提前在 OA 系统中提交加班申请；因紧急情况无法提前申请的，应先向直属主管报备，并原则上在加班结束后 1 个工作日内补交申请。
```



### 示例 4：采购审批

输入：

```text
采购 8 万元的设备需要哪些审批？
```

可能输出：

```text
单笔金额超过 50,000 元，需要部门负责人、财务部门和分管副总审批。

另外，单笔金额超过 50,000 元，原则上应至少进行三家供应商比价；如果只有一家供应商或无法比价，需要在申请中说明原因。

相关制度：采购审批规则。
```



### 示例 5：制度没有依据的问题

输入：

```text
公司员工迟到一次扣多少钱？
```

可能输出：

```text
暂未找到与该问题直接对应的企业制度依据，无法给出确定答案。建议咨询人力资源部门。
```



## 5 Agent 流程图

该示例的 LangGraph 流程如下：

```text
START
  ↓
classify_question
  ↓
retrieve_policy
  ↓
generate_answer
  ↓
END
```

其中：

```text
classify_question
```

负责判断问题类型：

```text
business_trip
leave
overtime
procurement
unknown
```

然后：

```text
retrieve_policy
```

根据分类结果调用对应工具：

```python
POLICY_TOOLS = {
    "business_trip": get_business_trip_policy,
    "leave": get_leave_policy,
    "overtime": get_overtime_policy,
    "procurement": get_procurement_policy,
}
```

最后：

```text
generate_answer
```

只能基于工具返回的制度原文生成回答。


## 6 关键的防幻觉设计

### 1. 分类失败时默认使用 `unknown`

```python
return "unknown"
```

不确定时不强行匹配制度。


### 2. 制度查询不到时不回答具体结论

```python
if category == "unknown" or not policy_content:
    return {
        "answer": "暂未找到与该问题直接对应的企业制度依据，无法给出确定答案。"
    }
```


### 3. 生成答案时明确限制来源

```text
只使用制度原文中明确出现的信息。
不得补充制度中没有写明的金额、时间、审批人或例外规则。
```

### 4. 对制度中没有具体说明的问题明确拒答

例如制度只写了“应提前申请”，但没有写“提前几天”，那么 Agent 不应该回答“提前三天”，而应该说：

```text
现有制度未明确规定，无法根据现有制度确认。
```



## 7 生产环境接入向量数据库

上面的示例是直接读取内存中的制度内容：

```python
POLICY_DOCUMENTS = {
    "business_trip": "...",
    "leave": "...",
}
```

生产环境可以将制度文件放在：

```text
policies/
├── 出差报销标准.md
├── 请假制度.md
├── 加班申请流程.md
└── 采购审批规则.md
```

然后使用：

- Chroma；
- FAISS；
- Milvus；
- Elasticsearch；
- OpenSearch；
- PostgreSQL + pgvector。

不过企业制度问答建议保留“制度类别路由”：

```text
先分类
  ↓
只在对应制度库中检索
  ↓
返回相关条款
  ↓
基于条款回答
```

比所有制度混在一起检索更容易控制答案来源，也能降低不同制度之间相互干扰的风险。

例如后续可以将：

```python
get_business_trip_policy()
```

替换为：

```python
business_trip_retriever.invoke(question)
```

将制度全文检索改成相关条款检索，但 Agent 的整体结构仍然保持不变。
