"""基于 LangGraph 与 DeepSeek 的多 Agent 作文生成图。

流程：
  planner -> research_plan -> generate -> (reflect -> research_critique -> generate)* -> END
"""
from __future__ import annotations

import os
import re
from typing import List

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.pydantic_v1 import BaseModel
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from prompts import (
    PLAN_PROMPT,
    REFLECTION_PROMPT,
    RESEARCH_CRITIQUE_PROMPT,
    RESEARCH_PLAN_PROMPT,
    WRITER_PROMPT,
)
from models import AgentState


class Queries(BaseModel):
    queries: List[str]


def _build_model() -> ChatOpenAI:
    """根据环境变量构建 DeepSeek Chat 模型。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "未找到 DEEPSEEK_API_KEY，请在 config.env 中配置后重启服务。"
        )
    model_name = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
    )


def _get_tavily_client():
    """按需构建 Tavily 搜索客户端；未配置返回 UNKNOWN。"""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None
    try:
        from tavily import TavilyClient

        return TavilyClient(api_key=api_key)
    except Exception:
        return None


def _extract_json(text: str) -> List[str]:
    """从模型输出中粗略提取 JSON 列表字符串。"""
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if not match:
        return []
    import json

    try:
        data = json.loads(match.group(0))
        if isinstance(data, list):
            return [str(x) for x in data][:3]
    except Exception:
        return []
    return []


def build_essay_graph():
    """构造并编译 LangGraph 多 Agent 图。"""
    model = _build_model()
    tavily = _get_tavily_client()

    def plan_node(state: AgentState):
        response = model.invoke(
            [SystemMessage(content=PLAN_PROMPT), HumanMessage(content=state["task"])]
        )
        return {"plan": response.content}

    def _do_research(task_text: str, content: List[str]) -> List[str]:
        """调用 DeepSeek 生成检索 query，再尝试联网检索。"""
        try:
            queries_obj = model.with_structured_output(Queries).invoke(
                [
                    SystemMessage(content=RESEARCH_PLAN_PROMPT),
                    HumanMessage(content=task_text),
                ]
            )
            queries = queries_obj.queries
        except Exception:
            # 结构化输出失败时退回普通文本再解析 JSON
            resp = model.invoke(
                [
                    SystemMessage(content=RESEARCH_PLAN_PROMPT),
                    HumanMessage(content=task_text),
                ]
            )
            queries = _extract_json(resp.content)

        if tavily and queries:
            for q in queries:
                try:
                    response = tavily.search(query=q, max_results=2)
                    for r in response.get("results", []):
                        content.append(r.get("content", ""))
                except Exception:
                    # 联网检索失败不应阻断流程
                    pass
        return content

    def research_plan_node(state: AgentState):
        content = list(state.get("content") or [])
        content = _do_research(state["task"], content)
        return {"content": content}

    def generation_node(state: AgentState):
        content = "\n\n".join(state.get("content") or [])
        user_message = HumanMessage(
            content=f"{state['task']}\n\nHere is my plan:\n\n{state['plan']}"
        )
        response = model.invoke(
            [
                SystemMessage(content=WRITER_PROMPT.format(content=content)),
                user_message,
            ]
        )
        return {
            "draft": response.content,
            "revision_number": state.get("revision_number", 1) + 1,
        }

    def reflection_node(state: AgentState):
        response = model.invoke(
            [SystemMessage(content=REFLECTION_PROMPT), HumanMessage(content=state["draft"])]
        )
        return {"critique": response.content}

    def research_critique_node(state: AgentState):
        content = list(state.get("content") or [])
        try:
            queries_obj = model.with_structured_output(Queries).invoke(
                [
                    SystemMessage(content=RESEARCH_CRITIQUE_PROMPT),
                    HumanMessage(content=state["critique"]),
                ]
            )
            queries = queries_obj.queries
        except Exception:
            resp = model.invoke(
                [
                    SystemMessage(content=RESEARCH_CRITIQUE_PROMPT),
                    HumanMessage(content=state["critique"]),
                ]
            )
            queries = _extract_json(resp.content)

        if tavily and queries:
            for q in queries:
                try:
                    response = tavily.search(query=q, max_results=2)
                    for r in response.get("results", []):
                        content.append(r.get("content", ""))
                except Exception:
                    pass
        return {"content": content}

    def should_continue(state: AgentState):
        if state.get("revision_number", 1) > state.get("max_revisions", 2):
            return END
        return "reflect"

    builder = StateGraph(AgentState)
    builder.add_node("planner", plan_node)
    builder.add_node("generate", generation_node)
    builder.add_node("reflect", reflection_node)
    builder.add_node("research_plan", research_plan_node)
    builder.add_node("research_critique", research_critique_node)

    builder.set_entry_point("planner")
    builder.add_edge("planner", "research_plan")
    builder.add_edge("research_plan", "generate")

    builder.add_conditional_edges(
        "generate", should_continue, {END: END, "reflect": "reflect"}
    )
    builder.add_edge("reflect", "research_critique")
    builder.add_edge("research_critique", "generate")

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)