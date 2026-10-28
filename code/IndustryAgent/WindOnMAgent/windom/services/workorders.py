"""工单服务（工单 Agent 的后端，规范 8.2）：草稿/紧急工单、审批流（L1/L2/L3 双人确认）、派发、执行跟踪、响应/修复时长、
关闭与知识沉淀触发。Agent 只能创建草稿，状态推进均需有权限的人员。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from .. import db, security
from ..config import settings
from ..db import J
from ..ontology import WARNING_LEVELS
from . import resources, rules as rules_svc

UTC = dt.timezone.utc


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


class WorkflowError(Exception):
    pass


def _event(wo_id: int, actor: str, event: str, detail: Optional[dict] = None) -> None:
    db.insert("work_order_events", {"wo_id": wo_id, "actor": actor, "event": event, "detail": J(detail or {})}, returning="id")


def get(wo_id: int) -> Optional[dict]:
    return db.q1("SELECT * FROM work_orders WHERE id=%s", (wo_id,))


def get_by_no(no: str) -> Optional[dict]:
    return db.q1("SELECT * FROM work_orders WHERE wo_no=%s", (no,))


def _next_no(prefix: str) -> str:
    year = now().year
    last = db.scalar("SELECT max(substring(wo_no from '[0-9]+$')::int) FROM work_orders WHERE wo_no LIKE %s", (f"{prefix}-{year}-%",)) or 0
    return f"{prefix}-{year}-{last + 1:04d}"


def create_draft(*, farm_id: int, asset_code: str, comp_code: Optional[str], title: str, description: str, fault_key: Optional[str],
                 warning_level: int, risk_level: str, causes: list, actions: list, parts: list, crew: list, vessel: Optional[str],
                 window: Optional[dict], safety: dict, evidence: list, features: dict, alarm_id: Optional[int], alarm_time: Optional[dt.datetime],
                 task_id: Any, requester: str, wo_type: Optional[str] = None, source: str = "agent") -> dict:
    """工单 Agent 创建草稿。预警 ≥ 二级自动升级为紧急工单(规范 8.2.2a)。"""
    emergency = warning_level >= settings.emergency_level
    wo_type = wo_type or ("emergency" if emergency else "normal")
    prefix = "WO-EM" if wo_type == "emergency" else "WO"
    with db.tx():
        db.scalar("SELECT pg_advisory_xact_lock(727003)")
        wo = db.insert("work_orders", {
            "wo_no": _next_no(prefix), "farm_id": farm_id, "asset_code": asset_code, "comp_code": comp_code, "wo_type": wo_type,
            "status": "draft", "warning_level": warning_level, "risk_level": risk_level, "title": title, "description": description,
            "fault_key": fault_key, "causes": J(causes), "actions": J(actions), "parts": J(parts), "crew": J(crew), "vessel": vessel,
            "window_start": window["start"] if window else None, "window_end": window["end"] if window else None,
            "safety": J(safety), "evidence": J(evidence), "features": J(features), "alarm_id": alarm_id, "task_id": task_id,
            "source": source, "auto_generated": True, "alarm_time": alarm_time or now()})
        _event(wo["id"], requester, "created", {"type": wo_type, "level": warning_level, "risk": risk_level})
        if alarm_id:
            db.x("UPDATE alarms SET wo_id=%s WHERE id=%s", (wo["id"], alarm_id))
        if parts:
            codes = [p["code"] for p in parts if p.get("available", 0) >= 1]
            if codes:
                resources.reserve_parts(codes, farm_id)
    security.audit(task_id, None, "workorder-agent", "workorder_create_draft", {"wo_no": wo["wo_no"], "type": wo_type, "level": warning_level})
    return wo


def submit(wo_id: int, actor: str) -> dict:
    wo = _must(wo_id)
    if wo["status"] not in ("draft",):
        raise WorkflowError(f"工单状态 {wo['status']} 不可提交审批")
    level = _approval_level(wo)
    role = "approver" if level in ("L2", "L3") else "engineer"
    with db.tx():
        db.update("work_orders", "id", wo_id, {"status": "pending_approval", "submitted_at": now(), "risk_level": level})
        db.insert("approvals", {"wo_id": wo_id, "task_id": wo["task_id"], "level": level, "stage": 1, "required_role": role}, returning="id")
        _event(wo_id, actor, "submitted", {"approval_level": level})
    return _must(wo_id)


def _approval_level(wo: dict) -> str:
    """工单审批级别: 含 L3 动作 → L3(作业票+双人确认); 工单本身(紧急/普通) → L2 授权人员审批。"""
    if wo.get("risk_level") == "L3" or (wo.get("safety") or {}).get("l3_actions"):
        return "L3"
    return "L2"


def decide(wo_id: int, approver: security.Principal, decision: str, comment: str = "", modifications: Optional[dict] = None) -> dict:
    """人工审批。L3: 需两名不同授权人员分别确认(双人确认)，并要求作业票号。"""
    wo = _must(wo_id)
    if wo["status"] != "pending_approval":
        raise WorkflowError(f"工单状态为 {wo['status']}，不在审批中")
    ap = db.q1("SELECT * FROM approvals WHERE wo_id=%s AND status='pending' ORDER BY stage LIMIT 1", (wo_id,))
    if not ap:
        raise WorkflowError("无待审批记录")
    need = f"approve:{ap['level']}"
    if not approver.can(need):
        raise PermissionError(f"当前角色无 {ap['level']} 审批权限")
    if not approver.can_farm(_farm_code(wo["farm_id"])):
        raise PermissionError("无该风场的审批权限(ABAC)")
    if decision not in ("approve", "reject", "modify"):
        raise ValueError("decision 必须为 approve/reject/modify")
    with db.tx():
        if decision == "reject":
            db.update("approvals", "id", ap["id"], {"status": "rejected", "approver": approver.username, "comment": comment, "decided_at": now()})
            db.update("work_orders", "id", wo_id, {"status": "rejected"})
            _release(wo)
            if wo["task_id"]:
                db.x("UPDATE agent_tasks SET status='Rejected', finished_at=now(), updated_at=now() WHERE id=%s", (wo["task_id"],))
            _event(wo_id, approver.username, "rejected", {"comment": comment})
            security.audit(wo["task_id"], None, approver.username, "approval_reject", {"wo": wo["wo_no"], "comment": comment})
            return _must(wo_id)
        if decision == "modify" and modifications:
            _apply_mods(wo, modifications)
        if ap["level"] == "L3":
            prev = db.q1("SELECT approver FROM approvals WHERE wo_id=%s AND status IN ('approved','modified') AND stage=1", (wo_id,)) if ap["stage"] == 2 else None
            if ap["stage"] == 2 and prev and prev["approver"] == approver.username:
                raise PermissionError("L3 双人确认须由两名不同的授权人员完成")
            permit_no = (modifications or {}).get("permit_no") or ap.get("permit_no")
            if not permit_no:
                raise WorkflowError("L3 高风险作业须提供作业票号(permit_no)")
            db.update("approvals", "id", ap["id"], {"status": "approved", "approver": approver.username, "comment": comment,
                                                     "modifications": J(modifications) if modifications else None, "permit_no": permit_no, "decided_at": now()})
            if ap["stage"] == 1:
                db.insert("approvals", {"wo_id": wo_id, "task_id": wo["task_id"], "level": "L3", "stage": 2, "required_role": "approver", "permit_no": permit_no}, returning="id")
                _event(wo_id, approver.username, "approved_stage1", {"permit_no": permit_no})
                return _must(wo_id)
            if not db.q1("SELECT 1 FROM work_permits WHERE permit_no=%s", (permit_no,)):
                db.insert("work_permits", {"permit_no": permit_no, "wo_id": wo_id, "kind": "high_risk", "status": "issued",
                                           "holder": prev["approver"] if prev else None, "second_signer": approver.username}, returning="id")
        else:
            db.update("approvals", "id", ap["id"], {"status": "modified" if decision == "modify" else "approved", "approver": approver.username,
                                                     "comment": comment, "modifications": J(modifications) if modifications else None, "decided_at": now()})
        db.update("work_orders", "id", wo_id, {"status": "approved", "approved_at": now()})
        if wo["task_id"]:
            db.x("UPDATE agent_tasks SET status='Completed', finished_at=coalesce(finished_at, now()), updated_at=now() WHERE id=%s AND status='WaitingApproval'", (wo["task_id"],))
        _event(wo_id, approver.username, "approved", {"comment": comment, "modified": bool(modifications)})
        security.audit(wo["task_id"], None, approver.username, "approval_approve", {"wo": wo["wo_no"], "level": ap["level"]})
    out = _must(wo_id)
    # 审批通过后自动派发(目标自动派发率 ≥95%: 无需额外人工动作)
    try:
        out = dispatch(wo_id, "workorder-agent", auto=True)
    except WorkflowError:
        pass
    return out


def _apply_mods(wo: dict, mods: dict) -> None:
    upd: dict = {}
    if "description" in mods:
        upd["description"] = mods["description"]
    if "crew" in mods:
        upd["crew"] = J(mods["crew"])
    if "window_start" in mods and "window_end" in mods:
        upd["window_start"], upd["window_end"] = mods["window_start"], mods["window_end"]
    if upd:
        db.update("work_orders", "id", wo["id"], upd)


def dispatch(wo_id: int, actor: str, auto: bool = False) -> dict:
    wo = _must(wo_id)
    if wo["status"] != "approved":
        raise WorkflowError(f"仅已审批工单可派发(当前 {wo['status']})")
    ts_ = now()
    resp = (ts_ - wo["alarm_time"]).total_seconds() / 60.0 if wo["alarm_time"] else None
    db.update("work_orders", "id", wo_id, {"status": "dispatched", "dispatched_at": ts_, "auto_dispatched": auto,
                                          "response_minutes": resp})
    _event(wo_id, actor, "dispatched", {"auto": auto, "response_minutes": resp})
    rules_svc.notify(wo["farm_id"], "info", f"工单已派发：{wo['wo_no']} {wo['title']}", f"响应用时 {resp:.1f} 分钟" if resp is not None else "",
                     "workorder", str(wo_id))
    security.audit(wo["task_id"], None, actor, "workorder_dispatch", {"wo": wo["wo_no"], "auto": auto, "response_minutes": resp})
    return _must(wo_id)


def start(wo_id: int, actor: security.Principal) -> dict:
    wo = _must(wo_id)
    if wo["status"] != "dispatched":
        raise WorkflowError(f"仅已派发工单可开始执行(当前 {wo['status']})")
    if not actor.can("wo:execute"):
        raise PermissionError("无工单执行权限")
    db.update("work_orders", "id", wo_id, {"status": "in_progress", "started_at": now()})
    _event(wo_id, actor.username, "started")
    return _must(wo_id)


def close(wo_id: int, actor: security.Principal, *, root_cause_key: Optional[str], root_cause: str, actual_actions: list[dict],
          result: str, effective: bool, notes: str = "") -> dict:
    wo = _must(wo_id)
    if wo["status"] not in ("in_progress", "dispatched"):
        raise WorkflowError(f"工单状态 {wo['status']} 不可关闭")
    if not actor.can("wo:close"):
        raise PermissionError("无工单关闭权限")
    ts_ = now()
    start = wo["started_at"] or wo["dispatched_at"] or ts_
    repair = (ts_ - start).total_seconds() / 60.0
    resp = wo["response_minutes"]
    with db.tx():
        db.update("work_orders", "id", wo_id, {"status": "closed", "closed_at": ts_, "root_cause": root_cause, "root_cause_key": root_cause_key,
                                              "actual_actions": J(actual_actions), "result": result, "effective": effective,
                                              "repair_minutes": repair, "description": (wo["description"] or "") + (f"\n关闭备注：{notes}" if notes else "")})
        _event(wo_id, actor.username, "closed", {"root_cause": root_cause, "effective": effective})
        # 消耗预占备件
        codes = [p["code"] for p in (wo["parts"] or [])]
        if codes:
            resources.release_parts(codes, wo["farm_id"], consume=True)
        # 关联告警闭环
        if wo["alarm_id"]:
            db.x("UPDATE alarms SET status='closed', closed_at=now() WHERE id=%s", (wo["alarm_id"],))
        db.x("UPDATE trip_plans SET status='done' WHERE %s = ANY(wo_ids) AND NOT EXISTS (SELECT 1 FROM work_orders w WHERE w.id = ANY(trip_plans.wo_ids) AND w.id<>%s AND w.status NOT IN ('closed','cancelled','rejected'))",
             (wo_id, wo_id))
    if wo["task_id"]:
        db.x("UPDATE agent_tasks SET status='Completed', finished_at=coalesce(finished_at, now()), updated_at=now() WHERE id=%s AND status='WaitingApproval'", (wo["task_id"],))
    security.audit(wo["task_id"], None, actor.username, "workorder_close", {"wo": wo["wo_no"], "root_cause": root_cause, "repair_minutes": repair,
                                                                           "response_minutes": resp, "effective": effective})
    return _must(wo_id)


def cancel(wo_id: int, actor: str, reason: str = "") -> dict:
    wo = _must(wo_id)
    if wo["status"] in ("closed", "cancelled"):
        raise WorkflowError("工单已结束")
    db.update("work_orders", "id", wo_id, {"status": "cancelled"})
    _release(wo)
    _event(wo_id, actor, "cancelled", {"reason": reason})
    return _must(wo_id)


def _release(wo: dict) -> None:
    codes = [p["code"] for p in (wo["parts"] or []) if p.get("available", 0) >= 1]
    if codes:
        resources.release_parts(codes, wo["farm_id"])


def _must(wo_id: int) -> dict:
    wo = get(wo_id)
    if not wo:
        raise WorkflowError(f"工单不存在: {wo_id}")
    return wo


def _farm_code(farm_id: int) -> str:
    return db.scalar("SELECT code FROM wind_farms WHERE id=%s", (farm_id,))


def events(wo_id: int) -> list[dict]:
    return db.q("SELECT * FROM work_order_events WHERE wo_id=%s ORDER BY id", (wo_id,))


def list_orders(farm_code: Optional[str] = None, status: Optional[str] = None, limit: int = 100, farms: Optional[list[str]] = None) -> list[dict]:
    return db.q("""SELECT w.*, f.code farm_code FROM work_orders w JOIN wind_farms f ON f.id=w.farm_id
                   WHERE (%s::text IS NULL OR f.code=%s) AND (%s::text IS NULL OR w.status=%s)
                     AND (%s::text[] IS NULL OR f.code = ANY(%s))
                   ORDER BY w.created_at DESC LIMIT %s""", (farm_code, farm_code, status, status, farms, farms, limit))


def kpis(farm_id: Optional[int] = None, since: Optional[dt.datetime] = None, until: Optional[dt.datetime] = None) -> dict:
    """规范 4e / 8.2.2b 绩效指标：自动派发率、响应时间、修复时长(MTTR)。"""
    since = since or (now() - dt.timedelta(days=30))
    until = until or now()
    r = db.q1("""SELECT count(*) total,
                        count(*) FILTER (WHERE status NOT IN ('draft','rejected','cancelled')) active_total,
                        count(*) FILTER (WHERE wo_type='emergency') emergencies,
                        count(*) FILTER (WHERE auto_dispatched) auto_dispatched,
                        count(*) FILTER (WHERE dispatched_at IS NOT NULL OR status='closed') dispatched,
                        count(*) FILTER (WHERE status='closed') closed,
                        avg(response_minutes) FILTER (WHERE response_minutes IS NOT NULL AND wo_type='emergency') avg_resp_em,
                        count(*) FILTER (WHERE wo_type='emergency' AND response_minutes IS NOT NULL AND response_minutes <= %s) resp_ok,
                        count(*) FILTER (WHERE wo_type='emergency' AND response_minutes IS NOT NULL) resp_n,
                        avg(repair_minutes) FILTER (WHERE status='closed') mttr
                 FROM work_orders WHERE (%s::int IS NULL OR farm_id=%s) AND created_at >= %s AND created_at < %s""",
              (settings.response_sla_min, farm_id, farm_id, since, until))
    auto_pool = db.scalar("""SELECT count(*) FROM work_orders WHERE (%s::int IS NULL OR farm_id=%s) AND created_at >= %s AND created_at < %s
                             AND auto_generated AND status IN ('dispatched','in_progress','closed')""", (farm_id, farm_id, since, until)) or 0
    # 自动派发率: 已通过审批进入执行的 Agent 工单中, 派发动作由系统自动完成的占比
    auto_rate = (r["auto_dispatched"] / auto_pool) if auto_pool else None
    # 对历史导入工单, 以其响应时长计入响应指标
    return {"total": r["total"], "emergencies": r["emergencies"], "closed": r["closed"], "mttr_minutes": r["mttr"],
            "avg_response_minutes_emergency": r["avg_resp_em"],
            "response_sla_rate": (r["resp_ok"] / r["resp_n"]) if r["resp_n"] else None, "response_sla_minutes": settings.response_sla_min,
            "auto_dispatch_rate": auto_rate, "auto_dispatch_target": settings.auto_dispatch_target,
            "auto_dispatched": r["auto_dispatched"], "auto_pool": auto_pool}
