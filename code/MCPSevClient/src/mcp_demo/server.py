from __future__ import annotations

import os
import re
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx
from mcp.server.fastmcp import FastMCP

# ---- 启动时加载项目根目录 config.env（真实搜索 Key 等配置） ----
try:
    from dotenv import load_dotenv
    _ROOT = Path(__file__).resolve().parents[2]
    load_dotenv(_ROOT / "config.env")
except Exception as e:  # noqa: BLE001
    print(f"⚠️ 加载 config.env 失败（不影响启动）: {e}", file=sys.stderr)

# ---- 配置文件访问的安全基础目录 ----
print("📂 [初始化] 配置文件访问基础目录...", file=sys.stderr)
BASE_DIR = Path(__file__).resolve().parent.parent.parent / "sample_data"
BASE_DIR.mkdir(parents=True, exist_ok=True)
print(f"   ✓ 基础目录: {BASE_DIR}", file=sys.stderr)

SAMPLE_FILE = BASE_DIR / "hello.txt"
if not SAMPLE_FILE.exists():
    print("   ✓ 创建示例文件 hello.txt", file=sys.stderr)
    SAMPLE_FILE.write_text("你好！这是通过 MCP read_file 工具读取的 sample_data/hello.txt 文件内容。\n", encoding="utf-8")
else:
    print("   ✓ 示例文件 hello.txt 已存在", file=sys.stderr)

print("🚀 [初始化] 创建 FastMCP 服务器实例...", file=sys.stderr)
mcp = FastMCP("mcp-demo")
print("   ✓ 服务器实例创建成功", file=sys.stderr)

# ---------- 工具 ----------

@mcp.tool()
def add(a: float, b: float) -> float:
    """将两个数字相加并返回结果。"""
    print(f"🔢 [工具调用] add(a={a}, b={b})", file=sys.stderr)
    result = a + b
    print(f"   ✓ 计算结果: {result}", file=sys.stderr)
    return result

# ---------- 真实搜索 ----------
# 双引擎支持：博查 Bocha（中文搜索推荐）+ SerpAPI（百度/Google/Bing 等）
# Key 来源：环境变量或项目根目录 config.env
BOCHA_API_URL = "https://api.bochaai.com/v1/web-search"
SERPAPI_URL = "https://serpapi.com/search"
SERPAPI_ENGINES = {"baidu", "google", "bing", "duckduckgo"}

# 演示数据：当没有配置任何 API Key 时使用
DEMO_SEARCH_RESULTS = {
    "python mcp": [
        {
            "title": "Model Context Protocol (MCP) - 官方文档",
            "snippet": "MCP 是一个开放协议，用于在 AI 应用和外部工具/数据源之间实现无缝集成。通过标准化的接口，让 AI 模型可以安全地访问本地和远程资源。",
            "url": "https://modelcontextprotocol.io"
        },
        {
            "title": "Python SDK for MCP - GitHub",
            "snippet": "官方 Python SDK，提供了构建 MCP 服务器和客户端的完整功能。包含 FastMCP 快速开发工具，让你用几行代码就能创建 MCP 服务器。",
            "url": "https://github.com/modelcontextprotocol/python-sdk"
        },
        {
            "title": "MCP 快速入门教程",
            "snippet": "学习如何使用 Python 构建 MCP 服务器，暴露工具和资源给 AI 应用使用。包含完整的代码示例和最佳实践。",
            "url": "https://modelcontextprotocol.io/quickstart"
        }
    ],
    "default": [
        {
            "title": "搜索演示结果",
            "snippet": "这是一个演示结果。要使用真实搜索，请在 config.env 中设置 BOCHA_API_KEY（博查，推荐中文搜索）或 SERPAPI_API_KEY（SerpAPI，支持百度/Google/Bing）。",
            "url": "https://open.bochaai.com"
        }
    ]
}


