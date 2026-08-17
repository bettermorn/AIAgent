import json
import os
import re
from typing import TypedDict, Literal

from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END


# ============================================================
# 1. 加载环境变量
# ============================================================

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not DEEPSEEK_API_KEY:
    raise ValueError(
        "没有找到 DEEPSEEK_API_KEY，请在 .env 文件中配置 DeepSeek API Key。"
    )


# ============================================================
# 2. 定义问题类型
# ============================================================

PolicyCategory = Literal[
    "business_trip",
    "leave",
    "overtime",
    "procurement",
    "unknown",
]


CATEGORY_NAMES = {
    "business_trip": "出差报销标准",
    "leave": "请假制度",
    "overtime": "加班申请流程",
    "procurement": "采购审批规则",
    "unknown": "未知或非制度问题",
}


# ============================================================
# 3. 配置企业制度知识
#
# 实际项目中可以将这些内容放到数据库、Markdown、向量数据库或知识库中。
# ============================================================

POLICY_DOCUMENTS = {
    "business_trip": """
【制度名称】出差报销标准

1. 交通费
- 高铁或动车原则上乘坐二等座。
- 飞机经济舱需要提前申请。
- 未经批准乘坐商务座、头等舱或公务舱的，超出标准部分原则上不予报销。
- 市内交通可以选择公共交通或网约车，需保留有效发票或电子行程单。

2. 住宿费
- 北京、上海、广州、深圳：住宿标准为每人每天 500 元以内。
- 其他城市：住宿标准为每人每天 350 元以内。
- 超出住宿标准的部分，除非事前获得部门负责人书面批准，否则不予报销。

3. 餐补
- 国内出差餐补标准为每人每天 100 元。
- 如果出差期间由公司或客户统一安排用餐，对应餐次不再重复领取餐补。

4. 报销时限
- 出差结束后 15 个工作日内提交报销。
- 报销需要提供审批通过的出差申请、发票以及必要的行程凭证。

5. 特殊情况
- 制度没有明确规定的费用，需要在发生前向部门负责人或财务部门确认。
""",

    "leave": """
【制度名称】请假制度

1. 请假类型
- 年假、事假、病假、婚假、产假、陪产假等按照公司规定执行。
- 不同假别需要提交对应证明材料的，应按要求提供。

2. 申请要求
- 员工请假原则上应提前在 OA 系统提交申请。
- 申请内容包括请假类型、开始时间、结束时间、请假天数和事由。

3. 审批权限
- 连续请假 1 个工作日以内，由直属主管审批。
- 连续请假超过 1 个工作日且不超过 3 个工作日，由直属主管和部门负责人审批。
- 连续请假超过 3 个工作日，还需要人力资源部门审批。

4. 紧急情况
- 因突发疾病或紧急事项无法提前申请的，应先通过电话或即时通讯工具向直属主管报备。
- 员工返岗后 2 个工作日内补办 OA 请假手续。

5. 注意事项
- 未经批准擅自缺勤不属于正常请假。
- 制度未明确说明的特殊假别，应咨询人力资源部门。
""",

    "overtime": """
【制度名称】加班申请流程

1. 加班原则
- 公司不鼓励无计划加班。
- 因项目交付、紧急故障或客户需求确需加班的，应提前申请。

2. 申请流程
- 员工在 OA 系统中填写加班申请。
- 申请内容包括加班日期、预计开始时间、预计结束时间、工作内容和预计时长。
- 提交直属主管审批。
- 涉及跨部门项目的，还需要项目负责人确认。

3. 事后补申请
- 因突发故障、紧急客户需求等无法提前申请的，应先向直属主管报备。
- 原则上应在加班结束后 1 个工作日内补交申请。
- 是否属于紧急情况由直属主管确认。

4. 加班认定
- 未提交申请或未获得批准的加班，可能无法认定为有效加班。
- 公司是否安排调休或加班补偿，应根据审批结果及相关劳动制度执行。

5. 制度边界
- 本制度没有规定具体加班费金额。
- 关于加班费具体计算方式，应咨询人力资源部门。
""",

    "procurement": """
【制度名称】采购审批规则

1. 采购申请
- 采购前需要在 OA 或采购系统提交采购申请。
- 申请内容包括采购物品、规格、数量、预算金额、使用部门、用途和期望到货时间。

2. 审批金额规则
- 单笔金额 5,000 元以下：由部门负责人审批。
- 单笔金额 5,000 元以上且不超过 50,000 元：由部门负责人和财务部门审批。
- 单笔金额超过 50,000 元：由部门负责人、财务部门和分管副总审批。
- 单笔金额超过 200,000 元：除上述审批外，还需要总经理审批。

3. 供应商和比价
- 单笔金额超过 10,000 元，原则上应至少进行两家供应商比价。
- 单笔金额超过 50,000 元，原则上应至少进行三家供应商比价。
- 只有一家供应商或无法比价的，需要在申请中说明原因。

4. 紧急采购
- 紧急采购需要说明紧急原因，并取得有权限的负责人确认。
- 紧急采购完成后，应按采购系统要求补齐材料。

5. 禁止事项
- 未经审批不得先采购后补审批。
- 不得通过拆分订单规避审批权限。
- 制度没有规定的特殊采购情形，应咨询采购部门或财务部门。
""",
}


