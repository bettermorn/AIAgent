"""
网络搜索服务

支持两个搜索源（配置读取自项目根目录 config.env）：
- SerpAPI : https://serpapi.com          (SERPAPI_API_KEY)
- Bocha   : https://bochaai.com (博查)   (BOCHA_API_KEY)

优先使用 SerpAPI，失败或未配置时回退到 Bocha；
两者都不可用时抛出异常，由调用方降级到本地 NEWS_DB。
"""
import os

import httpx

# llm_client 在导入时已加载 config.env
from llm_client import DEEPSEEK_MODEL  # noqa: F401  (确保 config.env 已加载)

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "")
BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "")

SERPAPI_URL = "https://serpapi.com/search"
BOCHA_URL = "https://api.bochaai.com/v1/web-search"

TIMEOUT = 20.0


def _normalize_serpapi(item: dict) -> dict:
    return {
        "title": (item.get("title") or "").strip(),
        "url": item.get("link") or "",
        "snippet": (item.get("snippet") or item.get("date") or "").strip(),
        "source": item.get("source") or "",
        "date": item.get("date") or "",
    }


def _normalize_bocha(item: dict) -> dict:
    return {
        "title": (item.get("name") or "").strip(),
        "url": item.get("url") or "",
        "snippet": (item.get("summary") or item.get("snippet") or "").strip(),
        "source": item.get("siteName") or "",
        "date": item.get("dateLastCrawled") or "",
    }


def _search_serpapi(query: str, count: int) -> list[dict]:
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.get(
            SERPAPI_URL,
            params={
                "q": query,
                "api_key": SERPAPI_API_KEY,
                "num": min(count, 10),
                "hl": "zh-cn",
                "gl": "cn",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    results = [_normalize_serpapi(x) for x in data.get("organic_results", [])]
    return [r for r in results if r["title"]][:count]


def _search_bocha(query: str, count: int) -> list[dict]:
    with httpx.Client(timeout=TIMEOUT) as client:
        resp = client.post(
            BOCHA_URL,
            headers={
                "Authorization": f"Bearer {BOCHA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"query": query, "count": min(count, 10)},
        )
        resp.raise_for_status()
        data = resp.json()
    pages = ((data.get("data") or {}).get("webPages") or {}).get("value", [])
    results = [_normalize_bocha(x) for x in pages]
    return [r for r in results if r["title"]][:count]


def _dedup(results: list[dict]) -> list[dict]:
    """按标题去重（同一新闻常被多源收录）"""
    seen = set()
    out = []
    for r in results:
        key = r["title"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _relevant_ratio(results: list[dict], keywords: list) -> float:
    """计算结果与主题关键词的相关比例（标题或摘要命中任一关键词即算相关）"""
    if not results or not keywords:
        return 1.0
    hits = 0
    for r in results:
        text = (r["title"] + " " + r["snippet"]).lower()
        if any(k.lower() in text for k in keywords):
            hits += 1
    return hits / len(results)


def search(query: str, count: int = 5, keywords: list = None) -> tuple[list[dict], str]:
    """执行网络搜索，返回 (结果列表, 实际使用的搜索源名称)。

    优先级：SerpAPI → Bocha；
    - 某个源调用失败、返回空、或结果与 keywords 相关性过低（<50%）时，自动切换下一个源；
    - 均失败时抛出 RuntimeError。
    """
    errors = []

    if SERPAPI_API_KEY:
        try:
            results = _dedup(_search_serpapi(query, count))
            if results and _relevant_ratio(results, keywords or []) >= 0.5:
                return results, "serpapi"
            errors.append(f"serpapi: 结果为空或与主题不相关")
        except Exception as e:  # noqa: BLE001
            errors.append(f"serpapi: {e}")

    if BOCHA_API_KEY:
        try:
            results = _dedup(_search_bocha(query, count))
            if results and _relevant_ratio(results, keywords or []) >= 0.5:
                return results, "bocha"
            errors.append(f"bocha: 结果为空或与主题不相关")
        except Exception as e:  # noqa: BLE001
            errors.append(f"bocha: {e}")

    if not SERPAPI_API_KEY and not BOCHA_API_KEY:
        raise RuntimeError("未配置 SERPAPI_API_KEY / BOCHA_API_KEY")

    raise RuntimeError("搜索失败 -> " + "; ".join(errors))
