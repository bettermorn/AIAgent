import os
import sys
import uuid
import requests

from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import tool
from serpapi import GoogleSearch

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    BingGroundingTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
)


# =========================================================
# 安全打印函数
# =========================================================

def safe_print(*args, **kwargs):
    """
    避免某些运行环境下 sys.stdout 不可用导致程序异常。
    """
    if sys.stdout is None or sys.stdout.closed:
        try:
            sys.stdout = sys.__stdout__
        except Exception:
            kwargs["file"] = sys.stderr

    try:
        print(*args, **kwargs)
    except ValueError:
        try:
            print(*args, **kwargs, file=sys.stderr)
        except Exception:
            pass


# =========================================================
# 本地工具
# =========================================================

@tool
def get_current_time() -> str:
    """
    返回当前的日期和时间，格式为 YYYY-MM-DD HH:MM:SS。
    """
    from datetime import datetime

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@tool
def calculate(expression: str) -> str:
    """
    安全计算数学表达式。

    支持：
    - 加法：+
    - 减法：-
    - 乘法：*
    - 除法：/
    - 幂运算：**
    - 括号
    - abs()
    - round()

    示例：
    - 2 + 3 * 4
    - (10 + 5) / 3
    """
    try:
        allowed_functions = {
            "abs": abs,
            "round": round,
        }

        result = eval(
            expression,
            {
                "__builtins__": None,
            },
            allowed_functions,
        )

        return f"计算结果: {result}"

    except Exception as exc:
        return f"计算错误: {exc}"


# =========================================================
# SerpAPI 搜索
# =========================================================

def search_serpapi(query: str) -> str | None:
    """
    使用 SerpAPI 搜索。
    """
    api_key = os.getenv("SERPAPI_API_KEY")

    if not api_key:
        return None

    try:
        wrapper = SerpAPIWrapper(
            serpapi_api_key=api_key,
            timeout=10,
        )

        result = wrapper.run(query)

        if not result:
            return "未找到相关结果。"

        return result

    except Exception as exc:
        error_msg = str(exc).lower()

        if "timeout" in error_msg:
            return "[SerpAPI 超时]"

        if "403" in error_msg or "unauthorized" in error_msg:
            return "[SerpAPI 密钥无效]"

        return f"[SerpAPI 错误: {exc}]"


# =========================================================
# Bocha 搜索
# =========================================================

def search_bocha(query: str) -> str | None:
    """
    使用 Bocha Search 搜索。
    """
    api_key = os.getenv("BOCHA_API_KEY")

    if not api_key:
        return None

    url = "https://api.bocha.cn/v1/web-search"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "query": query,
        "freshness": "noLimit",
        "summary": True,
        "count": 5,
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        # 兼容不同版本的 Bocha 返回结构
        root = data

        if isinstance(root.get("data"), dict):
            root = root["data"]

        web_pages = root.get("webPages", [])

        if isinstance(web_pages, dict):
            web_pages = web_pages.get("value", [])

        # 有些返回结构可能使用 results
        if not web_pages:
            web_pages = root.get("results", [])

        if not isinstance(web_pages, list):
            web_pages = []

        if not web_pages:
            return "未找到相关结果。"

        results = []

        for index, page in enumerate(web_pages[:5], 1):
            if not isinstance(page, dict):
                continue

            title = (
                page.get("name")
                or page.get("title")
                or "无标题"
            )

            snippet = (
                page.get("snippet")
                or page.get("description")
                or page.get("summary")
                or ""
            )

            page_url = (
                page.get("url")
                or page.get("link")
                or ""
            )

            results.append(
                f"{index}. {title}\n"
                f"   摘要：{snippet}\n"
                f"   链接：{page_url}"
            )

        if not results:
            return "未找到相关结果。"

        return "\n\n".join(results)

    except requests.exceptions.Timeout:
        return "[Bocha 超时]"

    except requests.exceptions.HTTPError as exc:
        status_code = getattr(
            exc.response,
            "status_code",
            None,
        )

        if status_code in (401, 403):
            return "[Bocha API 密钥无效或无权限]"

        return f"[Bocha HTTP 错误: {exc}]"

    except requests.exceptions.RequestException as exc:
        return f"[Bocha 网络错误: {exc}]"

    except Exception as exc:
        return f"[Bocha 错误: {exc}]"