# ============================================================
# 4. 定义制度查询工具
#
# 这些工具可以替换成数据库查询、向量检索或企业知识库检索。
# ============================================================

@tool
def get_business_trip_policy() -> str:
    """
    查询出差报销标准。
    当用户咨询差旅费、交通费、住宿费、餐补、出差报销时调用。
    """
    return POLICY_DOCUMENTS["business_trip"]


@tool
def get_leave_policy() -> str:
    """
    查询请假制度。
    当用户咨询年假、事假、病假、婚假、产假、请假审批时调用。
    """
    return POLICY_DOCUMENTS["leave"]


@tool
def get_overtime_policy() -> str:
    """
    查询加班申请流程。
    当用户咨询加班、加班审批、加班申请、调休或加班认定时调用。
    """
    return POLICY_DOCUMENTS["overtime"]


@tool
def get_procurement_policy() -> str:
    """
    查询采购审批规则。
    当用户咨询采购、采购审批、采购金额、供应商比价、紧急采购时调用。
    """
    return POLICY_DOCUMENTS["procurement"]


POLICY_TOOLS = {
    "business_trip": get_business_trip_policy,
    "leave": get_leave_policy,
    "overtime": get_overtime_policy,
    "procurement": get_procurement_policy,
}


# ============================================================
# 5. 初始化 DeepSeek
# ============================================================

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    temperature=0,
)


# ============================================================
# 6. LangGraph 状态定义
# ============================================================

class PolicyAgentState(TypedDict, total=False):
    question: str
    category: str
    category_name: str
    policy_content: str
    answer: str


# ============================================================
# 7. 安全解析分类结果
# ============================================================

