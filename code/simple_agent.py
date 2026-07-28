import ast
import math
import operator as op
import os
from typing import Any

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI


# ============================================================
# 1. 安全计算器
# ============================================================

_ALLOWED_OPERATORS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.Pow: op.pow,
    ast.Mod: op.mod,
    ast.USub: op.neg,
    ast.UAdd: op.pos,
}

# 限制表达式长度，避免传入极端复杂的表达式
_MAX_EXPRESSION_LENGTH = 200

# 限制幂运算指数，避免产生极大的数字导致内存或 CPU 消耗过高
_MAX_POWER = 1000


def _safe_eval(node: ast.AST) -> int | float:
    """
    递归计算 AST 表达式。

    只允许：
    - 整数
    - 浮点数
    - 加法
    - 减法
    - 乘法
    - 除法
    - 取模
    - 幂运算
    - 正负号

    不直接使用 eval。
    """

    if isinstance(node, ast.Constant):
        value = node.value

        # bool 是 int 的子类，因此必须单独排除
        if isinstance(value, bool):
            raise ValueError("不允许使用布尔值")

        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("不允许使用无穷大或 NaN")

            return value

        raise ValueError("只允许使用整数或浮点数")

    if isinstance(node, ast.UnaryOp):
        operator_type = type(node.op)

        if operator_type not in _ALLOWED_OPERATORS:
            raise ValueError("不支持的单目运算符")

        value = _safe_eval(node.operand)

        return _ALLOWED_OPERATORS[operator_type](value)

    if isinstance(node, ast.BinOp):
        operator_type = type(node.op)

        if operator_type not in _ALLOWED_OPERATORS:
            raise ValueError("不支持的双目运算符")

        left = _safe_eval(node.left)
        right = _safe_eval(node.right)

        # 单独限制幂运算
        if operator_type is ast.Pow:
            if not isinstance(right, (int, float)):
                raise ValueError("幂运算指数必须是数字")

            if abs(right) > _MAX_POWER:
                raise ValueError(
                    f"幂运算指数不能超过 {_MAX_POWER}"
                )

            # 对浮点数负指数进行基本保护
            if left == 0 and right < 0:
                raise ValueError("0 不能进行负数幂运算")

        try:
            result = _ALLOWED_OPERATORS[operator_type](left, right)
        except ZeroDivisionError:
            raise ValueError("除数不能为 0")
        except OverflowError:
            raise ValueError("计算结果过大")

        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("计算结果不是有限数字")

        return result

    raise ValueError(
        "表达式中包含不支持的内容，只允许数字和基本数学运算"
    )


@tool
def calculator(expression: str) -> str:
    """
    计算数学表达式。

    支持的运算符：
    +、-、*、/、%、**

    参数：
        expression:
            只包含数字和基本运算符的数学表达式。
            例如：
            "25 * 48 + 120"
            "2 ** 10"

    返回：
        计算结果或错误信息。
    """

    if not isinstance(expression, str):
        return "计算失败：表达式必须是字符串"

    expression = expression.strip()

    if not expression:
        return "计算失败：表达式不能为空"

    if len(expression) > _MAX_EXPRESSION_LENGTH:
        return (
            f"计算失败：表达式长度不能超过 "
            f"{_MAX_EXPRESSION_LENGTH} 个字符"
        )

    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return str(result)

    except SyntaxError:
        return "计算失败：表达式语法不正确"

    except ValueError as exc:
        return f"计算失败：{exc}"

    except Exception as exc:
        return f"计算失败：{exc}"


# ============================================================
# 2. 模型配置
# ============================================================

def _normalize_base_url(base_url: str) -> str:
    """
    将 base_url 规范化为 OpenAI API 根地址。

    ChatOpenAI 需要的是：
        https://example.com/v1

    而不是：
        https://example.com/v1/chat/completions
    """

    base_url = base_url.strip().rstrip("/")

    suffix = "/chat/completions"

    if base_url.endswith(suffix):
        base_url = base_url[: -len(suffix)]

    return base_url


