"""
A2A Web 网关服务 (FastAPI)
端口：8080

职责：
1. 作为 React 前端 (webapp/) 与 A2A Agent 服务之间的桥梁
2. 提供 Agent 状态查询 / 单 Agent 对话 / 多 Agent 管道编排 三类 API
3. 配置统一从项目根目录 config.env 读取

启动方式：
    python server/gateway.py
"""
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 保证可以 import agents.llm_client（用于加载 config.env）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "agents"))

load_dotenv(PROJECT_ROOT / "config.env")

import os  # noqa: E402

from a2a.client.legacy import A2AClient  # noqa: E402
from a2a.types import (  # noqa: E402
    Message,
    Part,
    Role,
    TextPart,
    MessageSendParams,
    SendMessageRequest,
)

# ---------- 配置 ----------
AGENT_URLS = {
    "collector": os.getenv("COLLECTOR_URL", "http://localhost:8001"),
    "summarizer": os.getenv("SUMMARIZER_URL", "http://localhost:8002"),
    "translator": os.getenv("TRANSLATOR_URL", "http://localhost:8003"),
    "classifier": os.getenv("CLASSIFIER_URL", "http://localhost:8004"),
}

GATEWAY_HOST = os.getenv("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8080"))

app = FastAPI(title="A2A Web Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- A2A 工具函数 ----------


def _build_text_message(text: str) -> SendMessageRequest:
    message = Message(
        message_id=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
    )
    return SendMessageRequest(
        id=str(uuid.uuid4()), params=MessageSendParams(message=message)
    )


async def _send_and_extract(client: A2AClient, req: SendMessageRequest) -> str:
    """向 Agent 发送消息并提取文本回复"""
    resp = await client.send_message(req)
    txt = ""
    result = getattr(resp.root, "result", None)
    if result and hasattr(result, "message"):
        msg_obj = getattr(result, "message")
    else:
        msg_obj = result or getattr(resp, "message", None)
    if msg_obj and hasattr(msg_obj, "parts"):
        for part in msg_obj.parts:
            if hasattr(part.root, "text"):
                txt = part.root.text
    return txt


async def call_agent(agent_name: str, message: str, timeout: float = 60.0) -> str:
    """调用指定 Agent 并返回文本结果"""
    url = AGENT_URLS.get(agent_name)
    if not url:
        raise ValueError(f"未知 Agent: {agent_name}")
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as http:
        client = A2AClient(httpx_client=http, url=url)
        return await _send_and_extract(client, _build_text_message(message))


# ---------- 数据模型 ----------


class ChatRequest(BaseModel):
    agent: str
    message: str


class PipelineRequest(BaseModel):
    topic: str = "集成电路"
    count: int = 3


# ---------- API 路由 ----------


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "a2a-gateway"}


@app.get("/api/history")
async def history(topic: str = Query(default="", description="按主题过滤"),
                  limit: int = Query(default=20, ge=1, le=100)):
    """查询 PostgreSQL 中记录的历史搜索结果"""
    from agents import db  # noqa: WPS433 (延迟导入，避免无谓加载)
    rows = db.recent_results(topic=topic, limit=limit)
    return {"ok": True, "topic": topic or None, "count": len(rows), "records": rows}


@app.get("/api/agents")
async def list_agents():
    """查询所有 Agent 的运行状态与 Agent Card 信息"""
    agents_info: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as http:
        for name, url in AGENT_URLS.items():
            item: dict[str, Any] = {
                "name": name,
                "url": url,
                "online": False,
                "card": None,
            }
            try:
                resp = await http.get(f"{url}/.well-known/agent-card.json")
                if resp.status_code == 200:
                    item["online"] = True
                    item["card"] = resp.json()
            except Exception:
                pass
            agents_info.append(item)
    return {"agents": agents_info}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """与单个 Agent 对话"""
    start = time.time()
    try:
        reply = await call_agent(req.agent, req.message)
        return {
            "ok": True,
            "agent": req.agent,
            "reply": reply,
            "elapsed": round(time.time() - start, 2),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "agent": req.agent,
            "reply": f"调用 Agent 失败: {e}",
            "elapsed": round(time.time() - start, 2),
        }


@app.post("/api/pipeline")
async def pipeline(req: PipelineRequest):
    """多 Agent 协作管道：
    Collector 收集信息 → Classifier 分类 → Summarizer 摘要 → Translator 翻译
    """
    stages: list[dict[str, Any]] = []

    async def _stage(agent: str, message: str, description: str) -> str:
        start = time.time()
        output = await call_agent(agent, message)
        stages.append(
            {
                "agent": agent,
                "description": description,
                "output": output,
                "elapsed": round(time.time() - start, 2),
            }
        )
        return output

    try:
        # 1. 收集信息
        news = await _stage(
            "collector",
            f"收集关于 {req.topic} 的信息，限制 {req.count} 条",
            f"收集「{req.topic}」主题信息",
        )

        # 2. 内容分类
        classification = await _stage(
            "classifier", f"对以下内容分类：\n\n{news}", "信息内容分类"
        )

        # 3. 生成摘要
        summary = await _stage(
            "summarizer", f"对以下信息生成详细摘要：\n\n{news}", "生成信息摘要"
        )

        # 4. 翻译为英文
        translation = await _stage(
            "translator",
            f"将以下摘要翻译成英文：\n\n{summary}",
            "将摘要翻译成英文",
        )

        return {
            "ok": True,
            "stages": stages,
            "result": {
                "news": news,
                "classification": classification,
                "summary": summary,
                "translation": translation,
            },
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "stages": stages}


if __name__ == "__main__":
    print("🚀 A2A Web Gateway 启动中...")
    print(f"   Gateway: http://localhost:{GATEWAY_PORT}")
    print(f"   Agents : {AGENT_URLS}")
    uvicorn.run(app, host=GATEWAY_HOST, port=GATEWAY_PORT)
