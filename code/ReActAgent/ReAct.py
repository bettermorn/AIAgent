import os
import sys
import uuid
import requests
import json
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_community.utilities import SerpAPIWrapper



from azure.ai.projects import AIProjectClient

from azure.identity import DefaultAzureCredential



from azure.ai.projects.models import (
    PromptAgentDefinition,
    BingGroundingTool,
    BingGroundingSearchToolParameters,
    BingGroundingSearchConfiguration,
)



# ----- 安全打印函数 -----
def safe_print(*args, **kwargs):
    if sys.stdout is None or sys.stdout.closed:
        try:
            sys.stdout = sys.__stdout__
        except Exception:
            kwargs['file'] = sys.stderr
    try:
        print(*args, **kwargs)
    except ValueError:
        try:
            print(*args, **kwargs, file=sys.stderr)
        except Exception:
            pass

# ----- 工具定义 -----
@tool
def get_current_time() -> str:
    """返回当前的日期和时间（格式：YYYY-MM-DD HH:MM:SS）。"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@tool
def calculate(expression: str) -> str:
    """
    安全地计算数学表达式，支持 +、-、*、/、** (幂) 和括号。
    输入示例："2 + 3 * 4" 或 "(10+5)/3"。
    """
    try:
        allowed = {"abs": abs, "round": round}
        result = eval(expression, {"__builtins__": None}, allowed)
        return f"计算结果: {result}"
    except Exception as e:
        return f"计算错误: {str(e)}"

def search_serpapi(query: str) -> str:
    """使用 SerpAPI 进行搜索（内部函数）"""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        return None  # 无密钥则跳过
    try:
        wrapper = SerpAPIWrapper(serpapi_api_key=api_key, timeout=10)
        result = wrapper.run(query)
        return result
    except Exception as e:
        error_msg = str(e).lower()
        if "timeout" in error_msg:
            return f"[SerpAPI 超时]"
        elif "403" in error_msg or "unauthorized" in error_msg:
            return f"[SerpAPI 密钥无效]"
        else:
            return f"[SerpAPI 错误: {e}]"

def search_bocha(query: str) -> str:
    """使用 Bocha Search 进行搜索（内部函数）"""
    api_key = os.getenv("BOCHA_API_KEY")
    if not api_key:
        return None
    url = "https://api.bocha.cn/v1/web-search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "freshness": "noLimit",   # 不限制时间
        "topK": 5                 # 返回前5条结果
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        # 提取结果文本
        web_pages = data.get("webPages", [])
        if not web_pages:
            return "未找到相关结果。"
        # 拼接成可读文本
        results = []
        for i, page in enumerate(web_pages[:5], 1):
            title = page.get("name", "无标题")
            snippet = page.get("snippet", "")
            url = page.get("url", "")
            results.append(f"{i}. {title}\n   摘要：{snippet}\n   链接：{url}")
        return "\n\n".join(results)
    except requests.exceptions.Timeout:
        return "[Bocha 超时]"
    except requests.exceptions.RequestException as e:
        return f"[Bocha 网络错误: {e}]"
    except Exception as e:
        return f"[Bocha 错误: {e}]"


def extract_azure_agent_text(message) -> str:
    """
    从 Azure AI Agent 消息中提取文本内容。
    Azure SDK 返回的 message.content 通常是一个列表。
    """
    texts = []

    try:
        contents = getattr(message, "content", None) or []

        for content_item in contents:
            content_type = getattr(content_item, "type", None)

            if content_type == "text":
                text_obj = getattr(content_item, "text", None)
                if text_obj is not None:
                    value = getattr(text_obj, "value", None)
                    if value:
                        texts.append(value)

            # 兼容某些 SDK 版本的结构
            elif hasattr(content_item, "text"):
                text_obj = content_item.text

                if isinstance(text_obj, str):
                    texts.append(text_obj)
                else:
                    value = getattr(text_obj, "value", None)
                    if value:
                        texts.append(value)

        if texts:
            return "\n".join(texts)

    except Exception:
        pass

    # 某些版本可能直接返回字符串
    if isinstance(getattr(message, "content", None), str):
        return message.content

    return ""


def create_bing_grounding_tool():
    """
    创建一个 LangChain 工具。
    
    该工具内部调用 Azure AI Foundry Agent，
    由 Azure Agent 使用 BingGroundingTool 进行搜索。
    """
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    
    project_connection_id = os.getenv("PROJECT_CONNECTION_ID")
    
    azure_agent_model = os.getenv("AZURE_AI_AGENT_MODEL")
    print("model:"+azure_agent_model)

    if not project_endpoint:
        raise RuntimeError(
            "未配置 AZURE_AI_PROJECT_ENDPOINT，请检查 config.env。"
        )

    if not project_connection_id:
        raise RuntimeError(
            "未配置 PROJECT_CONNECTION_ID，请检查 config.env。"
        )

    if not azure_agent_model:
        raise RuntimeError(
            "未配置 AZURE_AI_AGENT_MODEL，请检查 config.env。"
        )

    # 使用 Azure 默认凭据进行身份认证
    credential = DefaultAzureCredential()

    # 创建 Azure AI Project Client
    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
    )


    # 从项目连接中获取 Bing 连接

    # connections = project_client.connections.list()

    # bing_connection = None

    # for connection in connections:
    # # 根据实际 SDK 返回字段调整判断逻辑
    #     if "bing" in str(connection).lower():
    #         bing_connection = connection
    #     break

    # if bing_connection is None:
    #     raise RuntimeError("未找到项目中的 Bing Grounding 连接")



    # bing_connection_id = getattr(
    #     bing_connection,
    #     "id",
    #     getattr(bing_connection, "connection_id", None)
    # )

    # if not bing_connection_id:
    #     raise RuntimeError(f"无法从连接对象中获取连接 ID：{bing_connection}")

    # print(bing_connection_id)    

   
    bing_tool = BingGroundingTool(
                    bing_grounding=BingGroundingSearchToolParameters(
                        search_configurations=[
                            BingGroundingSearchConfiguration(
                                project_connection_id=project_connection_id
                            )
                        ]
                    )
                )



    # 在 Azure AI Foundry 中创建一个专门用于 Bing 搜索的 Agent
    agent_definition = PromptAgentDefinition(
        model=azure_agent_model,
        instructions=(
        "你是一个专业的联网搜索助手。"
        "当用户提出问题时，必须优先使用 Bing Grounding 搜索实时信息。"
        "请基于搜索结果回答，不要凭空编造。"
        "尽量返回关键事实、来源和链接。"
        ),
        tools=[bing_tool],
    )

    bing_agent = project_client.agents.create_version(
        agent_name="bing-grounding-search-agent",
        definition=agent_definition,
        description="You are a helpful agent.",
    )

    safe_print(
        f"✅ Bing Grounding Agent 已创建，agent_id={bing_agent.id}"
    )

    @tool
    def bing_grounding_search(query: str) -> str:
        """
        使用 Azure AI Foundry 的 Bing Grounding 进行联网搜索。
        
        适用于实时新闻、网页信息、产品资料、官方文档、
        当前价格、天气、人物信息等需要联网查询的问题。
        """
        if not query or not query.strip():
            return "搜索关键词不能为空。"

        thread = None

        try:
            # 为每次查询创建一个新的线程
            thread = project_client.agents.threads.create()

            # 写入用户问题
            project_client.agents.messages.create(
                thread_id=thread.id,
                role="user",
                content=query.strip(),
            )

            # 执行 Azure Agent
            run = project_client.agents.runs.create_and_process(
                thread_id=thread.id,
                agent_id=bing_agent.id,
            )

            # 检查执行状态
            if getattr(run, "status", None) != "completed":
                last_error = getattr(run, "last_error", None)
                return (
                    "Bing Grounding 搜索执行失败。"
                    f"状态：{getattr(run, 'status', 'unknown')}；"
                    f"错误：{last_error}"
                )

            # 获取 Azure Agent 返回的消息
            messages = project_client.agents.messages.list(
                thread_id=thread.id
            )

            # 通常 list 返回的是最新消息在前
            for message in messages:
                if getattr(message, "role", None) == "assistant":
                    answer = extract_azure_agent_text(message)

                    if answer:
                        return f"【Bing Grounding 搜索结果】\n{answer}"

            return "Bing Grounding 没有返回有效的搜索结果。"

        except Exception as e:
            return f"[Bing Grounding 错误: {e}]"

    return bing_grounding_search






@tool
def multi_web_search(query: str) -> str:
    """
    综合搜索工具，自动尝试多个搜索引擎（SerpAPI、Bocha Search）以获取实时信息。
    会按顺序尝试，返回第一个成功的结果；若全部失败，返回错误说明。
    """
    # 获取所有可用的搜索引擎函数
    engines = []
    if os.getenv("SERPAPI_API_KEY"):
        engines.append(("SerpAPI", search_serpapi))
    if os.getenv("BOCHA_API_KEY"):
        engines.append(("Bocha", search_bocha))
    
    if not engines:
        return "错误：未配置任何有效的搜索引擎 API 密钥，请检查 SERPAPI_API_KEY 或 BOCHA_API_KEY。"
    
    errors = []
    for name, func in engines:
        result = func(query)
        if result is None:
            continue  # 该引擎未配置，跳过
        # 检查是否是错误信息（以 [ 开头表示错误）
        if result.startswith("["):
            errors.append(f"{name}: {result[1:-1]}")  # 去掉方括号
            continue
        # 成功返回结果
        return f"【{name} 搜索结果】\n{result}"
    
    # 所有引擎都失败了
    error_summary = "; ".join(errors)
    return f"所有搜索引擎均无法返回有效结果：{error_summary}。请稍后再试。"

def main():
    # 确保 stdout 可用
    if sys.stdout is None or sys.stdout.closed:
        sys.stdout = sys.__stdout__

    load_dotenv("config.env")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_api_key:
        raise RuntimeError("未检测到 DEEPSEEK_API_KEY，请检查 config.env。")

    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=deepseek_api_key,
        base_url="https://api.deepseek.com",
        temperature=0.5,
    )

    tools = [get_current_time, calculate]

    # -----------------------------
    # 启用 Azure Bing Grounding
    # -----------------------------
    bing_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    project_connection_id = os.getenv("PROJECT_CONNECTION_ID")
    azure_agent_model = os.getenv("AZURE_AI_AGENT_MODEL")

    if bing_endpoint and project_connection_id and azure_agent_model:
        try:
            bing_grounding_search = create_bing_grounding_tool()
            tools.append(bing_grounding_search)

            safe_print("✅ Azure Bing Grounding 搜索已启用")

        except Exception as e:
            safe_print(f"⚠️ Azure Bing Grounding 初始化失败：{e}")
    else:
        safe_print(
            "⚠️ 未配置完整的 Azure Bing Grounding 环境变量，"
            "需要 AZURE_AI_PROJECT_ENDPOINT、"
            "PROJECT_CONNECTION_ID、"
            "AZURE_AI_AGENT_MODEL"
        )

    # -----------------------------
    # 启用 SerpAPI / Bocha 搜索
    # -----------------------------
    if os.getenv("SERPAPI_API_KEY") or os.getenv("BOCHA_API_KEY"):
        tools.append(multi_web_search)

        enabled = []

        if os.getenv("SERPAPI_API_KEY"):
            enabled.append("SerpAPI")

        if os.getenv("BOCHA_API_KEY"):
            enabled.append("Bocha")

        safe_print(
            f"✅ 多引擎搜索已启用（后备引擎：{', '.join(enabled)}）"
        )
    else:
        safe_print(
            "⚠️ 未检测到 SERPAPI_API_KEY / BOCHA_API_KEY，"
            "SerpAPI 和 Bocha 搜索不可用。"
        )
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=(
        "你是一个智能助手，请用中文回答用户的问题。"
        "如果用户询问实时信息、新闻、当前价格、近期事件、"
        "网页资料、官方文档或其他需要联网验证的问题，"
        "请优先调用 bing_grounding_search 工具。"
        "如果 Bing Grounding 不可用，再尝试其他搜索工具。"
        "回答联网搜索问题时，请尽量保留来源和链接。"
        ),
    )

    safe_print("\n🤖 智能助手已启动（输入 quit/exit 退出）:\n")
    while True:
        try:
            user_input = input("您的问题: ").strip()
            if user_input.lower() in ("quit", "exit", "q"):
                safe_print("👋 再见！")
                break
            if not user_input:
                safe_print("⚠️ 输入不能为空。")
                continue

            result = agent.invoke({"messages": [("user", user_input)]})
            final_msg = result["messages"][-1].content
            safe_print("\n✅ 最终回答:\n", final_msg, "\n")
            safe_print("-" * 60)

        except KeyboardInterrupt:
            safe_print("\n👋 退出程序。")
            break
        except Exception as e:
            safe_print(f"❌ 错误: {e}\n")

if __name__ == "__main__":
    main()
