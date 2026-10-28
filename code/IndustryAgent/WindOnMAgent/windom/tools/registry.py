"""工具注册中心（文档 3.5 / 6.5，MCP 风格）：统一注册、Schema 校验、最小权限、用户身份透传(ABAC)、配额、熔断、审计。

- 每个 Agent 只能调用其白名单工具（总控 Agent 不直接访问业务系统，只能调用子 Agent）
- 参数经 Pydantic JSON Schema 校验；设备编码必须存在于台账，禁止通配/批量操作
- 以发起用户的身份与权限调用工具（On-Behalf-Of），不得越权访问无权风场
- 单任务最大步数/工具调用次数/Token/时长（防失控循环）
- 工具连续失败熔断；每次调用写审计(入参、出参摘要、耗时、结果码)
"""
from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError

from .. import db, llm, security
from ..config import settings


class ToolError(Exception):
    """工具执行/参数错误(可被 Agent 感知并重试或降级)。"""


class PermissionDenied(Exception):
    pass


class QuotaExceeded(Exception):
    pass


class TaskAborted(Exception):
    """任务被人工接管/暂停/取消。"""


_WILDCARD = re.compile(r"[*%?\[\]{};|]")
ASSET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-:]{1,40}$")


def validate_asset_code(code: str) -> str:
    code = (code or "").strip().upper()
    if _WILDCARD.search(code) or not ASSET_RE.match(code):
        raise ToolError(f"设备编码非法(禁止通配/批量): {code!r}")
    return code


@dataclass
class TaskCtx:
    task_id: Any
    trace_id: str
    principal: security.Principal
    farm_code: Optional[str] = None
    emit: Callable[[str, str, dict], None] = lambda agent, typ, payload: None
    started: float = field(default_factory=time.time)
    tool_calls: int = 0
    steps: int = 0
    cancel_check: Callable[[], None] = lambda: None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check_quota(self, kind: str = "step") -> None:
        self.cancel_check()
        with self._lock:
            if kind == "tool":
                self.tool_calls += 1
            else:
                self.steps += 1
            if self.steps > settings.max_steps:
                raise QuotaExceeded(f"超过单任务最大步数 {settings.max_steps}")
            if self.tool_calls > settings.max_tool_calls:
                raise QuotaExceeded(f"超过单任务最大工具调用次数 {settings.max_tool_calls}")
        if time.time() - self.started > settings.max_task_seconds:
            raise QuotaExceeded(f"超过单任务最大时长 {settings.max_task_seconds}s")
        if llm.meter.snapshot()["tokens"] > settings.max_tokens_per_task:
            raise QuotaExceeded(f"超过单任务最大 Token {settings.max_tokens_per_task}")

    def require_farm_of_asset(self, asset_code: str) -> dict:
        a = db.q1("SELECT a.code, a.type, a.farm_id, a.model, f.code farm_code FROM assets a JOIN wind_farms f ON f.id=a.farm_id WHERE a.code=%s", (asset_code,))
        if not a:
            raise ToolError(f"设备不在台账: {asset_code}")
        if not self.principal.can_farm(a["farm_code"]):
            raise PermissionDenied(f"用户 {self.principal.username} 无权访问风场 {a['farm_code']} (ABAC)")
        return a

    def require_farm(self, farm_code: str) -> dict:
        f = db.q1("SELECT id, code, name FROM wind_farms WHERE code=%s", (farm_code,))
        if not f:
            raise ToolError(f"风场不存在: {farm_code}")
        if not self.principal.can_farm(f["code"]):
            raise PermissionDenied(f"用户 {self.principal.username} 无权访问风场 {farm_code} (ABAC)")
        return f


@dataclass
class Tool:
    name: str
    desc: str
    model: type[BaseModel]
    fn: Callable[[TaskCtx, Any], Any]
    mode: str = "read"                 # read | write_candidate | write_draft | write
    perm: Optional[str] = None         # 需要的用户权限


