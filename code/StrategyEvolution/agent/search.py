import html
import os
import re

import requests

try:
    from ddgs import DDGS
except ImportError:  # ddgs 未安装时仅禁用该兜底
    DDGS = None

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _google_search(query: str, num: int = 3):
    """使用 Google Custom Search API 搜索。"""
    api_key = os.getenv("GOOGLE_API_KEY")
    cse_id = os.getenv("GOOGLE_CSE_ID")

    if not api_key or not cse_id:
        raise ValueError("Missing GOOGLE_API_KEY or GOOGLE_CSE_ID")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {"q": query, "key": api_key, "cx": cse_id, "num": num}

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    items = data.get("items", []) or []
    return [
        {
            "title": it.get("title", ""),
            "snippet": it.get("snippet", ""),
            "link": it.get("link", "")
        }
        for it in items
    ]


def _duckduckgo_search(query: str, num: int = 3):
    """使用 ddgs 库搜索（免费、无需 API 密钥，聚合多个搜索引擎）。"""
    if DDGS is None:
        raise ValueError("ddgs 库未安装，请运行: pip install ddgs")

    backends = os.getenv("SEARCH_BACKENDS", "auto")
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=num, backend=backends):
            results.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "link": r.get("href", "")
            })
    return results


_BING_ITEM = re.compile(r'<li class="b_algo".*?</li>', re.S)
_BING_LINK = re.compile(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_BING_SNIPPET = re.compile(r'<p[^>]*>(.*?)</p>', re.S)
_TAG = re.compile(r"<[^>]+>")


def _strip_tags(fragment: str) -> str:
    return html.unescape(_TAG.sub("", fragment)).strip()


def _bing_search(query: str, num: int = 3):
    """直接抓取 Bing 搜索结果（免费、无需密钥的最终兜底）。"""
    r = requests.get(
        "https://www.bing.com/search",
        params={"q": query, "count": max(num, 10), "ensearch": 1},
        headers=_HEADERS,
        timeout=15,
    )
    r.raise_for_status()

    results = []
    for item in _BING_ITEM.findall(r.text)[:num]:
        m = _BING_LINK.search(item)
        if not m:
            continue
        link, title = m.group(1), _strip_tags(m.group(2))
        sm = _BING_SNIPPET.search(item)
        snippet = _strip_tags(sm.group(1)) if sm else ""
        if title:
            results.append({"title": title, "snippet": snippet, "link": link})
    return results


def search_enabled() -> bool:
    """搜索功能是否可用（Google / ddgs / Bing 至少一条链路可用）。"""
    has_google = bool(os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CSE_ID"))
    # Bing 兜底仅依赖 requests（硬依赖），始终可用
    return has_google or DDGS is not None or True


def search_provider() -> str:
    """当前实际使用的搜索提供方。"""
    if os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CSE_ID"):
        return "google"
    return "bing"


def google_search_func(query: str, num: int = 3):
    """网络搜索入口（多级兜底，失败时返回空结果而不中断流程）：

    1. Google Custom Search（配置了密钥时）
    2. Bing 网页抓取（免费、无需密钥、稳定）
    3. ddgs 聚合搜索（免费兜底）
    """
    searchers = []
    if os.getenv("GOOGLE_API_KEY") and os.getenv("GOOGLE_CSE_ID"):
        searchers.append(_google_search)
    searchers.append(_bing_search)
    if DDGS is not None:
        searchers.append(_duckduckgo_search)

    last_err = None
    for searcher in searchers:
        try:
            results = searcher(query, num)
            if results:
                return results
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    if last_err is not None:
        print(f"⚠️ 搜索失败（{type(last_err).__name__}: {last_err}），返回空结果")
    return []


google_search_tool = {
    "type": "function",
    "function": {
        "name": "google_search_func",
        "description": (
            "Search the web and return top results (title, snippet, link)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string."
                },
                "num": {
                    "type": "integer",
                    "description": "Number of results to return (1-10).",
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["query"]
        }
    }
}