# =========================================================
# Azure Bing Grounding 引用提取
# =========================================================

def extract_citations_from_object(obj, citations: list[dict]):
    """
    从 Azure Responses API 的事件、响应、输出项或内容项中提取
    Bing Grounding 返回的 URL 引用。

    兼容以下结构：

        event.item.content[].annotations[]
        response.output[].content[].annotations[]
        response.output_item.done
        response.completed
    """

    if obj is None:
        return

    visited = set()

    def add_citation(annotation):
        """
        从 annotation 对象中提取 URL。
        """
        try:
            if isinstance(annotation, dict):
                annotation_type = annotation.get("type")
                citation_url = annotation.get("url")
                citation_title = annotation.get("title")

            else:
                annotation_type = getattr(
                    annotation,
                    "type",
                    None,
                )

                citation_url = getattr(
                    annotation,
                    "url",
                    None,
                )

                citation_title = getattr(
                    annotation,
                    "title",
                    None,
                )

            if annotation_type != "url_citation":
                return

            if not citation_url:
                return

            citation = {
                "title": citation_title or citation_url,
                "url": citation_url,
            }

            if not any(
                item.get("url") == citation_url
                for item in citations
            ):
                citations.append(citation)

        except Exception as exc:
            safe_print(
                f"解析 Bing 引用时出现警告：{exc}"
            )

    def walk(node):
        """
        递归遍历 Azure SDK 返回对象。
        """
        if node is None:
            return

        node_id = id(node)

        if node_id in visited:
            return

        visited.add(node_id)

        # 处理字典
        if isinstance(node, dict):
            if node.get("type") == "url_citation":
                add_citation(node)

            for value in node.values():
                walk(value)

            return

        # 处理列表、元组
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

            return

        # 处理 Azure SDK 对象
        object_type = getattr(
            node,
            "type",
            None,
        )

        if object_type == "url_citation":
            add_citation(node)

        # 只遍历可能包含引用的字段，
        # 避免遍历 SDK 对象的全部内部属性。
        possible_fields = [
            "item",
            "response",
            "output",
            "content",
            "annotations",
        ]

        for field_name in possible_fields:
            try:
                value = getattr(
                    node,
                    field_name,
                    None,
                )

                if value is not None:
                    walk(value)

            except Exception:
                continue

    try:
        walk(obj)

    except Exception as exc:
        safe_print(
            f"提取 Bing 参考来源时出现警告：{exc}"
        )

def get_bing_connection_id(
    project_client: AIProjectClient,
) -> str:
    """
    获取 Bing Grounding 项目连接 ID。

    优先使用：
        PROJECT_CONNECTION_ID

    如果没有配置，则使用：
        BING_CONNECTION_NAME

    默认连接名称为：
        Search
    """

    configured_connection_id = os.getenv(
        "PROJECT_CONNECTION_ID"
    )

    if configured_connection_id:
        safe_print(
            "使用环境变量 PROJECT_CONNECTION_ID 作为 Bing 连接："
            f"{configured_connection_id}"
        )

        return configured_connection_id

    connection_name = os.getenv(
        "BING_CONNECTION_NAME",
        "Search",
    )

    try:
        bing_connection = project_client.connections.get(
            connection_name
        )
    except Exception as exc:
        raise RuntimeError(
            f"无法获取项目连接 {connection_name!r}。"
            "请确认 Azure AI Foundry 项目中存在该连接，"
            f"或者配置 PROJECT_CONNECTION_ID。原始错误：{exc}"
        ) from exc

    bing_connection_id = getattr(
        bing_connection,
        "id",
        None,
    )

    if not bing_connection_id:
        raise RuntimeError(
            f"连接 {connection_name!r} 没有返回有效的 id："
            f"{bing_connection}"
        )

    safe_print(
        f"已通过连接名称获取 Bing 连接："
        f"{connection_name} -> {bing_connection_id}"
    )

    return bing_connection_id


# =========================================================
# 创建 Azure Bing Grounding LangChain 工具
# =========================================================