def create_model() -> ChatOpenAI:
    """
    根据 MODEL_PROVIDER 创建大语言模型。

    支持的提供商：

    1. qwen

       环境变量：
           DASHSCOPE_API_KEY
           MODEL_NAME，可选，默认 qwen-plus
           MODEL_BASE_URL，可选

       默认地址：
           https://dashscope.aliyuncs.com/compatible-mode/v1

    2. openai

       环境变量：
           OPENAI_API_KEY
           MODEL_NAME，可选，默认 gpt-4o-mini
           MODEL_BASE_URL，可选

       默认地址：
           https://api.openai.com/v1

    3. compatible

       环境变量：
           MODEL_API_KEY
           MODEL_BASE_URL
           MODEL_NAME
    """

    provider = os.getenv("MODEL_PROVIDER", "qwen").strip().lower()

    if provider == "qwen":
        api_key = os.getenv("DASHSCOPE_API_KEY")

        if not api_key:
            raise RuntimeError(
                "使用 Qwen 时必须设置 DASHSCOPE_API_KEY 环境变量"
            )

        model_name = os.getenv("MODEL_NAME", "qwen-plus")

        base_url = os.getenv(
            "MODEL_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=_normalize_base_url(base_url),
            temperature=0,
        )

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise RuntimeError(
                "使用 OpenAI 时必须设置 OPENAI_API_KEY 环境变量"
            )

        model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")

        base_url = os.getenv(
            "MODEL_BASE_URL",
            "https://api.openai.com/v1",
        )

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=_normalize_base_url(base_url),
            temperature=0,
        )

    if provider == "compatible":
        api_key = os.getenv("MODEL_API_KEY")
        base_url = os.getenv("MODEL_BASE_URL")
        model_name = os.getenv("MODEL_NAME")

        if not api_key:
            raise RuntimeError(
                "使用 compatible 时必须设置 MODEL_API_KEY 环境变量"
            )

        if not base_url:
            raise RuntimeError(
                "使用 compatible 时必须设置 MODEL_BASE_URL 环境变量"
            )

        if not model_name:
            raise RuntimeError(
                "使用 compatible 时必须设置 MODEL_NAME 环境变量"
            )

        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=_normalize_base_url(base_url),
            temperature=0,
        )

    raise ValueError(
        f"不支持的模型提供商：{provider}。"
        "可选值：qwen、openai、compatible"
    )


# ============================================================
# 3. 创建 Agent
# ============================================================

model = create_model()

agent = create_agent(
    model=model,
    tools=[calculator],
    system_prompt=(
        "你是一个有帮助的中文智能助手。"
        "当用户提出数学计算问题时，必须优先调用 calculator 工具，"
        "不能直接心算或猜测结果。"
        "调用工具后，请根据工具返回结果，用简洁、清晰的中文回答。"
        "如果计算失败，请准确说明失败原因。"
    ),
)


# ============================================================
# 4. 处理 Agent 返回内容
# ============================================================

def _get_message_content(message: Any) -> str:
    """
    兼容不同 LangChain 版本的消息内容格式。

    content 可能是：
    - 字符串
    - 内容块列表
    """

    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts = []

        for block in content:
            if isinstance(block, str):
                text_parts.append(block)

            elif isinstance(block, dict):
                text = block.get("text")

                if isinstance(text, str):
                    text_parts.append(text)

        return "".join(text_parts)

    return str(content)


# ============================================================
# 5. 启动程序
# ============================================================

def main() -> None:
    user_input = os.getenv(
        "USER_INPUT",
        "请计算 25 * 48 + 120，并告诉我结果。",
    )

    try:
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": user_input,
                    }
                ]
            }
        )

        messages = result.get("messages", [])

        if not messages:
            raise RuntimeError("Agent 没有返回任何消息")

        final_message = messages[-1]
        final_content = _get_message_content(final_message)

        print("智能体回答：")
        print(final_content)

    except Exception as exc:
        print(f"调用智能体失败：{exc}")


if __name__ == "__main__":
    main()