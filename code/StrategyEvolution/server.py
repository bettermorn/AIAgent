"""Web 服务端：提供 REST/SSE 接口驱动自进化报告生成代理。

用法：
    uvicorn server:app --reload --port 8000

配置从 config.env 读取（DEEPSEEK_API_KEY 等）。
"""

import json
import os
import queue
import threading

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

load_dotenv("config.env")

from agent import SelfEvolvingAgent  # noqa: E402
from agent.search import search_enabled, search_provider  # noqa: E402

app = FastAPI(title="自进化商业报告生成代理", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="报告主题或用户需求")
    steps: int = Field(5, ge=1, le=20)
    target_words: int = Field(800, ge=100, le=10000)
    target_score: float = Field(0.86, ge=0.0, le=1.0)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
        "search_configured": search_enabled(),
        "search_provider": search_provider(),
    }


@app.post("/api/generate")
def generate(req: RunRequest):
    """运行自进化代理，通过 SSE 流式返回日志与最终结果。"""
    events: "queue.Queue" = queue.Queue()

    def log(message: str):
        events.put(("log", message))

    def worker():
        try:
            agent = SelfEvolvingAgent()
            summary, meta = agent.run(
                source_text=req.prompt,
                steps=req.steps,
                target_score=req.target_score,
                target_words=req.target_words,
                log_fn=log,
            )
            events.put((
                "result",
                {
                    "summary": summary,
                    "best_score": meta["best_score"],
                    "search_summary": meta["search_summary"],
                    "learned_params": meta["learned_params"],
                },
            ))
        except Exception as e:  # noqa: BLE001
            events.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            item = events.get()
            if item is None:
                break
            event, data = item
            payload = json.dumps(data, ensure_ascii=False)
            yield f"event: {event}\ndata: {payload}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# 托管前端构建产物（web/dist），存在则直接访问 http://host:port
_dist = os.path.join(os.path.dirname(__file__), "web", "dist")
if os.path.isdir(_dist):
    from fastapi.staticfiles import StaticFiles  # noqa: E402

    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host=os.getenv("SERVER_HOST", "127.0.0.1"),
        port=int(os.getenv("SERVER_PORT", "8000")),
        reload=True,
    )