def create_bing_grounding_tool():
    """
    创建一个 LangChain Bing 搜索工具。

    工具内部使用：

        Azure AI Foundry Prompt Agent
        + BingGroundingTool
        + Azure Responses API

    工具返回：

        搜索答案
        参考来源 URL
    """

    project_endpoint = os.getenv(
        "AZURE_AI_PROJECT_ENDPOINT"
    )

    azure_agent_model = os.getenv(
        "AZURE_AI_AGENT_MODEL"
    )

    if not project_endpoint:
        raise RuntimeError(
            "未配置 AZURE_AI_PROJECT_ENDPOINT，"
            "请检查 config.env。"
        )

    if not azure_agent_model:
        raise RuntimeError(
            "未配置 AZURE_AI_AGENT_MODEL，"
            "请检查 config.env。"
        )

    safe_print(
        f"Azure Bing Grounding Agent 模型："
        f"{azure_agent_model}"
    )

    # -----------------------------------------------------
    # 创建 Azure AI Project Client
    # -----------------------------------------------------

    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(),
    )

    # -----------------------------------------------------
    # 获取 Azure Responses API 客户端
    # -----------------------------------------------------

    openai_client = project_client.get_openai_client()

    # -----------------------------------------------------
    # 获取 Bing Grounding 连接
    # -----------------------------------------------------

    bing_connection_id = get_bing_connection_id(
        project_client
    )

    # -----------------------------------------------------
    # 创建 Bing Grounding Tool
    # -----------------------------------------------------

    bing_tool = BingGroundingTool(
        bing_grounding=BingGroundingSearchToolParameters(
            search_configurations=[
                BingGroundingSearchConfiguration(
                    project_connection_id=bing_connection_id
                )
            ]
        )
    )

    # -----------------------------------------------------
    # 创建 Azure AI Foundry Prompt Agent
    # -----------------------------------------------------

    agent_name = (
        "bing-grounding-search-"
        f"{uuid.uuid4().hex[:8]}"
    )

    agent_definition = PromptAgentDefinition(
        model=azure_agent_model,

        instructions="""
你是一名支持中文的联网搜索助手。

请遵循以下要求：

1. 用户可以使用中文提问。
2. 对于天气、新闻、日期、价格、股票、体育、旅游、实时信息、最新信息以及用户明确要求搜索的问题，必须使用 Bing Grounding。
3. 必要时，可以将中文问题转换为中文、英文或中英文组合搜索查询。
4. 搜索完成后，必须使用中文回答。
5. 必须优先依据 Bing Grounding 返回的搜索结果回答。
6. 不要凭空编造搜索结果中不存在的信息。
7. 如果搜索结果包含网页来源，应在回答中说明相关来源。
8. 如果搜索结果不足以回答问题，应明确说明信息不足。
""",

        tools=[
            bing_tool
        ],
    )

    bing_agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=agent_definition,
        description=(
            "支持中文交互并返回参考来源的 "
            "Azure Bing Grounding 搜索 Agent"
        ),
    )

    safe_print(
        "✅ Azure Bing Grounding Agent 创建成功"
    )

    safe_print(
        f"   Agent ID: {bing_agent.id}"
    )

    safe_print(
        f"   Agent Name: {bing_agent.name}"
    )

    safe_print(
        f"   Agent Version: {bing_agent.version}"
    )

# =========================================================
# 创建  LangChain Agent 工具
# =========================================================

