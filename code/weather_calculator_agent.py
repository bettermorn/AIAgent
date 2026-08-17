import ast
import json
import operator
import os
import re
from typing import Union

import requests
from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain.agents.middleware import (
    after_model,
    before_model,
    wrap_tool_call,
)
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


# 加载 .env
load_dotenv()


# ============================================================
# 1. 天气工具
# ============================================================

@tool
def get_weather(city: str) -> str:
    """
    查询指定城市今天的天气。

    参数：
    city: 城市名称，例如北京、上海、广州、深圳。

    返回：
    当前温度、体感温度、天气状况、降雨概率、风速以及出行建议。
    当用户询问天气、是否需要带伞、是否适合出差时，必须调用此工具。
    """

    city = city.strip()

    city_mapping = {
        "北京": "Beijing",
        "上海": "Shanghai",
        "广州": "Guangzhou",
        "深圳": "Shenzhen",
        "杭州": "Hangzhou",
        "南京": "Nanjing",
        "成都": "Chengdu",
        "重庆": "Chongqing",
        "武汉": "Wuhan",
        "西安": "Xi'an",
        "天津": "Tianjin",
        "苏州": "Suzhou",
        "厦门": "Xiamen",
        "青岛": "Qingdao",
        "大连": "Dalian",
        "哈尔滨": "Harbin",
        "昆明": "Kunming",
        "长沙": "Changsha",
        "郑州": "Zhengzhou",
        "济南": "Jinan",
    }

    query_city = city_mapping.get(city, city)

    url = f"https://wttr.in/{query_city}"

    try:
        response = requests.get(
            url,
            params={
                "format": "j1",
                "lang": "zh",
            },
            headers={
                "User-Agent": "Mozilla/5.0",
            },
            timeout=15,
        )

        response.raise_for_status()
        data = response.json()

    except requests.RequestException as e:
        return f"天气查询失败：{e}"

    except ValueError:
        return "天气查询失败：天气服务返回的数据格式不正确。"

    try:
        current = data["current_condition"][0]
        today = data["weather"][0]

        temperature = current.get("temp_C", "未知")
        feels_like = current.get("FeelsLikeC", "未知")
        humidity = current.get("humidity", "未知")
        wind_speed = current.get("windspeedKmph", "未知")
        wind_direction = current.get("winddir16Point", "未知")

        weather_description = (
            current.get("lang_zh", [{}])[0].get("value")
            or current.get("weatherDesc", [{}])[0].get("value")
            or "未知"
        )

        max_temp = today.get("maxtempC", "未知")
        min_temp = today.get("mintempC", "未知")

        # 统计今天各时段的降雨概率
        hourly_data = today.get("hourly", [])

        rain_chances = []

        for item in hourly_data:
            chance_of_rain = item.get("chanceofrain", "0")

            try:
                rain_chances.append(int(chance_of_rain))
            except (ValueError, TypeError):
                pass

        max_rain_chance = max(rain_chances) if rain_chances else 0

        # 根据降雨概率给出建议
        if max_rain_chance >= 60:
            umbrella_advice = "今天降雨概率较高，建议携带雨伞。"
        elif max_rain_chance >= 30:
            umbrella_advice = "今天有一定降雨可能，建议随身携带折叠伞。"
        else:
            umbrella_advice = "今天降雨概率较低，通常不必特意带伞。"

        # 根据温度给出建议
        try:
            temperature_number = float(temperature)
        except (ValueError, TypeError):
            temperature_number = 20

        if temperature_number <= 5:
            clothing_advice = "天气较冷，建议做好保暖。"
        elif temperature_number >= 32:
            clothing_advice = "天气较热，注意防暑降温。"
        else:
            clothing_advice = "温度总体适中，正常着装即可。"

        travel_advice = f"{umbrella_advice}{clothing_advice}"

        result = {
            "城市": city,
            "日期": today.get("date", "今天"),
            "当前天气": weather_description,
            "当前温度": f"{temperature}°C",
            "体感温度": f"{feels_like}°C",
            "今日最高温": f"{max_temp}°C",
            "今日最低温": f"{min_temp}°C",
            "湿度": f"{humidity}%",
            "风速": f"{wind_speed} km/h",
            "风向": wind_direction,
            "今日最大降雨概率": f"{max_rain_chance}%",
            "出行建议": travel_advice,
        }

        return json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )

    except (KeyError, IndexError, TypeError) as e:
        return f"天气数据解析失败：{e}"


