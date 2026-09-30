"""FastAPI 后端服务入口。

提供：
  GET  /api/health          健康检查
  POST /api/essay/generate  流式生成（SSE）作文
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import AsyncIterator, Dict

from dotenv import dotenv_values
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from essay_graph import build_essay_graph


# ------------------------- 配置加载 ------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = os.environ.get("CONFIG_PATH", str(PROJECT_ROOT / "config.env"))


def load_env() -> None:
    """从 config.env 加载环境变量（不覆盖已存在的）。"""
    if not Path(CONFIG_PATH).exists():
        print(f"[WARN] 未找到配置文件 {CONFIG_PATH}")
        return
    values = dotenv_values(CONFIG_PATH)
    for k, v in values.items():
        if v is None:
            continue
        os.environ.setdefault(k, v)
    print(f"[INFO] 已加载配置: {CONFIG_PATH}")


load_env()


# ------------------------- 应用初始化 ------------------------- #
app = FastAPI(title="Essay Writer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 懒加载 graph，避免未配置 Key 时启动失败
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_essay_graph()
    return _graph


# ------------------------- 请求 / 响应模型 ------------------------- #
class EssayRequest(BaseModel):
    task: str = Field(..., description="作文题目或主题", min_length=1)
    max_revisions: int = Field(2, ge=1, le=5, description="最大修订次数")


# ------------------------- 路由 ------------------------- #
@app.get("/api/health")
async def health() -> Dict[str, str]:
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY"))
    return {
        "status": "ok",
        "deepseek_configured": "yes" if has_key else "no",
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
    }


@app.post("/api/essay/generate")
async def generate_essay(req: EssayRequest):
    """通过 Server-Sent Events 流式推送每一步状态与产物。"""
    if not req.task.strip():
        raise HTTPException(status_code=400, detail="作文题目不能为空")

    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="未配置 DEEPSEEK_API_KEY，请在 config.env 中设置后重启。",
        )

    thread_id = str(uuid.uuid4())
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    initial_state = {
        "task": req.task,
        "max_revisions": req.max_revisions,
        "revision_number": 1,
        "content": [],
    }

    async def event_stream() -> AsyncIterator[str]:
        try:
            # LangGraph 的 stream 在线程中阻塞，通过 to_thread 异步化
            steps = await asyncio.to_thread(
                lambda: list(
                    graph.stream(initial_state, config)
                )
            )

            # 依次推送节点输出
            for step in steps:
                for node_name, node_state in step.items():
                    payload = {
                        "type": "node",
                        "node": node_name,
                        "data": _serialize_state(node_name, node_state),
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            # 最终输出当前完整状态
            final_state = graph.get_state(config)
            payload = {
                "type": "done",
                "node": "final",
                "data": _serialize_state("final", final_state.values if final_state else {}),
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        except Exception as exc:  # noqa: BLE001
            err = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _serialize_state(node_name: str, state: dict) -> Dict[str, object]:
    """将每个节点的更新片段整理成前端友好的字段。"""
    out: Dict[str, object] = {"node": node_name}
    for key in ("plan", "draft", "critique", "revision_number"):
        if key in state and state[key] is not None:
            out[key] = state[key]
    if "content" in state and state["content"] is not None:
        out["content_count"] = len(state["content"])
    return out


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)