"""数据模型定义。"""
from typing import TypedDict, List


class AgentState(TypedDict):
    """LangGraph 多 Agent 共享状态。"""
    task: str
    plan: str
    draft: str
    critique: str
    content: List[str]
    revision_number: int
    max_revisions: int