# ============================================================
# 2. 安全计算器工具
# ============================================================

_ALLOWED_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_calculate(expression: str) -> Union[int, float]:
    """
    使用 AST 安全解析四则运算表达式。

    支持：
    +、-、*、/、%、**、括号、小数、负数。
    """

    def evaluate(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value

            raise ValueError("只允许数字")

        if isinstance(node, ast.Num):
            return node.n

        if isinstance(node, ast.BinOp):
            operator_type = type(node.op)

            if operator_type not in _ALLOWED_OPERATORS:
                raise ValueError("不支持的运算符")

            left = evaluate(node.left)
            right = evaluate(node.right)

            # 限制幂运算，避免异常大的计算
            if operator_type is ast.Pow and abs(right) > 10:
                raise ValueError("幂运算指数过大")

            return _ALLOWED_OPERATORS[operator_type](left, right)

        if isinstance(node, ast.UnaryOp):
            operator_type = type(node.op)

            if operator_type not in _ALLOWED_OPERATORS:
                raise ValueError("不支持的一元运算符")

            operand = evaluate(node.operand)

            return _ALLOWED_OPERATORS[operator_type](operand)

        raise ValueError("表达式中包含不支持的内容")

    tree = ast.parse(expression, mode="eval")

    return evaluate(tree.body)


@tool
def calculate(expression: str) -> str:
    """
    计算数学表达式。

    参数：
    expression: 数学表达式，例如：
    1280 + 860
    100 * 0.85
    (1280 + 860) / 2

    支持中文金额中的“元”、人民币符号、逗号。
    当用户询问总费用、加法、减法、乘法、除法或其他数学计算时，调用此工具。
    """

    # 清理常见金额格式
    expression = expression.strip()
    expression = expression.replace("人民币", "")
    expression = expression.replace("元", "")
    expression = expression.replace("￥", "")
    expression = expression.replace("¥", "")
    expression = expression.replace(",", "")
    expression = expression.replace("，", "")

    # 只允许数字、运算符、小数点和括号
    if not re.fullmatch(
        r"[\d\s\+\-\*\/\%\(\)\.]+",
        expression,
    ):
        return (
            "计算失败：表达式中包含不支持的字符。"
            "请使用数字、+、-、*、/、%、括号和小数点。"
        )

    try:
        result = safe_calculate(expression)

        # 处理浮点数显示
        if isinstance(result, float):
            if result.is_integer():
                result_text = str(int(result))
            else:
                result_text = f"{result:.2f}".rstrip("0").rstrip(".")
        else:
            result_text = str(result)

        return f"{expression} = {result_text}"

    except ZeroDivisionError:
        return "计算失败：不能除以 0。"

    except Exception as e:
        return f"计算失败：{e}"


# ============================================================
# 3. 初始化 DeepSeek
# ============================================================

deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

if not deepseek_api_key:
    raise ValueError(
        "没有找到 DEEPSEEK_API_KEY，请在 .env 文件中配置 DeepSeek API Key。"
    )


llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=deepseek_api_key,
    base_url="https://api.deepseek.com",
    temperature=0,
)


# ============================================================
# 4. Middleware
# ============================================================

@before_model
def log_before_model(state, runtime):
    """
    在每次模型调用前执行。

    state 中的 messages 包含当前 Agent 的完整消息链，
    包括用户消息、AI 消息、工具调用消息和工具返回消息。
    """

    messages = state.get("messages", [])

    print(
        f"[middleware] 即将调用模型，当前消息数量：{len(messages)}"
    )

    return None