def create_langchain_agent():
        """
        创建 LangChain Agent。

        搜索工具始终使用统一的 web_search。
        Azure Bing 不可用时自动回退到 Bocha 或 SerpAPI。
        """

        deepseek_api_key = os.getenv(
            "DEEPSEEK_API_KEY"
        )

        if not deepseek_api_key:
            raise RuntimeError(
                "未检测到 DEEPSEEK_API_KEY，"
                "请检查 config.env。"
            )

        # 创建统一搜索工具
        web_search_tool = create_unified_search_tool()

        tools = [
            get_current_time,
            calculate,
            web_search_tool,
        ]

        enabled_engines = []

        if (
            os.getenv("AZURE_AI_PROJECT_ENDPOINT")
            and os.getenv("AZURE_AI_AGENT_MODEL")
        ):
            enabled_engines.append(
                "Azure Bing Grounding"
            )

        if os.getenv("BOCHA_API_KEY"):
            enabled_engines.append("Bocha")

        if os.getenv("SERPAPI_API_KEY"):
            enabled_engines.append("SerpAPI")

        safe_print(
            "✅ 可用搜索引擎："
            + "、".join(enabled_engines)
        )

        model = ChatOpenAI(
            model=os.getenv(
                "DEEPSEEK_MODEL",
                "deepseek-chat",
            ),
            api_key=deepseek_api_key,
            base_url=os.getenv(
                "DEEPSEEK_BASE_URL",
                "https://api.deepseek.com",
            ),
            temperature=0.3,
            timeout=60,
            max_retries=2,
        )

        agent = create_agent(
            model=model,
            tools=tools,
            system_prompt="""
    你是一个支持中文的智能助手。

    请严格遵循以下规则：

    1. 用户使用中文提问时，必须使用中文回答。
    2. 以下问题必须调用 web_search：
       - 新闻
       - 天气
       - 股票
       - 体育
       - 当前价格
       - 旅游信息
       - 最新信息
       - 实时信息
       - 网页资料
       - 官方文档
       - 用户明确要求搜索的问题
    3. 不要使用模型记忆直接回答实时问题。
    4. 对需要联网的信息，必须先调用 web_search。
    5. 搜索后优先依据搜索结果回答。
    6. 不要编造搜索结果中不存在的信息。
    7. 如果搜索结果不足，应明确告诉用户信息不足。
    8. 如果搜索结果包含链接，应在最终回答中保留参考来源。
    9. 数学问题可以调用 calculate。
    10. 当前日期和时间问题可以调用 get_current_time。
    """,
        )

        return agent


    # -----------------------------------------------------
    # 定义 LangChain 工具
    # -----------------------------------------------------

@tool
def bing_grounding_search(query: str) -> str:
        """
        使用 Azure AI Foundry Bing Grounding 搜索互联网。

        适用于：

        - 实时新闻
        - 当前日期
        - 当前天气
        - 当前价格
        - 股票和体育信息
        - 旅游信息
        - 产品资料
        - 官方文档
        - 最新事件
        - 需要网页来源验证的问题

        返回内容包含搜索答案和参考来源。
        """

        if not query or not query.strip():
            return "搜索关键词不能为空。"

        query = query.strip()

        prompt = f"""
请使用 Bing Grounding 搜索下面的问题，并用中文回答。

要求：

1. 必须使用 Bing Grounding。
2. 对于实时信息，必须以本次搜索结果为准。
3. 必要时可以使用中文、英文或中英文组合关键词搜索。
4. 回答必须使用中文。
5. 不要编造搜索结果中没有的信息。
6. 在回答末尾列出相关参考来源。
7. 如果没有找到可靠结果，请明确说明。

用户问题：

{query}
"""

        answer_parts = []
        citations = []

        try:
            # -------------------------------------------------
            # 调用 Azure Responses API
            # -------------------------------------------------

            stream_response = openai_client.responses.create(
                stream=True,

                # 与可以正常工作的代码保持一致：
                # 强制调用 Bing Grounding
                tool_choice="required",

                input=prompt,

                extra_body={
                    "agent_reference": {
                        "name": bing_agent.name,
                        "type": "agent_reference",
                    }
                },
            )

            # -------------------------------------------------
            # 处理流式事件
            # -------------------------------------------------

            for event in stream_response:
                event_type = getattr(
                    event,
                    "type",
                    None,
                )

                # 每个事件都尝试提取引用
                extract_citations_from_object(
                    event,
                    citations,
                )

                # 文本增量
                if event_type == "response.output_text.delta":
                    delta = getattr(
                        event,
                        "delta",
                        None,
                    )

                    if delta:
                        answer_parts.append(delta)

                # 响应完成
                elif event_type == "response.completed":
                    response = getattr(
                        event,
                        "response",
                        None,
                    )

                    if response is not None:
                        full_output_text = getattr(
                            response,
                            "output_text",
                            None,
                        )

                        if (
                            full_output_text
                            and not answer_parts
                        ):
                            answer_parts.append(
                                full_output_text
                            )

                        extract_citations_from_object(
                            response,
                            citations,
                        )

            # -------------------------------------------------
            # 组装搜索答案
            # -------------------------------------------------

            answer = "".join(answer_parts).strip()

            if not answer:
                answer = "Bing 没有返回可用的文字答案。"

            # -------------------------------------------------
            # 追加参考来源
            # -------------------------------------------------

            if citations:
                source_lines = [
                    "\n参考来源："
                ]

                for index, citation in enumerate(
                    citations,
                    start=1,
                ):
                    title = citation.get(
                        "title",
                        "网页来源",
                    )

                    url = citation.get(
                        "url",
                        "",
                    )

                    source_lines.append(
                        f"{index}. {title}\n"
                        f"   {url}"
                    )

                answer = (
                    f"{answer}\n"
                    + "\n".join(source_lines)
                )

            else:
                answer = (
                    f"{answer}\n\n"
                    "参考来源：本次响应未提取到 URL 引用。"
                )

            return answer

        except Exception as exc:
            safe_print(
                f"Azure Bing Grounding 搜索失败：{exc}"
            )

            return (
                "Azure Bing Grounding 搜索失败。"
                f"错误信息：{exc}"
            )

        return bing_grounding_search



