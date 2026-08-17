import ast
import json
import operator
import os
import re
from typing import Union

import requests
from dotenv import load_dotenv

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
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

    # 这里只是为了让中文城市查询更加稳定
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
                "User-Agent": "Mozilla/5.0"
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
        weather_types = []

        for item in hourly_data:
            chance_of_rain = item.get("chanceofrain", "0")
            try:
                rain_chances.append(int(chance_of_rain))
            except ValueError:
                pass

            description = (
                item.get("lang_zh", [{}])[0].get("value")
                or item.get("weatherDesc", [{}])[0].get("value")
            )

            if description:
                weather_types.append(description)

        max_rain_chance = max(rain_chances) if rain_chances else 0

        # 根据天气情况给出基础建议
        if max_rain_chance >= 60:
            umbrella_advice = "今天降雨概率较高，建议携带雨伞。"
        elif max_rain_chance >= 30:
            umbrella_advice = "今天有一定降雨可能，建议随身携带折叠伞。"
        else:
            umbrella_advice = "今天降雨概率较低，通常不必特意带伞。"

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

        return json.dumps(result, ensure_ascii=False, indent=2)

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
    if not re.fullmatch(r"[\d\s\+\-\*\/\%\(\)\.]+", expression):
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
# 4. 创建 LangChain Agent
# ============================================================

tools = [
    get_weather,
    calculate,
]

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
"""
你是一个中文智能助手，负责处理天气查询和数学计算。

你的行为规则：

1. 用户询问天气时，必须调用 get_weather 工具，不能凭空编造天气。
2. 用户询问“是否需要带伞”时，必须先调用 get_weather 工具。
3. 用户询问“是否适合出差”时，必须先查询天气，再结合温度、降雨概率、风力给出建议。
4. 用户询问总费用、价格相加或其他数学问题时，必须调用 calculate 工具。
5. 计算结果必须以工具返回的结果为准，不能自行猜测。
6. 最终回答使用中文，表达清晰、简洁。
7. 如果是天气问题，请说明天气数据可能存在实时延迟。
8. 如果用户的问题同时包含多个任务，需要依次调用相应工具。

天气建议可以参考：
- 降雨概率较高：建议带伞；
- 温度过低：建议保暖；
- 温度过高：注意防暑；
- 风力较大：出差或户外活动需要谨慎。
""",
        ),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

agent = create_tool_calling_agent(
    llm=llm,
    tools=tools,
    prompt=prompt,
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    handle_parsing_errors=True,
)


# ============================================================
# 5. 命令行交互
# ============================================================

def main():
    print("天气与计算器 Agent 已启动。")
    print("输入 exit、quit 或 退出 可以结束程序。")
    print()

    chat_history = []

    while True:
        user_input = input("用户：").strip()

        if not user_input:
            continue

        if user_input.lower() in ["exit", "quit", "退出"]:
            print("程序结束。")
            break

        try:
            result = agent_executor.invoke(
                {
                    "input": user_input,
                    "chat_history": chat_history,
                }
            )

            answer = result["output"]
            print(f"助手：{answer}")
            print()

            # 保存简单对话历史
            chat_history.append(("human", user_input))
            chat_history.append(("ai", answer))

        except Exception as e:
            print(f"调用失败：{e}")
            print()


if __name__ == "__main__":
    main()