@after_model
def log_after_model(state, runtime):
    """
    在每次模型调用后执行。
    """

    messages = state.get("messages", [])

    if messages:
        last_message = messages[-1]

        print(
            "[middleware] 模型调用完成，"
            f"最新消息类型：{type(last_message).__name__}"
        )

    return None


@wrap_tool_call
def handle_tool_errors(request, handler):
    """
    包装所有工具调用，统一捕获工具异常。

    如果工具发生未处理异常，则返回 ToolMessage，
    让 Agent 可以继续处理，而不是直接导致整个程序崩溃。
    """

    try:
        return handler(request)

    except Exception as e:
        tool_call = request.tool_call

        tool_name = tool_call.get("name", "未知工具")
        tool_call_id = tool_call.get("id", "")

        print(
            f"[middleware] 工具调用失败：{tool_name}，错误：{e}"
        )

        return ToolMessage(
            content=(
                f"工具 {tool_name} 调用失败。"
                f"错误信息：{e}"
            ),
            tool_call_id=tool_call_id,
        )


# ============================================================
# 5. 创建 LangChain Agent
# ============================================================

tools = [
    get_weather,
    calculate,
]


SYSTEM_PROMPT = """
你是一个中文智能助手，负责处理天气查询和数学计算。

你的行为规则：

1. 用户询问天气时，必须调用 get_weather 工具，不能凭空编造天气。
2. 用户询问“是否需要带伞”时，必须先调用 get_weather 工具。
3. 用户询问“是否适合出差”时，必须先查询天气，再结合温度、降雨概率、风力给出建议。
4. 用户询问总费用、价格相加或其他数学问题时，必须调用 calculate 工具。
5. 计算结果必须以 calculate 工具返回的结果为准，不能自行猜测。
6. 最终回答使用中文，表达清晰、简洁。
7. 如果是天气问题，请说明天气数据可能存在实时延迟。
8. 如果用户的问题同时包含多个任务，需要依次调用相应工具。
9. 如果工具返回错误信息，应当如实告知用户，不要编造结果。

天气建议可以参考：

- 降雨概率较高：建议带伞；
- 温度过低：建议保暖；
- 温度过高：注意防暑；
- 风力较大：出差或户外活动需要谨慎。
"""


agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        log_before_model,
        log_after_model,
        handle_tool_errors,
    ],
)


# ============================================================
# 6. 命令行交互
# ============================================================

def get_message_text(message) -> str:
    """
    提取 LangChain 消息的文本内容。

    某些模型返回的 content 可能是字符串，
    也可能是内容块列表。
    """

    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []

        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            else:
                text_parts.append(str(block))

        return "".join(text_parts)

    return str(content)


def main():
    print("天气与计算器 Agent 已启动。")
    print("输入 exit、quit 或 退出可以结束程序。")
    print()

    # 新版 create_agent 使用 messages 作为状态
    messages = []

    while True:
        user_input = input("用户：").strip()

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "退出"]:
            print("程序结束。")
            break

        try:
            # 将本轮用户消息追加到 Agent 消息状态中
            messages.append(
                HumanMessage(content=user_input)
            )

            result = agent.invoke(
                {
                    "messages": messages,
                }
            )

            # create_agent 返回的结果中包含完整 messages
            messages = result["messages"]

            # 从最后一条消息中提取最终回答
            answer = get_message_text(messages[-1])

            print(f"助手：{answer}")
            print()

        except Exception as e:
            print(f"调用失败：{e}")
            print()

            # 如果本轮调用失败，移除刚刚追加的用户消息，
            # 避免下一轮继续携带可能不完整的状态
            if messages and isinstance(messages[-1], HumanMessage):
                messages.pop()


if __name__ == "__main__":
    main()