def create_unified_search_tool():
    """
    创建统一搜索工具。

    优先使用 Azure Bing Grounding。
    如果 Azure Bing 不可用，则自动使用 Bocha 或 SerpAPI。
    """

    bing_search_tool = None

    # Azure Bing 是可选功能，初始化失败不能阻止程序启动
    try:
        if (
            os.getenv("AZURE_AI_PROJECT_ENDPOINT")
            and os.getenv("AZURE_AI_AGENT_MODEL")
        ):
            bing_search_tool = create_bing_grounding_tool()

            safe_print(
                "✅ Azure Bing Grounding 搜索已启用"
            )

    except Exception as exc:
        safe_print(
            "⚠️ Azure Bing Grounding 初始化失败，"
            "将使用备用搜索引擎："
            f"{exc}"
        )

    has_bocha = bool(
        os.getenv("BOCHA_API_KEY")
    )

    has_serpapi = bool(
        os.getenv("SERPAPI_API_KEY")
    )

    if not bing_search_tool and not has_bocha and not has_serpapi:
        raise RuntimeError(
            "没有可用的搜索引擎。\n"
            "请至少配置以下一种搜索服务：\n"
            "1. Azure Bing Grounding：\n"
            "   AZURE_AI_PROJECT_ENDPOINT\n"
            "   AZURE_AI_AGENT_MODEL\n"
            "   PROJECT_CONNECTION_ID 或 BING_CONNECTION_NAME\n"
            "2. Bocha：BOCHA_API_KEY\n"
            "3. SerpAPI：SERPAPI_API_KEY"
        )

    @tool
    def web_search(query: str) -> str:
        """
        搜索互联网并返回搜索结果。

        适用于：

        - 新闻
        - 天气
        - 股票
        - 体育
        - 价格
        - 旅游
        - 产品信息
        - 官方文档
        - 最新事件
        - 用户明确要求联网搜索的问题
        """

        if not query or not query.strip():
            return "搜索关键词不能为空。"

        query = query.strip()

        # -------------------------------------------------
        # 优先使用 Azure Bing Grounding
        # -------------------------------------------------

        if bing_search_tool is not None:
            try:
                result = bing_search_tool.invoke(
                    {
                        "query": query
                    }
                )

                result = str(result).strip()

                # Bing 返回正常结果
                if (
                    result
                    and not result.startswith(
                        "Azure Bing Grounding 搜索失败"
                    )
                    and not result.startswith(
                        "Bing 没有返回可用的文字答案"
                    )
                ):
                    return result

                safe_print(
                    "⚠️ Azure Bing 未返回有效结果，"
                    "开始使用备用搜索。"
                )

            except Exception as exc:
                safe_print(
                    "⚠️ Azure Bing 调用失败，"
                    f"开始使用备用搜索：{exc}"
                )

        # -------------------------------------------------
        # 使用 Bocha / SerpAPI 备用搜索
        # -------------------------------------------------

        return multi_web_search.invoke(
            {
                "query": query
            }
        )

    return web_search