def parse_category(content: str) -> str:
    """
    从 DeepSeek 返回的内容中提取分类。
    期望返回：
    {"category": "leave"}
    """

    content = content.strip()

    # 去掉 Markdown 代码块
    content = re.sub(r"```json\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"```\s*", "", content)

    # 优先直接解析 JSON
    try:
        data = json.loads(content)
        category = data.get("category", "unknown")

        if category in CATEGORY_NAMES:
            return category
    except json.JSONDecodeError:
        pass

    # 如果模型额外输出了解释，则使用正则提取
    match = re.search(
        r'"category"\s*:\s*"(business_trip|leave|overtime|procurement|unknown)"',
        content,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).lower()

    # 兜底：不确定时必须返回 unknown
    return "unknown"


# ============================================================
# 8. 节点一：判断问题类型
# ============================================================

def classify_question(state: PolicyAgentState) -> PolicyAgentState:
    question = state["question"]

    classification_prompt = f"""
你是企业制度分类器。

请判断用户问题最相关的制度类别，只能从以下类别中选择一个：

- business_trip：出差报销标准，包括交通、住宿、餐补、差旅报销
- leave：请假制度，包括年假、事假、病假、婚假、产假、请假审批
- overtime：加班申请流程，包括加班申请、加班审批、加班认定、调休
- procurement：采购审批规则，包括采购金额、采购审批、供应商比价、紧急采购
- unknown：无法归类、制度中没有涉及，或与上述制度无关

只返回 JSON，不要输出解释：

{{
  "category": "business_trip|leave|overtime|procurement|unknown"
}}

用户问题：
{question}
"""

    response = llm.invoke(classification_prompt)
    category = parse_category(response.content)

    return {
        **state,
        "category": category,
        "category_name": CATEGORY_NAMES[category],
    }


# ============================================================
# 9. 节点二：调用对应制度工具
# ============================================================

def retrieve_policy(state: PolicyAgentState) -> PolicyAgentState:
    category = state["category"]

    if category not in POLICY_TOOLS:
        return {
            **state,
            "policy_content": "",
        }

    selected_tool = POLICY_TOOLS[category]

    try:
        # LangChain Tool 的标准调用方式
        policy_content = selected_tool.invoke({})
    except Exception as e:
        policy_content = f"制度知识查询失败：{e}"

    return {
        **state,
        "policy_content": policy_content,
    }


# ============================================================
# 10. 节点三：基于制度原文生成答案
# ============================================================

def generate_answer(state: PolicyAgentState) -> PolicyAgentState:
    question = state["question"]
    category = state.get("category", "unknown")
    category_name = state.get("category_name", "未知或非制度问题")
    policy_content = state.get("policy_content", "")

    if category == "unknown" or not policy_content:
        return {
            **state,
            "answer": (
                "暂未找到与该问题直接对应的企业制度依据，"
                "无法给出确定答案。建议咨询人力资源、财务、采购或直属主管。"
            ),
        }

    answer_prompt = f"""
你是企业制度问答助手。

请严格根据下面提供的制度原文回答用户问题。

【问题类别】
{category_name}

【用户问题】
{question}

【制度原文】
{policy_content}

回答要求：

1. 只使用制度原文中明确出现的信息。
2. 不得补充制度中没有写明的金额、时间、审批人或例外规则。
3. 如果制度原文无法回答用户问题，必须明确回答：
   “现有制度未明确规定，无法根据现有制度确认。”
4. 回答简洁，优先直接给出结论。
5. 如果涉及多个条件，请使用项目符号列出。
6. 可以在回答最后注明相关制度名称。
7. 不要说“根据常识”“一般来说”“通常情况下”。
8. 不要编造公司名称、部门名称或内部流程。

请直接输出中文答案，不要输出分析过程。
"""

    response = llm.invoke(answer_prompt)

    return {
        **state,
        "answer": response.content.strip(),
    }


# ============================================================
# 11. 构建 LangGraph
# ============================================================

def build_graph():
    graph_builder = StateGraph(PolicyAgentState)

    graph_builder.add_node("classify_question", classify_question)
    graph_builder.add_node("retrieve_policy", retrieve_policy)
    graph_builder.add_node("generate_answer", generate_answer)

    # 必须先分类，再查询制度，再生成答案
    graph_builder.add_edge(START, "classify_question")
    graph_builder.add_edge("classify_question", "retrieve_policy")
    graph_builder.add_edge("retrieve_policy", "generate_answer")
    graph_builder.add_edge("generate_answer", END)

    return graph_builder.compile()


policy_graph = build_graph()


# ============================================================
# 12. 调试调用
# ============================================================

def ask_agent(question: str) -> str:
    result = policy_graph.invoke(
        {
            "question": question,
        }
    )

    return result["answer"]


# ============================================================
# 13. 命令行交互
# ============================================================

def main():
    print("企业制度问答 Agent 已启动。")
    print("支持：出差报销、请假、加班申请、采购审批。")
    print("输入 exit、quit 或 退出结束程序。")
    print()

    while True:
        question = input("用户：").strip()

        if not question:
            continue

        if question.lower() in ["exit", "quit", "退出"]:
            print("程序结束。")
            break

        try:
            result = policy_graph.invoke(
                {
                    "question": question,
                }
            )

            print(f"助手：{result['answer']}")
            print()

        except Exception as e:
            print(f"系统调用失败：{e}")
            print()


if __name__ == "__main__":
    main()
