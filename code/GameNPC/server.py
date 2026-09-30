"""FastAPI 后端服务：为 React 前端提供 NPC 对话 API"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from game_npc_langgraph.main import build_app
from game_npc_langgraph.config import HOST, PORT
from game_npc_langgraph.npc_agents import npc_profiles

app = FastAPI(title="Game NPC LangGraph API")

# 允许前端开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 构建对话状态图（应用启动时初始化一次）
langgraph_app = build_app()

# NPC 展示信息（前端角色卡片）
npc_meta = {
    "村长": {"emoji": "🏛️", "desc": "村庄管理、历史故事、一般建议"},
    "铁匠": {"emoji": "⚔️", "desc": "武器装备、打造修理、战斗相关"},
    "药师": {"emoji": "🌿", "desc": "草药治疗、健康咨询、医疗相关"},
}


class ChatRequest(BaseModel):
    message: str
    chat_history: Optional[List[Dict[str, Any]]] = []


@app.get("/api/npcs")
def get_npcs():
    """返回可用的 NPC 列表"""
    return [
        {"name": name, "emoji": npc_meta[name]["emoji"], "desc": npc_meta[name]["desc"]}
        for name in npc_profiles
    ]


@app.post("/api/chat")
def chat(req: ChatRequest):
    """对话接口：自动路由到最合适的 NPC 并返回回复"""
    state = {
        "input": req.message,
        "chat_history": _tag_history(req.chat_history or []),
    }
    result = langgraph_app.invoke(state)
    output = result.get("output", "")

    # 从输出中解析 NPC 名字（格式为 "NPC名: 内容"）
    npc_name = "村长"
    reply = output
    for name in npc_profiles:
        if output.startswith(f"{name}:"):
            npc_name = name
            reply = output[len(name) + 1:].strip()
            break

    return {"npc": npc_name, "npc_emoji": npc_meta[npc_name]["emoji"], "reply": reply}


def _tag_history(chat_history):
    """给 assistant 历史消息加上 "[NPC名]" 前缀，帮助路由器知道上一句话是谁说的"""
    tagged = []
    for m in chat_history:
        if m.get("role") == "assistant" and m.get("npc"):
            tagged.append({
                "role": "assistant",
                "content": f"[{m['npc']}] {m.get('content', '')}",
            })
        else:
            tagged.append(m)
    return tagged


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host=HOST, port=PORT, reload=True)