# =========================================================
# 综合备用搜索工具
# =========================================================

@tool
def multi_web_search(query: str) -> str:
    """
    使用 SerpAPI 和 Bocha 进行备用搜索。

    搜索顺序：

    1. Bocha
    2. SerpAPI

    如果第一个搜索引擎失败，则自动尝试下一个。
    """

    if not query or not query.strip():
        return "搜索关键词不能为空。"

    query = query.strip()

    engines = []

    # 中文搜索优先使用 Bocha
    if os.getenv("BOCHA_API_KEY"):
        engines.append(
            ("Bocha", search_bocha)
        )

    if os.getenv("SERPAPI_API_KEY"):
        engines.append(
            ("SerpAPI", search_serpapi)
        )

    if not engines:
        return (
            "未配置备用搜索引擎。\n"
            "请至少配置以下一个环境变量：\n"
            "- BOCHA_API_KEY\n"
            "- SERPAPI_API_KEY"
        )

    errors = []

    for engine_name, search_function in engines:
        try:
            result = search_function(query)

            if result is None:
                errors.append(
                    f"{engine_name}: 未配置或未返回结果"
                )
                continue

            result = str(result).strip()

            # 这些内容代表搜索失败
            if (
                not result
                or result.startswith("[")
                or result == "未找到相关结果。"
            ):
                errors.append(
                    f"{engine_name}: {result or '无结果'}"
                )
                continue

            return (
                f"【{engine_name} 搜索结果】\n\n"
                f"{result}"
            )

        except Exception as exc:
            errors.append(
                f"{engine_name}: {exc}"
            )

    return (
        "所有备用搜索引擎均未返回有效结果。\n"
        + "\n".join(errors)
    )




def run_langchain_agent(agent, user_question: str):
    """
    调用 LangChain Agent。
    """

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": user_question,
                }
            ]
        }
    )

    messages = result.get(
        "messages",
        [],
    )

    if not messages:
        return "没有返回结果。"

    # 从后往前寻找最终 AI 消息
    final_message = None

    for message in reversed(messages):
        message_type = getattr(
            message,
            "type",
            None,
        )

        if message_type == "ai":
            final_message = message
            break

    if final_message is None:
        final_message = messages[-1]

    content = getattr(
        final_message,
        "content",
        None,
    )

    if isinstance(content, list):
        text_parts = []

        for item in content:
            if isinstance(item, dict):
                text = (
                    item.get("text")
                    or item.get("content")
                    or ""
                )

                if text:
                    text_parts.append(str(text))

            else:
                text_parts.append(str(item))

        content = "\n".join(text_parts)

    if content is None:
        content = str(final_message)

    content = str(content).strip()

    safe_print("\n助手：")
    safe_print(content)

    return content


# =========================================================
# 主程序
# =========================================================

def main():
    # 确保标准输出可用
    if sys.stdout is None or sys.stdout.closed:
        sys.stdout = sys.__stdout__

    load_dotenv("config.env")

    try:

        agent = create_langchain_agent()

        safe_print("")
        safe_print("=" * 60)
        safe_print("中文 Bing Grounding 搜索助手已启动")
        safe_print("输入 quit、exit、q 或 退出结束程序")
        safe_print("=" * 60)

        

        

        while True:
            try:
                user_question = input(
                    "\n请输入问题："
                ).strip()

            except KeyboardInterrupt:
                safe_print("\n程序已退出。")
                break

            except EOFError:
                safe_print("\n程序已退出。")
                break

            if not user_question:
                safe_print("请输入有效的问题。")
                continue

            if user_question.lower() in {
                "quit",
                "exit",
                "q",
                "退出",
                "结束",
            }:
                safe_print("程序已退出。")
                break

            try:
                run_langchain_agent(
                    agent,
                    user_question,
                )

            except Exception as exc:
                safe_print(
                    f"LangChain Agent 执行失败：{exc}"
                )

    except Exception as exc:
        safe_print(
            f"程序启动失败：{exc}"
        )


# =========================================================
# 程序入口
# =========================================================

if __name__ == "__main__":
    main()