class Registry:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}
        self.grants: dict[str, set[str]] = {}
        self._fails: dict[str, list[float]] = {}

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def grant(self, agent: str, names: list[str]) -> None:
        missing = [n for n in names if n not in self.tools]
        if missing:
            raise KeyError(f"未注册的工具: {missing}")
        self.grants[agent] = set(names)

    def describe(self, agent: Optional[str] = None) -> list[dict]:
        names = self.grants.get(agent, set()) if agent else set(self.tools)
        return [{"name": t.name, "desc": t.desc, "mode": t.mode, "perm": t.perm, "schema": t.model.model_json_schema(),
                 "agents": sorted(a for a, g in self.grants.items() if t.name in g)} for t in self.tools.values() if t.name in names]

    def _breaker_open(self, name: str) -> bool:
        now = time.time()
        recent = [t for t in self._fails.get(name, []) if now - t < 30]
        self._fails[name] = recent
        return len(recent) >= 5

    def call(self, agent: str, name: str, args: dict, ctx: TaskCtx) -> Any:
        t0 = time.time()
        tool = self.tools.get(name)
        if tool is None:
            raise ToolError(f"工具不存在: {name}")
        if name not in self.grants.get(agent, set()):
            security.audit(ctx.task_id, ctx.trace_id, agent, "tool_denied", {"tool": name, "reason": "不在该 Agent 的最小权限白名单内"})
            ctx.emit(agent, "tool_denied", {"tool": name})
            raise PermissionDenied(f"Agent {agent} 无权调用工具 {name}")
        if tool.perm and not ctx.principal.can(tool.perm):
            security.audit(ctx.task_id, ctx.trace_id, agent, "tool_denied", {"tool": name, "reason": f"用户缺少权限 {tool.perm}"})
            raise PermissionDenied(f"用户角色 {ctx.principal.role} 无权限 {tool.perm}（工具 {name}）")
        ctx.check_quota("tool")
        if self._breaker_open(name):
            raise ToolError(f"工具 {name} 连续失败，熔断中，请稍后重试")
        try:
            parsed = tool.model.model_validate(args or {})
        except ValidationError as e:
            msg = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
            raise ToolError(f"工具 {name} 参数校验失败: {msg}")
        err: Optional[Exception] = None
        result: Any = None
        attempts = 2 if tool.mode == "read" else 1
        for i in range(attempts):
            try:
                result = tool.fn(ctx, parsed)
                err = None
                break
            except (PermissionDenied, ToolError, QuotaExceeded, TaskAborted):
                raise
            except Exception as e:  # 瞬时错误: 只读工具重试一次
                err = e
                time.sleep(0.2)
        ms = int((time.time() - t0) * 1000)
        if err is not None:
            self._fails.setdefault(name, []).append(time.time())
            security.audit(ctx.task_id, ctx.trace_id, agent, "tool_call", {"tool": name, "args": _short(args), "ok": False, "error": str(err)[:300], "ms": ms})
            ctx.emit(agent, "tool_call", {"tool": name, "args": _short(args), "ok": False, "error": str(err)[:200], "ms": ms})
            raise ToolError(f"工具 {name} 执行失败: {err}")
        summ = _short(result)
        security.audit(ctx.task_id, ctx.trace_id, agent, "tool_call", {"tool": name, "args": _short(args), "ok": True, "result": summ, "ms": ms, "mode": tool.mode})
        ctx.emit(agent, "tool_call", {"tool": name, "args": _short(args), "ok": True, "ms": ms, "mode": tool.mode, "summary": summ if len(summ) < 400 else summ[:400] + "…"})
        return result


def _short(o: Any, n: int = 700) -> str:
    try:
        s = json.dumps(o, ensure_ascii=False, default=str)
    except Exception:
        s = str(o)
    return s if len(s) <= n else s[:n] + "…"


registry = Registry()
