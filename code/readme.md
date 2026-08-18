
# 企业制度问答 Agent
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
