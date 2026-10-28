"""Agent 基类：统一的六层内部结构（文档 4.1）——感知、规划、记忆、工具、反思、输出。

- 感知层：解析输入、实体识别、上下文装载
- 规划层：由子类给出步骤（本系统中为确定性 DAG + LLM 辅助），事件流可见
- 记忆层：任务状态 Checkpoint(PostgreSQL) + 长期知识(图谱/案例)
- 工具层：只能经 registry.call 调用其白名单工具(参数校验/配额/审计)
- 反思层：证据充分性、一致性(规则 vs 模型)、置信度
- 输出层：结构化结果 + 证据链 + 不确定性
"""
from __future__ import annotations

import time
from typing import Any

from .. import security
from ..tools.registry import PermissionDenied, TaskCtx, ToolError, registry


class BaseAgent:
    name = "base"
    label = "Agent"

    def __init__(self, ctx: TaskCtx):
        self.ctx = ctx

    # ---- 事件 ----
    def emit(self, typ: str, payload: dict | None = None) -> None:
        self.ctx.emit(self.name, typ, payload or {})

    def perceive(self, **kw) -> dict:
        self.ctx.check_quota("step")
        self.emit("perceive", kw)
        return kw

    def plan(self, steps: list[str]) -> None:
        self.ctx.check_quota("step")
        self.emit("plan", {"steps": steps})

    def tool(self, name: str, **args) -> Any:
        return registry.call(self.name, name, args, self.ctx)

    def try_tool(self, name: str, **args) -> Any:
        """工具失败不终止整个任务：返回 {'error':...}，反思层据此降低置信度或重规划。"""
        try:
            return self.tool(name, **args)
        except PermissionDenied:
            raise
        except ToolError as e:
            self.emit("tool_error", {"tool": name, "error": str(e)})
            return {"error": str(e)}

    def reflect(self, checks: list[dict]) -> dict:
        ok = all(c.get("ok", True) for c in checks)
        self.emit("reflect", {"ok": ok, "checks": checks})
        return {"ok": ok, "checks": checks}

    def output(self, data: dict) -> dict:
        self.emit("output", {"keys": list(data.keys())})
        return data