def _search_bocha(query: str, count: int = 5) -> List[Dict[str, str]]:
    """使用博查（Bocha）Web Search API 执行真实搜索。"""
    api_key = os.getenv("BOCHA_API_KEY")
    if not api_key:
        raise ValueError("未配置 BOCHA_API_KEY")

    payload = {"query": query, "summary": True, "count": count}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=15.0) as client:
        r = client.post(BOCHA_API_URL, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()

    pages = (data.get("data") or {}).get("webPages") or {}
    results = []
    for item in (pages.get("value") or [])[:count]:
        results.append({
            "title": item.get("name", ""),
            "snippet": item.get("summary") or item.get("snippet", ""),
            "url": item.get("url", ""),
        })
    if not results:
        raise ValueError("博查搜索未返回结果")
    return results


def _search_serpapi(query: str, engine: str = "baidu", count: int = 5) -> List[Dict[str, str]]:
    """使用 SerpAPI 执行真实搜索（支持 baidu / google / bing / duckduckgo）。"""
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        raise ValueError("未配置 SERPAPI_API_KEY")

    params = {
        "q": query,
        "engine": engine if engine in SERPAPI_ENGINES else "baidu",
        "api_key": api_key,
        "num": count,
    }

    with httpx.Client(timeout=15.0, headers={"User-Agent": "mcp-demo/0.1"}) as client:
        r = client.get(SERPAPI_URL, params=params)
        r.raise_for_status()
        data = r.json()

    # SerpAPI 各引擎的 organic_results 结构一致
    results = []
    for item in data.get("organic_results", [])[:count]:
        results.append({
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "url": item.get("link", ""),
        })
    if not results:
        raise ValueError(f"SerpAPI（{engine}）搜索未返回结果")
    return results


@mcp.tool()
def search_http(query: str, engine: str = "auto") -> List[Dict[str, str]]:
    """
    执行网络搜索并返回真实搜索结果（标题 / 摘要 / 链接）。

    引擎选择（engine 参数）：
    - "auto"（默认）: 自动选择已配置的搜索源，优先博查 BOCHA，其次 SerpAPI
    - "bocha": 强制使用博查搜索（中文搜索效果好，需 BOCHA_API_KEY）
    - "baidu" / "google" / "bing" / "duckduckgo": 使用 SerpAPI 对应引擎（需 SERPAPI_API_KEY）

    首选引擎失败或未配置 Key 时自动切换到另一个搜索源；
    两个 Key 都未配置时返回演示结果。
    """
    print(f"🔍 [工具调用] search_http(query='{query}', engine='{engine}')", file=sys.stderr)

    bocha_key = bool(os.getenv("BOCHA_API_KEY"))
    serpapi_key = bool(os.getenv("SERPAPI_API_KEY"))

    # 根据参数与 Key 配置决定尝试顺序
    if engine == "bocha":
        providers = [("bocha", _search_bocha)]
        if serpapi_key:
            providers.append(("serpapi", _search_serpapi))
    elif engine in SERPAPI_ENGINES:
        providers = [("serpapi", lambda q: _search_serpapi(q, engine))]
        if bocha_key:
            providers.append(("bocha", _search_bocha))
    else:  # auto：优先博查（中文场景），其次 SerpAPI
        providers = []
        if bocha_key:
            providers.append(("bocha", _search_bocha))
        if serpapi_key:
            providers.append(("serpapi", lambda q: _search_serpapi(q, "baidu")))

    if not providers:
        print("   → 未配置 BOCHA_API_KEY / SERPAPI_API_KEY，使用演示结果", file=sys.stderr)
        return _get_demo_results(query)

    # 依次尝试各搜索源，失败时降级
    last_error = None
    for name, fn in providers:
        try:
            print(f"   → 使用 {name} 进行真实搜索...", file=sys.stderr)
            results = fn(query)
            print(f"   ✓ {name} 返回 {len(results)} 个真实搜索结果", file=sys.stderr)
            return results
        except Exception as e:  # noqa: BLE001
            last_error = e
            print(f"   ✗ {name} 搜索失败: {e}", file=sys.stderr)
            print(f"   → 切换下一个搜索源...", file=sys.stderr)

    print(f"   ✗ 所有搜索源均失败，降级到演示结果（最后错误: {last_error}）", file=sys.stderr)
    return _get_demo_results(query)

def _get_demo_results(query: str) -> List[Dict[str, str]]:
    """获取演示搜索结果"""
    normalized_query = query.lower().strip()
    
    # 尝试匹配预设的演示数据
    for key, results in DEMO_SEARCH_RESULTS.items():
        if key != "default" and key in normalized_query:
            print(f"   ✓ 找到匹配的演示结果: '{key}'", file=sys.stderr)
            return results
    
    # 返回默认演示结果
    print(f"   → 返回默认演示结果", file=sys.stderr)
    return DEMO_SEARCH_RESULTS["default"]

def _safe_join(base: Path, relative: str) -> Path:
    print(f"   → 安全路径检查: base={base}, relative={relative}", file=sys.stderr)
    p = (base / relative).resolve()
    if not str(p).startswith(str(base.resolve())):
        print(f"   ✗ 检测到路径遍历攻击", file=sys.stderr)
        raise ValueError("检测到路径遍历攻击")
    print(f"   ✓ 路径安全验证通过: {p}", file=sys.stderr)
    return p

@mcp.tool()
def read_file(path: str) -> str:
    """
    读取沙箱化的 sample_data 目录下的 UTF-8 文本文件。
    示例：path='hello.txt'
    """
    print(f"📄 [工具调用] read_file(path='{path}')", file=sys.stderr)
    p = _safe_join(BASE_DIR, path)
    
    if not p.exists() or not p.is_file():
        print(f"   ✗ 文件未找到: {p}", file=sys.stderr)
        raise FileNotFoundError(f"{p} 未找到")
    
    print(f"   → 读取文件: {p}", file=sys.stderr)
    content = p.read_text(encoding="utf-8")
    print(f"   ✓ 成功读取 {len(content)} 个字符", file=sys.stderr)
    return content


# ---------- 资源 ----------

@mcp.resource("sample://hello.txt")
def sample_text_resource() -> Tuple[str, bytes]:
    """
    服务器暴露的简单资源示例。
    返回：(MIME 类型, 字节数据)
    """
    print(f"📦 [资源访问] sample://hello.txt", file=sys.stderr)
    print(f"   → 读取文件: {SAMPLE_FILE}", file=sys.stderr)
    data = SAMPLE_FILE.read_bytes()
    print(f"   ✓ 成功读取 {len(data)} 字节", file=sys.stderr)
    return "text/plain; charset=utf-8", data


def main() -> None:
    # 通过 stdio 运行服务器
    print("=" * 60, file=sys.stderr)
    print("🎯 [启动] MCP 服务器开始运行", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("📡 等待客户端通过 STDIO 连接...", file=sys.stderr)
    print("", file=sys.stderr)
    mcp.run()

if __name__ == "__main__":
    print("", file=sys.stderr)
    print("🌟 MCP 演示服务器", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    main()
