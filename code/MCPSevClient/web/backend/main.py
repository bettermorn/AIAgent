# web/backend/main.py
# FastAPI 后端：读取 config.env 中的 DEEPSEEK_API_KEY，代理调用 DeepSeek 模型
# 工具调用能力 = 3 个原生工具（calculate / get_current_time / generate_password）
#              + MCP 工具（add / search_http / read_file）
import asyncio
import ast
import datetime as _dt
import json
import operator as _op
import os
import secrets
import string
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI

# ---------------------------------------------------------------------------
# 配置加载：优先加载项目根目录下的 config.env
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / "config.env")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
PORT = int(os.getenv("PORT", "8000"))
MAX_TOOL_ROUNDS = 5  # 单次对话最多工具调用轮数，防止死循环

# ---------------------------------------------------------------------------
# MCP 工具会话（可选依赖：缺少 mcp 包或服务器启动失败时降级为纯聊天）
# ---------------------------------------------------------------------------
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

mcp_session: Optional["ClientSession"] = None
mcp_tools: list = []


async def _mcp_worker():
    """后台任务：启动 MCP 服务器子进程并保持会话存活。"""
    global mcp_session, mcp_tools
    try:
        server_script = ROOT_DIR / "src" / "mcp_demo" / "server.py"
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-u", str(server_script)],
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
                mcp_session = session
                mcp_tools = list(resp.tools)
                print(f"[MCP] 已连接，发现 {len(mcp_tools)} 个工具: "
                      f"{[t.name for t in mcp_tools]}")
                await asyncio.Event().wait()  # 保持会话存活
    except asyncio.CancelledError:
        pass
    except Exception as e:  # noqa: BLE001
        print(f"[MCP] 连接失败，Web 应用将以纯聊天模式运行: {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = None
    if MCP_AVAILABLE:
        task = asyncio.create_task(_mcp_worker())
    yield
    if task:
        task.cancel()


app = FastAPI(title="DeepSeek Chat Web App", lifespan=lifespan)

# 开发阶段允许 Vite 开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_client() -> OpenAI:
    """获取 DeepSeek 客户端（OpenAI 兼容接口），并校验 API Key。"""
    if not DEEPSEEK_API_KEY or DEEPSEEK_API_KEY == "your-deepseek-api-key-here":
        raise HTTPException(
            status_code=500,
            detail="未配置 DEEPSEEK_API_KEY，请在项目根目录 config.env 中填写你的 DeepSeek API Key。",
        )
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


def _mcp_tools_to_openai() -> list:
    """将 MCP 工具转换为 OpenAI/DeepSeek 函数调用格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in mcp_tools
    ]


# ---------------------------------------------------------------------------
# 原生工具（Web 后端内置，无需 MCP 服务器）
# ---------------------------------------------------------------------------
_AST_OPS = {
    ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
    ast.Div: _op.truediv, ast.Pow: _op.pow, ast.Mod: _op.mod,
    ast.FloorDiv: _op.floordiv, ast.USub: _op.neg, ast.UAdd: _op.pos,
}


def _safe_eval(node):
    """基于 AST 的安全算术表达式求值，仅允许数字与算术运算符。"""
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _AST_OPS:
        return _AST_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _AST_OPS:
        return _AST_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError(f"不支持的表达式元素: {type(node).__name__}")


def _tool_calculate(expression: str) -> str:
    """计算四则/幂/取模等数学表达式的精确结果。"""
    tree = ast.parse(expression, mode="eval")
    return f"{expression} = {_safe_eval(tree)}"


def _tool_get_current_time(timezone: str = "Asia/Shanghai") -> str:
    """获取指定时区的当前日期时间。"""
    try:
        from zoneinfo import ZoneInfo
        now = _dt.datetime.now(ZoneInfo(timezone))
    except Exception:  # noqa: BLE001
        now = _dt.datetime.now()
        timezone = "本地时间"
    return now.strftime(f"%Y-%m-%d %H:%M:%S（%A，{timezone}）")


def _tool_generate_password(length: int = 16, include_symbols: bool = True) -> str:
    """生成一个加密安全的随机密码。"""
    length = max(6, min(64, int(length)))
    pool = string.ascii_letters + string.digits
    if include_symbols:
        pool += "!@#$%^&*()-_=+[]{}"
    pw = "".join(secrets.choice(pool) for _ in range(length))
    return f"已生成 {length} 位{'含特殊字符' if include_symbols else '纯字母数字'}密码: `{pw}`"


# ---------------------------------------------------------------------------
# 原生工具：天气 / 汇率 / 网页阅读（使用免费公开 API，无需 Key）
# ---------------------------------------------------------------------------
_WMO_WEATHER = {
    0: "晴", 1: "基本晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾凇",
    51: "小毛毛雨", 53: "毛毛雨", 55: "大毛毛雨", 61: "小雨", 63: "中雨",
    65: "大雨", 66: "冻雨", 67: "强冻雨", 71: "小雪", 73: "中雪", 75: "大雪",
    77: "雪粒", 80: "小阵雨", 81: "阵雨", 82: "强阵雨", 85: "小阵雪",
    86: "大阵雪", 95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
}


def _tool_get_weather(city: str) -> str:
    """查询指定城市的实时天气（Open-Meteo 免费公开 API，无需 Key）。"""
    import httpx

    with httpx.Client(timeout=15.0) as client:
        # 1) 城市名 -> 经纬度（geocoding API）
        geo = client.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "zh", "format": "json"},
        )
        geo.raise_for_status()
        locations = (geo.json() or {}).get("results") or []
        if not locations:
            return f"未找到城市: {city}"
        loc = locations[0]
        lat, lon = loc["latitude"], loc["longitude"]
        city_name = loc.get("name", city)
        country = loc.get("country", "")

        # 2) 经纬度 -> 实时天气
        wx = client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
        )
        wx.raise_for_status()
        cur = (wx.json() or {}).get("current") or {}

    code = cur.get("weather_code")
    desc = _WMO_WEATHER.get(code, f"未知({code})")
    return (
        f"{city_name}（{country}）当前天气：{desc}，"
        f"气温 {cur.get('temperature_2m', '?')}°C，"
        f"湿度 {cur.get('relative_humidity_2m', '?')}%，"
        f"风速 {cur.get('wind_speed_10m', '?')} km/h"
    )


def _tool_get_exchange_rate(base: str = "USD", target: str = "CNY", amount: float = 1.0) -> str:
    """查询实时汇率并换算金额（open.er-api.com 免费公开 API，无需 Key）。"""
    import httpx

    base, target = base.upper(), target.upper()
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"https://open.er-api.com/v6/latest/{base}")
        r.raise_for_status()
        data = r.json()

    if data.get("result") != "success":
        return f"汇率查询失败: {data.get('error-type', '未知错误')}"
    rates = data.get("rates") or {}
    if target not in rates:
        return f"不支持的货币代码: {target}"
    rate = rates[target]
    converted = rate * float(amount)
    return f"当前汇率: 1 {base} = {rate} {target}\n换算结果: {amount} {base} ≈ {converted:.4f} {target}\n（数据更新时间: {data.get('time_last_update_utc', '未知')}）"


def _tool_read_url(url: str, max_chars: int = 2000) -> str:
    """抓取网页并提取正文文本（自动去除 HTML 标签/脚本/样式），用于阅读网页内容。"""
    import re as _re
    import httpx

    if not _re.match(r"^https?://", url):
        return f"仅支持 http/https 链接: {url}"

    headers = {"User-Agent": "Mozilla/5.0 (compatible; DeepSeekChatBot/1.0)"}
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        html = r.text

    # 去除 script/style/noscript 与 HTML 标签
    text = _re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=_re.S | _re.I)
    text = _re.sub(r"<br\s*/?>|</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", text, flags=_re.I)
    text = _re.sub(r"<[^>]+>", " ", text)
    # 反转义常见实体并压缩空白
    import html as _html
    text = _html.unescape(text)
    text = _re.sub(r"[ \t]+", " ", text)
    text = _re.sub(r"\n\s*\n+", "\n", text).strip()

    max_chars = max(200, min(6000, int(max_chars)))
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n...(已截断，全文共 {len(text)} 字符)"
    return f"网页内容（{url}）:\n{text}"


# ---------------------------------------------------------------------------
# 原生工具：网络搜索（直接调用博查 / SerpAPI，不依赖 MCP 服务器）
# Key 来源：环境变量或项目根目录 config.env（BOCHA_API_KEY / SERPAPI_API_KEY）
# ---------------------------------------------------------------------------
def _tool_web_search(query: str, count: int = 5) -> str:
    """使用真实搜索引擎（博查优先，SerpAPI 备用）搜索网络信息。"""
    import httpx

    count = max(1, min(10, int(count)))
    errors = []

    # 1) 博查 Bocha（中文搜索推荐）
    bocha_key = os.getenv("BOCHA_API_KEY")
    if bocha_key:
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.post(
                    "https://api.bochaai.com/v1/web-search",
                    json={"query": query, "summary": True, "count": count},
                    headers={"Authorization": f"Bearer {bocha_key}",
                             "Content-Type": "application/json"},
                )
                r.raise_for_status()
                pages = ((r.json() or {}).get("data") or {}).get("webPages") or {}
                items = [
                    f"{i + 1}. {it.get('name', '')}\n   摘要: {it.get('summary') or it.get('snippet', '')}\n   链接: {it.get('url', '')}"
                    for i, it in enumerate((pages.get("value") or [])[:count])
                ]
                if items:
                    return f"搜索「{query}」的结果（博查，共 {len(items)} 条）:\n" + "\n".join(items)
                errors.append("博查未返回结果")
        except Exception as e:  # noqa: BLE001
            errors.append(f"博查失败: {e}")

    # 2) SerpAPI 备用
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if serpapi_key:
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.get(
                    "https://serpapi.com/search",
                    params={"q": query, "engine": "baidu", "api_key": serpapi_key, "num": count},
                )
                r.raise_for_status()
                items = [
                    f"{i + 1}. {it.get('title', '')}\n   摘要: {it.get('snippet', '')}\n   链接: {it.get('link', '')}"
                    for i, it in enumerate((r.json() or {}).get("organic_results", [])[:count])
                ]
                if items:
                    return f"搜索「{query}」的结果（SerpAPI，共 {len(items)} 条）:\n" + "\n".join(items)
                errors.append("SerpAPI 未返回结果")
        except Exception as e:  # noqa: BLE001
            errors.append(f"SerpAPI失败: {e}")

    if errors:
        return f"搜索失败: {'; '.join(errors)}。请检查 config.env 中的 BOCHA_API_KEY / SERPAPI_API_KEY 配置。"
    return "未配置搜索 API Key（BOCHA_API_KEY / SERPAPI_API_KEY），无法执行真实搜索。"


NATIVE_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "计算数学表达式的精确结果，支持 + - * / // % ** 和括号，例如 '(123*456+789)/3'",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "要计算的数学表达式"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的日期和时间，可指定 IANA 时区名，如 Asia/Shanghai、America/New_York",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {"type": "string", "description": "IANA 时区名，默认 Asia/Shanghai"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_password",
            "description": "生成一个加密安全的随机密码",
            "parameters": {
                "type": "object",
                "properties": {
                    "length": {"type": "integer", "description": "密码长度，6-64，默认 16"},
                    "include_symbols": {"type": "boolean", "description": "是否包含特殊字符，默认 true"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的实时天气（气温/湿度/天气现象/风速），支持中文或英文城市名",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如 '北京'、'Shanghai'、'Tokyo'"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "查询两种货币之间的实时汇率并换算金额，如 '100 USD 换算成 CNY 是多少'",
            "parameters": {
                "type": "object",
                "properties": {
                    "base": {"type": "string", "description": "基准货币代码，如 USD，默认 USD"},
                    "target": {"type": "string", "description": "目标货币代码，如 CNY，默认 CNY"},
                    "amount": {"type": "number", "description": "要换算的金额，默认 1"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_url",
            "description": "抓取网页链接并提取正文文本，用于阅读指定 URL 的内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要阅读的网页链接（http/https）"},
                    "max_chars": {"type": "integer", "description": "返回正文最大字符数，200-6000，默认 2000"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "使用真实搜索引擎搜索网络上的最新信息，返回标题、摘要与链接。适合查询新闻、技术资料、事实性信息等",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "count": {"type": "integer", "description": "返回结果条数，1-10，默认 5"},
                },
                "required": ["query"],
            },
        },
    },
]

NATIVE_HANDLERS = {
    "calculate": _tool_calculate,
    "get_current_time": _tool_get_current_time,
    "generate_password": _tool_generate_password,
    "get_weather": _tool_get_weather,
    "get_exchange_rate": _tool_get_exchange_rate,
    "read_url": _tool_read_url,
    "web_search": _tool_web_search,
}


class Message(BaseModel):
    role: str  # "user" / "assistant" / "system"
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None
    stream: bool = True


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model": DEEPSEEK_MODEL,
        "api_key_configured": bool(DEEPSEEK_API_KEY) and DEEPSEEK_API_KEY != "your-deepseek-api-key-here",
        "native_tools": list(NATIVE_HANDLERS),
        "mcp_tools": [t.name for t in mcp_tools],
    }


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """调用 DeepSeek 模型。当模型决定调用 MCP 工具时：
    - 通过 SSE 发送 `data: [TOOL] {...}` 通知前端
    - 通过 MCP 执行工具，将结果回传给模型继续生成
    - 最终回答以纯文本 SSE 块流式返回
    """
    client = get_client()
    model = req.model or DEEPSEEK_MODEL
    messages = [m.model_dump() for m in req.messages]
    # 工具列表 = 3 个原生工具 + MCP 工具
    openai_tools = NATIVE_TOOL_SPECS + (_mcp_tools_to_openai() if (mcp_session and mcp_tools) else [])

    async def run_rounds():
        """工具调用循环；产出 ("text", delta) / ("tool", {...}) / ("final", content)。"""
        tool_events = []
        for _ in range(MAX_TOOL_ROUNDS):
            kwargs = dict(model=model, messages=messages, stream=True)
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"

            stream = client.chat.completions.create(**kwargs)
            round_content = ""
            tc_acc: dict = {}  # index -> {"id","name","arguments"}

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    round_content += delta.content
                    yield ("text", delta.content)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        slot = tc_acc.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                        if tc.id:
                            slot["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                slot["name"] += tc.function.name
                            if tc.function.arguments:
                                slot["arguments"] += tc.function.arguments

            if not tc_acc:
                # 模型未调用工具，本轮即为最终回答
                yield ("final", round_content)
                return

            # 模型决定调用工具：记录 assistant 消息并执行
            tool_calls = [
                {
                    "id": s["id"],
                    "type": "function",
                    "function": {"name": s["name"], "arguments": s["arguments"]},
                }
                for s in tc_acc.values()
            ]
            messages.append({
                "role": "assistant",
                "content": round_content or None,
                "tool_calls": tool_calls,
            })

            for s in tool_calls:
                name = s["function"]["name"]
                try:
                    args = json.loads(s["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_events.append({"name": name, "args": args})
                yield ("tool", {"name": name, "args": args})

                # 执行工具：原生工具优先，其余走 MCP
                try:
                    if name in NATIVE_HANDLERS:
                        handler = NATIVE_HANDLERS[name]
                        tool_result = await asyncio.to_thread(
                            lambda: handler(**{k: v for k, v in args.items()})
                        )
                    elif mcp_session:
                        result = await mcp_session.call_tool(name, args)
                        tool_result = str(result.content)
                    else:
                        tool_result = f"工具调用失败: 未知工具 {name}（MCP 未连接）"
                except Exception as e:  # noqa: BLE001
                    tool_result = f"工具调用失败: {e}"

                yield ("tool_result", {"name": name, "result": tool_result[:300]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": s["id"],
                    "content": tool_result,
                })
            # 继续下一轮，让模型基于工具结果生成最终回答

        yield ("final", "（工具调用轮数已达上限）")

    if req.stream:
        async def event_stream():
            try:
                async for kind, payload in run_rounds():
                    if kind == "text":
                        yield f"data: {payload}\n\n"
                    elif kind == "tool":
                        yield f"data: [TOOL] {json.dumps(payload, ensure_ascii=False)}\n\n"
                    elif kind == "tool_result":
                        yield f"data: [TOOL_RESULT] {json.dumps(payload, ensure_ascii=False)}\n\n"
                    # "final" 无需额外处理，[DONE] 结束
                yield "data: [DONE]\n\n"
            except Exception as e:  # noqa: BLE001
                yield f"data: [ERROR] {e}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # 非流式：收集最终结果一次性返回
    final_content = ""
    tool_events = []
    async for kind, payload in run_rounds():
        if kind == "text":
            final_content += payload
        elif kind == "tool":
            tool_events.append(payload)
        elif kind == "final":
            final_content = payload or final_content
    return {"content": final_content, "tool_calls": tool_events}


# ---------------------------------------------------------------------------
# 生产模式：直接托管 React 构建产物（web/frontend/dist）
# ---------------------------------------------------------------------------
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file = DIST_DIR / full_path
        if full_path and file.is_file():
            return FileResponse(file)
        return FileResponse(DIST_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
