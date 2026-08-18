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

    # 检查是否至少配置了一个搜索引擎
    if os.getenv("SERPAPI_API_KEY") or os.getenv("BOCHA_API_KEY"):
        tools.append(multi_web_search)
        enabled = []
        if os.getenv("SERPAPI_API_KEY"): enabled.append("SerpAPI")
        if os.getenv("BOCHA_API_KEY"): enabled.append("Bocha")
        safe_print(f"✅ 多引擎搜索已启用（后备引擎：{', '.join(enabled)}）")
    else:
        safe_print("⚠️ 未检测到任何搜索引擎 API 密钥（SERPAPI_API_KEY / BOCHA_API_KEY），搜索功能不可用。")

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="你是一个智能助手，请用中文回答用户的问题。",
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
