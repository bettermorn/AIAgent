"""总控 Agent（Orchestrator，文档 4.2~4.3, 4.8, 6.4）。

职责：意图识别 → 任务拆解 → 调度专业 Agent(串行/并行/条件路由/否决) → 反思 → 汇总输出。
- 状态机：Received → Planning → Executing → Reflecting → SafetyCheck → WaitingApproval/Completed/Rejected/HumanTakeover
- Checkpoint：每个节点后将状态写入 agent_checkpoints（PostgreSQL），支持回溯与恢复
- 人在回路：L1/L2 生成待审批工单后任务挂起 WaitingApproval（审批在工单中心完成，审批结果回写任务）
- 总控 Agent 不直接访问业务系统，只调用子 Agent
"""
from __future__ import annotations

import concurrent.futures as cf
import contextvars
import datetime as dt
import json
import logging
import threading
import time
import uuid
from typing import Any, Callable, Optional

from .. import db, llm, security
from ..config import settings
from ..db import J
from ..ontology import COMP_NAME, FAULTS, SENSOR_NAME, WARNING_LEVELS
from ..tools.registry import PermissionDenied, QuotaExceeded, TaskAborted, TaskCtx, ToolError
from . import nlu
from .specialists import (DiagnosisAgent, ImprovementAgent, KnowledgeAgent, ResourceAgent, RetrievalAgent, SafetyAgent, WorkOrderAgent)

log = logging.getLogger("windom.orchestrator")
UTC = dt.timezone.utc

TERMINAL = {"Completed", "Rejected", "Failed"}
_pool = cf.ThreadPoolExecutor(max_workers=16, thread_name_prefix="agent")
_subscribers: dict[str, list[Callable[[dict], None]]] = {}
_sub_lock = threading.Lock()
_flags: dict[str, str] = {}   # task_id -> "pause" | "cancel"


# ----------------------------------------------------------------------------- 事件总线
def subscribe(task_id: str, cb: Callable[[dict], None]) -> Callable[[], None]:
    with _sub_lock:
        _subscribers.setdefault(task_id, []).append(cb)

    def unsub():
        with _sub_lock:
            if cb in _subscribers.get(task_id, []):
                _subscribers[task_id].remove(cb)
    return unsub


def _publish(task_id: str, ev: dict) -> None:
    with _sub_lock:
        cbs = list(_subscribers.get(task_id, []))
    for cb in cbs:
        try:
            cb(ev)
        except Exception:
            pass


class TaskRunner:
    def __init__(self, task_id: str, principal: security.Principal):
        self.task_id = task_id
        self.principal = principal
        row = db.q1("SELECT * FROM agent_tasks WHERE id=%s", (task_id,))
        self.task = row
        self.seq = 0
        self._seq_lock = threading.Lock()
        self.step = 0
        self.ctx = TaskCtx(task_id=task_id, trace_id=row["trace_id"], principal=principal, farm_code=row["farm_code"],
                           emit=self.emit, cancel_check=self._check_cancel)
        self.sources: list[dict] = []
        self.state: dict[str, Any] = {}

    # ---- 基础设施 ----
    def emit(self, agent: str, typ: str, payload: dict) -> None:
        with self._seq_lock:
            self.seq += 1
            seq = self.seq
        ev = {"task_id": str(self.task_id), "seq": seq, "ts": dt.datetime.now(UTC).isoformat(), "agent": agent, "type": typ, "payload": payload}
        try:
            db.insert("agent_events", {"task_id": self.task_id, "seq": seq, "agent": agent, "type": typ, "payload": J(payload)}, returning="id")
        except Exception:
            log.exception("事件写入失败")
        _publish(str(self.task_id), ev)

    def _check_cancel(self) -> None:
        f = _flags.get(str(self.task_id))
        if f == "cancel":
            raise TaskAborted("任务已被人工终止")
        if f == "pause":
            raise TaskAborted("任务已被人工接管/暂停")

    def set_status(self, status: str, **extra) -> None:
        upd = {"status": status, "updated_at": dt.datetime.now(UTC), **extra}
        if status in TERMINAL:
            upd["finished_at"] = dt.datetime.now(UTC)
        db.update("agent_tasks", "id", self.task_id, upd)
        self.emit("orchestrator", "state", {"status": status})

    def checkpoint(self, node: str) -> None:
        self.step += 1
        snap = json.loads(json.dumps(self.state, default=str, ensure_ascii=False))
        # 状态过大时只保留键与摘要
        if len(json.dumps(snap, ensure_ascii=False)) > 200_000:
            snap = {k: (v if len(json.dumps(v, ensure_ascii=False, default=str)) < 4000 else "<omitted>") for k, v in snap.items()}
        db.insert("agent_checkpoints", {"task_id": self.task_id, "step": self.step, "node": node, "state": J(snap)}, returning="step")
        usage = llm.meter.snapshot()
        db.update("agent_tasks", "id", self.task_id, {"steps": self.step, "tool_calls": self.ctx.tool_calls, "tokens": usage["tokens"],
                                                       "models": J(usage["models"]), "updated_at": dt.datetime.now(UTC)})

    def run_agent(self, agent, fn: str, *a, **kw):
        """调用子 Agent。每次调用后保存检查点。"""
        self.ctx.check_quota("step")
        self.emit("orchestrator", "dispatch", {"to": agent.name, "task": fn})
        t0 = time.time()
        try:
            res = getattr(agent, fn)(*a, **kw)
        finally:
            pass
        self.emit("orchestrator", "agent_done", {"from": agent.name, "ms": int((time.time() - t0) * 1000)})
        self.state[f"{agent.name}.{fn}"] = res
        self.checkpoint(f"{agent.name}.{fn}")
        return res

    def add_sources(self, evidence: list[dict]) -> None:
        have = {e["id"] for e in self.sources}
        for e in evidence:
            if e["id"] not in have:
                self.sources.append(e)
                have.add(e["id"])

    # ---- 主流程 ----
    def run(self) -> dict:
        llm.meter.start()
        t = self.task
        text = t["query"]
        try:
            self.set_status("Received")
            clean, hits = security.guard_input(text)
            self.emit("orchestrator", "input_guard", {"injection_hits": hits, "len": len(clean)})
            if hits:
                security.audit(self.task_id, t["trace_id"], self.principal.username, "input_blocked", {"hits": hits})
                msg = "检测到疑似提示注入/越权指令（" + "；".join(hits) + "），本次请求已被安全护栏拒绝。请直接描述运维问题；涉及停机、调参、绕过审批等操作须走正式流程。"
                return self.finish("Rejected", {"answer": msg, "rejected": True, "reason": "prompt_injection"}, risk="L4")
            self.set_status("Planning")
            kind = t["kind"]
            payload = (t["state"] or {}).get("input") or {}
            if kind in ("auto", "ask"):
                nl = self.perceive(clean, payload)
                kind = nl["intent"]
            handler = {"qa": self.flow_qa, "diagnose": self.flow_diagnose, "alarm": self.flow_diagnose, "stats": self.flow_stats,
                       "efficiency": self.flow_efficiency, "report": self.flow_report, "schedule": self.flow_schedule,
                       "improve": self.flow_improve, "knowledge_extract": self.flow_knowledge}.get(kind)
            if not handler:
                return self.finish("Failed", {"answer": f"不支持的任务类型 {kind}"}, error="unsupported")
            self.set_status("Executing", intent=J({**(self.task.get("intent") or {}), "resolved": kind}))
            res = handler(clean, payload)
            return res
        except TaskAborted as e:
            self.set_status("HumanTakeover", error=str(e))
            return {"status": "HumanTakeover", "error": str(e)}
        except QuotaExceeded as e:
            self.emit("orchestrator", "quota_exceeded", {"error": str(e)})
            return self.finish("Failed", {"answer": f"任务已被安全熔断：{e}。已保存当前进度，请人工接管。"}, error=str(e), status_override="HumanTakeover")
        except PermissionDenied as e:
            security.audit(self.task_id, t["trace_id"], self.principal.username, "permission_denied", {"error": str(e)})
            return self.finish("Rejected", {"answer": f"权限校验未通过：{e}", "rejected": True, "reason": "permission"}, risk="L4", error=str(e))
        except llm.LLMError as e:
            log.exception("LLM 失败")
            return self.finish("Failed", {"answer": f"大模型服务不可用：{e}。其余结构化证据已保留，请稍后重试。"}, error=str(e))
        except Exception as e:
            log.exception("任务失败")
            return self.finish("Failed", {"answer": f"任务执行失败：{e}"}, error=str(e))

    def perceive(self, text: str, payload: dict) -> dict:
        """感知层：实体识别、意图识别。"""
        assets, missing = nlu.extract_assets(text)
        farm = payload.get("farm") or nlu.extract_farm(text)
        intent = nlu.classify_intent(text, bool(assets) or bool(payload.get("asset")))
        comp = nlu.extract_component(text)
        fault = payload.get("fault_key") or nlu.resolve_fault(text, comp)
        info = {"intent": payload.get("intent") or intent["intent"], "assets": assets, "missing_assets": missing, "farm": farm,
                "component": comp, "fault_key": fault, "by": intent["by"]}
        self.state["perception"] = info
        self.emit("orchestrator", "perceive", info)
        db.update("agent_tasks", "id", self.task_id, {"intent": J(info)})
        return info

    def farm_of_asset(self, asset: str) -> dict:
        return self.ctx.require_farm_of_asset(asset)

    # ---- 收尾 ----
    def finish(self, status: str, result: dict, *, risk: Optional[str] = None, error: Optional[str] = None,
               wo_id: Optional[int] = None, alarm_id: Optional[int] = None, status_override: Optional[str] = None) -> dict:
        usage = llm.meter.snapshot()
        result.setdefault("sources", self.sources)
        result["usage"] = usage
        upd = {"result": J(result), "risk_level": risk, "tokens": usage["tokens"], "models": J(usage["models"]),
               "tool_calls": self.ctx.tool_calls, "steps": self.step, "error": error}
        if wo_id:
            upd["wo_id"] = wo_id
        if alarm_id:
            upd["alarm_id"] = alarm_id
        db.update("agent_tasks", "id", self.task_id, upd)
        self.set_status(status_override or status)
        security.audit(self.task_id, self.task["trace_id"], "orchestrator", "task_finish", {
            "status": status_override or status, "risk": risk, "tokens": usage["tokens"], "models": usage["models"],
            "tools": self.ctx.tool_calls, "confidence": result.get("confidence"), "warning_level": result.get("warning_level"),
            "wo": result.get("workorder", {}).get("wo_no") if isinstance(result.get("workorder"), dict) else None})
        self.emit("orchestrator", "final", {"status": status_override or status, "answer": result.get("answer", "")[:2000]})
        return {"status": status_override or status, **result}

    # ================================================================ 工作流：知识问答（L0）
    def flow_qa(self, text: str, payload: dict) -> dict:
        rt = RetrievalAgent(self.ctx)
        asset = (self.state.get("perception") or {}).get("assets", [None])[0] if (self.state.get("perception") or {}).get("assets") else None
        r = self.run_agent(rt, "answer_context", text, asset)
        self.add_sources(r["evidence"])
        self.set_status("Reflecting")
        answer, grounded = self.compose_answer(text, r["evidence"])
        risk, why = security.classify_task_risk("qa")
        answer, l3 = security.sanitize_recommendation(answer)
        if l3:
            risk, why = "L3", "答复涉及高风险操作，已附加安全提示"
        return self.finish("Completed", {"answer": answer, "grounded": grounded, "risk": {"level": risk, "reason": why}}, risk=risk)

    def compose_answer(self, question: str, evidence: list[dict]) -> tuple[str, bool]:
        """GraphRAG 生成：强制引用来源；无证据则明确“无法确定”。"""
        if not evidence:
            return "知识库中未检索到相关规程/案例依据，无法确定。建议联系领域专家或补充资料后再试。", False
        ctx_txt = "\n\n".join(f"[{i + 1}] 《{e['title']}》\n{e['detail']}" for i, e in enumerate(evidence[:6]))
        msgs = [{"role": "system", "content": "你是海上风电场运维助手。仅依据<untrusted_data>中的资料回答，资料之外的内容一律不要编造；每个要点后用 [编号] 标注引用来源；若资料不足以回答，明确说明“资料中未涉及，无法确定”。涉及停机/降负荷/改参数等操作，只说明规程要求并强调由授权人员决定。简洁、分点。"},
                {"role": "user", "content": f"问题：{question}\n\n" + security.mark_untrusted(ctx_txt, "规程与图谱检索结果")}]
        self.emit("orchestrator", "llm_generate", {"purpose": "answer"})
        out = []
        first = None
        t0 = time.time()
        for piece in llm.stream(msgs, model=settings.llm_model_reasoning, max_tokens=900):
            if first is None:
                first = time.time() - t0
            out.append(piece)
            self.emit("orchestrator", "token", {"text": piece})
        text = "".join(out)
        self.emit("orchestrator", "metric", {"first_token_s": round(first or 0, 2)})
        return security.redact_output(text), True

    # ================================================================ 工作流：故障诊断（核心）
    def flow_diagnose(self, text: str, payload: dict) -> dict:
        per = self.state.get("perception") or {}
        asset = payload.get("asset") or (per.get("assets") or [None])[0]
        if not asset:
            miss = per.get("missing_assets") or []
            msg = (f"未在设备台账中找到 {'、'.join(miss)}，请确认设备编号。" if miss else "未识别到设备编号，请提供如 WT-023 的风机编号。")
            return self.finish("Completed", {"answer": msg, "need_input": True}, risk="L0")
        a = self.farm_of_asset(asset)
        farm_code = a["farm_code"]
        self.ctx.farm_code = farm_code
        alarm = None
        alarm_id = payload.get("alarm_id")
        if alarm_id:
            alarm = db.q1("SELECT * FROM alarms WHERE id=%s", (alarm_id,))
        fault_key = payload.get("fault_key") or per.get("fault_key") or (alarm["fault_key"] if alarm else None)
        if not fault_key and not alarm:
            op = db.q1("SELECT id, fault_key FROM alarms WHERE asset_code=%s AND status IN ('open','acknowledged') ORDER BY level DESC LIMIT 1", (asset,))
            if op:
                fault_key, alarm_id, alarm = op["fault_key"], op["id"], db.q1("SELECT * FROM alarms WHERE id=%s", (op["id"],))
        question = text if not payload.get("alarm_id") else f"告警 {alarm['title']}"

        # ---- 第1步: 诊断(串行先行, 以确定故障类型) 与 检索(并行)
        dg, rt = DiagnosisAgent(self.ctx), RetrievalAgent(self.ctx)
        d = self.run_agent(dg, "analyze", asset, fault_key, 120, alarm)
        if d.get("healthy"):
            return self.finish("Completed", {"answer": f"{asset}：{d['message']}", "healthy": True, "diagnosis": None}, risk="L0")
        fault_key = d["fault_key"]
        diag = d.get("diag")
        if not diag:
            return self.finish("Completed", {"answer": f"{asset} 诊断模型暂不可用：{d.get('error') or '未知'}。已转人工处理。", "diagnosis": None}, risk="L4")
        # 并行取证(与诊断相互独立的检索; 诊断结果已得, 证据与资源并行)
        ctxv = contextvars.copy_context()
        f_rt = _pool.submit(ctxv.run, self.run_agent, rt, "gather", asset, fault_key, question)
        ev = f_rt.result()
        self.add_sources(ev["evidence"])
        self.set_status("Reflecting")

        # ---- 反思: 证据充分性/一致性/置信度
        level = int(d["warning_level"])
        if alarm:  # 由告警触发：预警等级不得低于触发告警的等级（响应时限按告警等级计）
            level = max(level, int(alarm["level"]))
        conf = float(diag["confidence"])
        causes = diag["causes"]
        top = causes[0] if causes else None
        evidence_n = len(ev["evidence"])
        risk, risk_reason = security.classify_task_risk("diagnose", confidence=conf, evidence_count=evidence_n, rule_conflict=bool(d["rule_conflict"]))
        refl = self.ctx and {"conf": conf, "evidence": evidence_n, "rule_conflict": d["rule_conflict"], "level": level}
        self.emit("orchestrator", "reflect", refl)
        if level == 0 and (diag.get("current") is None or diag["trend"].get("available") is False):
            risk, risk_reason = "L4", "无有效观测数据"
        # 低置信/规则冲突 → L4 转人工, 不继续生成工单(停止推理)
        if risk == "L4":
            ans = self.compose_diagnosis_answer(asset, fault_key, diag, ev, d, None, None, conf, level, handoff=True, reason=risk_reason)
            return self.finish("Completed", {"answer": ans, "diagnosis": self._diag_view(diag, d), "confidence": conf, "warning_level": level,
                                             "risk": {"level": "L4", "reason": risk_reason}, "handoff": True}, risk="L4", alarm_id=alarm_id)

        # ---- 措施选择: 取排名最前原因的首选措施(并避免 L3 动作被 Agent 执行)
        actions: list[dict] = []
        for c in causes[:2]:
            if c["actions"]:
                act = c["actions"][0]
                if act["key"] not in {x["key"] for x in actions}:
                    actions.append({**act, "cause": c["name"]})
        rs_agent, sf_agent = ResourceAgent(self.ctx), SafetyAgent(self.ctx)
        # ---- 资源(串行依赖措施) → 安全(依赖资源方案, 拥有否决权)
        plan = self.run_agent(rs_agent, "plan_trip", farm_code, asset, actions[:1])["plan"] if actions else {"feasible": True, "parts": [], "team": {}}
        sf = self.run_agent(sf_agent, "review", farm_code, actions[:1], plan, asset) if actions else {"verdict": "pass", "detail": {}, "ais_notice": []}
        verdict = sf["verdict"]
        # 风险再分级(含 L3)
        risk, risk_reason = security.classify_task_risk("diagnose", confidence=conf, actions=[{"name": a["name"]} for a in actions[:1]], creates_wo=True,
                                                        evidence_count=evidence_n)
        if verdict == "veto":
            ans = self.compose_diagnosis_answer(asset, fault_key, diag, ev, d, plan, sf, conf, level, veto=True)
            self.set_status("SafetyCheck")
            return self.finish("Rejected", {"answer": ans, "diagnosis": self._diag_view(diag, d), "safety": sf, "resource_plan": _plan_view(plan),
                                            "confidence": conf, "warning_level": level, "risk": {"level": risk, "reason": "安全 Agent 否决: " + "；".join(sf["detail"].get("vetoes", []))},
                                            "veto": True}, risk=risk, alarm_id=alarm_id)
        self.set_status("SafetyCheck")

        # ---- 工单草稿（预警≥二级 → 紧急工单）
        evid_refs = [{"id": e["id"], "title": e["title"]} for e in ev["evidence"] if e["type"] != "kg"][:12]
        wo_agent = WorkOrderAgent(self.ctx)
        desc = self._wo_description(asset, fault_key, diag, causes, actions, d)
        features = {"dirs": {s: v["dir"] for s, v in (diag.get("deviations") or {}).items()},
                    "top_cause": top["key"] if top else None, "confidence": conf}
        w = self.run_agent(wo_agent, "draft", asset=asset, fault_key=fault_key, warning_level=max(level, 1), risk=risk if risk in ("L1", "L2", "L3") else "L2",
                           causes=[{"key": c["short_key"], "name": c["name"], "probability": c["probability"]} for c in causes[:3]], actions=actions[:2],
                           plan=plan, safety={"verdict": verdict, **{k: sf["detail"].get(k) for k in ("conditions", "required_permits", "l3_actions")}},
                           evidence=evid_refs, features=features, alarm_id=alarm_id, description=desc)
        wo = w["workorder"] if isinstance(w.get("workorder"), dict) and "wo_id" in w["workorder"] else None
        if wo and alarm_id:
            db.x("UPDATE alarms SET task_id=%s, wo_id=%s WHERE id=%s", (self.task_id, wo["wo_id"], alarm_id))
        ans = self.compose_diagnosis_answer(asset, fault_key, diag, ev, d, plan, sf, conf, level, wo=wo)
        ans, l3 = security.sanitize_recommendation(ans)
        status = "WaitingApproval" if wo else "Completed"
        if wo:
            db.update("agent_tasks", "id", self.task_id, {"wo_id": wo["wo_id"]})
            # 竞态保护：任务收尾前工单若已被人工处理(审批/驳回)，直接采用终态而非“待审批”
            cur = db.q1("SELECT status FROM work_orders WHERE id=%s", (wo["wo_id"],))
            if cur and cur["status"] != "pending_approval" and cur["status"] != "draft":
                status = "Rejected" if cur["status"] in ("rejected", "cancelled") else "Completed"
        return self.finish(status, {
            "answer": ans, "diagnosis": self._diag_view(diag, d), "safety": sf, "resource_plan": _plan_view(plan), "workorder": wo,
            "confidence": conf, "warning_level": level, "warning_name": WARNING_LEVELS.get(level, ("正常",))[0],
            "risk": {"level": risk, "reason": risk_reason}, "response_timer": {"started_at": dt.datetime.now(UTC).isoformat(), "sla_min": settings.response_sla_min} if wo and wo.get("type") == "emergency" else None},
            risk=risk, wo_id=wo["wo_id"] if wo else None, alarm_id=alarm_id)

    # ---- 诊断输出 ----
    def _diag_view(self, diag: dict, d: dict) -> dict:
        return {"asset": diag["asset"], "fault_key": diag["fault_key"], "fault_name": diag["fault_name"], "primary_sensor": diag["primary_sensor"],
                "current": diag["current"], "warning_level": d["warning_level"], "causes": [
                    {k: c[k] for k in ("key", "name", "probability", "features", "checks")} | {"actions": [{"name": a["name"], "key": a["key"]} for a in c["actions"]]}
                    for c in diag["causes"]],
                "deviations": {k: {kk: (round(vv, 2) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in diag["deviations"].items()},
                "anomaly_score": diag["anomaly_score"], "trend": diag["trend"], "health": diag["health"], "rule": diag["rule"], "model_version": diag["model_version"],
                "rule_results": [r for r in (d.get("rules") or {}).get("results", []) if r["level"] > 0]}

    def _wo_description(self, asset: str, fault_key: str, diag: dict, causes: list, actions: list, d: dict) -> str:
        cur = diag["current"] or {}
        lines = [f"{asset} {FAULTS[fault_key]['name']}。当前{SENSOR_NAME.get(diag['primary_sensor'])}均值 {cur.get('mean', 0):.1f}。",
                 "疑似原因（后验概率）：" + "；".join(f"{c['name']}({c['probability']:.0%})" for c in causes[:3]),
                 "建议措施：" + "；".join(a["name"] for a in actions[:2])]
        return "\n".join(lines)

    def compose_diagnosis_answer(self, asset, fault_key, diag, ev, d, plan, sf, conf, level, *, wo=None, handoff=False, veto=False, reason="") -> str:
        """LLM 生成带证据与不确定性的诊断说明；输入全部为结构化事实, 不允许模型自行编造数值。"""
        top = diag["causes"][:3]
        cur = diag["current"] or {}
        facts = {
            "asset": asset, "fault": FAULTS[fault_key]["name"], "warning_level": WARNING_LEVELS.get(level, ("正常",))[0],
            "primary_sensor": SENSOR_NAME.get(diag["primary_sensor"]), "trend": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in diag["trend"].items()},
            "current_mean": round(cur.get("mean", 0), 2),
            "deviation_vs_peers": {SENSOR_NAME.get(k, k): {"现值": round(v["value"], 1), "同场基线": round(v["baseline"], 1), "偏离方向": {1: "偏高", -1: "偏低", 0: "正常"}[v["dir"]]}
                                   for k, v in diag["deviations"].items()},
            "candidate_causes": [{"原因": c["name"], "后验概率": c["probability"], "建议检查": c["checks"], "措施": [a["name"] for a in c["actions"]]} for c in top],
            "confidence": conf, "health_score": diag["health"].get("overall"), "anomaly_score": diag["anomaly_score"],
            "rule_levels": [{"规则": r["rule"], "级别": r["level_name"], "值": round(r["value"], 1)} for r in (d.get("rules") or {}).get("results", []) if r["level"] > 0],
        }
        refs = [f"[{i + 1}] {e['title']}：{e['detail'][:140]}" for i, e in enumerate([e for e in ev["evidence"] if e["type"] != "kg"][:6])]
        extra = ""
        if plan:
            extra += f"\n资源方案：备件={[(p['code'], p['name'], '有库存' if p['ok'] else '缺货') for p in plan.get('parts', [])]}；" \
                     f"班组={[c['name'] for c in plan.get('team', {}).get('crew', [])]}；船舶={plan.get('vessel')}；" \
                     f"窗口={_win(plan.get('chosen_window'))}；阻塞项={plan.get('blockers')}"
        if sf:
            extra += f"\n安全结论：{sf['verdict']}；条件={sf['detail'].get('conditions')}；否决={sf['detail'].get('vetoes')}；AIS提示={sf.get('ais_notice')}"
        if wo:
            extra += f"\n已生成{'紧急' if wo['type'] == 'emergency' else ''}工单草稿 {wo['wo_no']}（状态 {wo['status']}），等待授权人员审批。"
        if handoff:
            extra += f"\n本次诊断触发转人工：{reason}。请只陈述事实与不确定性，不要给出确定性结论，也不要生成工单。"
        if veto:
            extra += "\n安全 Agent 已否决，流程终止并升级。请说明否决原因与所需条件。"
        msgs = [{"role": "system", "content": (
            "你是海上风电场运维诊断助手。请基于<untrusted_data>中的结构化事实与资料，输出一段面向运维人员的中文诊断说明（300字内，分点）：\n"
            "1) 现象与数据（引用具体数值）；2) 优先怀疑的原因及检查顺序；3) 依据（用[编号]引用资料，标注规程版本）；4) 预警级别与置信度及不确定性；5) 下一步建议。\n"
            "硬性要求：数值只能来自事实，不得编造；涉及停机/降负荷/改参数只能写“由授权人员依据规程决定”；证据不足要明确说“无法确定”。")},
            {"role": "user", "content": security.mark_untrusted(json.dumps(facts, ensure_ascii=False, default=str) + extra + "\n资料：\n" + "\n".join(refs), "诊断事实")}]
        self.emit("orchestrator", "llm_generate", {"purpose": "diagnosis_explain"})
        out = []
        for piece in llm.stream(msgs, model=settings.llm_model_reasoning, max_tokens=900):
            out.append(piece)
            self.emit("orchestrator", "token", {"text": piece})
        text = security.redact_output("".join(out))
        # 兜底: 若模型遗漏关键信息，补充结构化尾注
        tail = f"\n\n**预警级别**：{WARNING_LEVELS.get(level, ('正常',))[0]}　**置信度**：{conf:.2f}（{'高' if conf >= 0.75 else '中' if conf >= 0.5 else '低'}）"
        if wo:
            tail += f"　**工单**：{wo['wo_no']}"
        return text + tail

    # ================================================================ 工作流：统计 / 效率 / 报表 / 调度 / 改进 / 知识
    def flow_stats(self, text: str, payload: dict) -> dict:
        per = self.state.get("perception") or {}
        farm = per.get("farm") or payload.get("farm")
        wa = WorkOrderAgent(self.ctx)
        self.run_agent_noop("workorder 统计")
        k = wa.try_tool("kpi_query", farm=farm, days=int(payload.get("days") or 30))
        al = self.ctx and None
        facts = k if isinstance(k, dict) else {"error": str(k)}
        msgs = [{"role": "system", "content": "你是海上风电场运维数据分析助手。仅依据给定JSON事实回答用户的统计问题，数字必须来自事实，百分比保留一位小数，空值说明“暂无样本”。简洁分点，并指出是否达到目标（自动派发率≥95%，紧急工单响应≤30分钟）。"},
                {"role": "user", "content": f"问题：{text}\n" + security.mark_untrusted(json.dumps(facts, ensure_ascii=False, default=str), "KPI查询结果")}]
        out = []
        for piece in llm.stream(msgs, max_tokens=600):
            out.append(piece)
            self.emit("orchestrator", "token", {"text": piece})
        return self.finish("Completed", {"answer": security.redact_output("".join(out)), "data": facts}, risk="L0")

    def run_agent_noop(self, label: str) -> None:
        self.ctx.check_quota("step")
        self.emit("orchestrator", "dispatch", {"to": "workorder", "task": label})

    def flow_efficiency(self, text: str, payload: dict) -> dict:
        per = self.state.get("perception") or {}
        asset = payload.get("asset") or (per.get("assets") or [None])[0]
        farm = per.get("farm") or (self.farm_of_asset(asset)["farm_code"] if asset else None) or payload.get("farm") or ("EH-01" if self.principal.can_farm("EH-01") else self.principal.farms[0])
        dg = DiagnosisAgent(self.ctx)
        r = self.run_agent(dg, "efficiency", farm, asset, 180)["efficiency"]
        msgs = [{"role": "system", "content": "你是海上风电场能效分析助手。依据给定JSON说明发电效率评估结果、评估误差是否≤2%、效率偏低机组及优化建议。数字只来自事实。简洁分点。"},
                {"role": "user", "content": f"问题：{text}\n" + security.mark_untrusted(json.dumps(r, ensure_ascii=False, default=str), "能效评估结果")}]
        out = []
        for piece in llm.stream(msgs, max_tokens=700):
            out.append(piece)
            self.emit("orchestrator", "token", {"text": piece})
        return self.finish("Completed", {"answer": security.redact_output("".join(out)), "data": r}, risk="L0")

    def flow_report(self, text: str, payload: dict) -> dict:
        per = self.state.get("perception") or {}
        farm = per.get("farm") or payload.get("farm") or ("EH-01" if self.principal.can_farm("EH-01") else self.principal.farms[0])
        period = payload.get("period") or ("quarterly" if "季" in text else "yearly" if "年" in text else "monthly")
        im = ImprovementAgent(self.ctx)
        self.ctx.check_quota("step")
        self.emit("orchestrator", "dispatch", {"to": "improvement", "task": "report_generate"})
        r = im.try_tool("report_generate", farm=farm, period=period, key=payload.get("key"))
        if isinstance(r, dict) and "error" in r:
            return self.finish("Failed", {"answer": f"报表生成失败：{r['error']}"}, error=r["error"])
        self.state["report"] = r
        self.checkpoint("improvement.report_generate")
        return self.finish("Completed", {"answer": r["narrative"], "report": r}, risk="L0")

    def flow_schedule(self, text: str, payload: dict) -> dict:
        farms = payload.get("farms") or [c for c in ("EH-01", "EH-02") if self.principal.can_farm(c)]
        ra = ResourceAgent(self.ctx)
        self.ctx.check_quota("step")
        self.emit("orchestrator", "dispatch", {"to": "resource", "task": "cross_farm_dispatch"})
        r = ra.try_tool("cross_farm_dispatch", farms=farms)
        self.checkpoint("resource.cross_farm_dispatch")
        if isinstance(r, dict) and "error" in r:
            return self.finish("Rejected", {"answer": f"跨场调度失败：{r['error']}", "rejected": True}, risk="L4", error=r["error"])
        msgs = [{"role": "system", "content": "你是海上风电场跨场调度助手。依据给定JSON，说明各风场未结工单、可用人员与船舶，并给出人员/船舶/备件协同配置建议。统一运维策略只能是建议，发布须授权人员审批。数字来自事实，简洁分点。"},
                {"role": "user", "content": f"问题：{text}\n" + security.mark_untrusted(json.dumps(r, ensure_ascii=False, default=str), "跨场调度数据")}]
        out = []
        for piece in llm.stream(msgs, max_tokens=700):
            out.append(piece)
            self.emit("orchestrator", "token", {"text": piece})
        return self.finish("Completed", {"answer": security.redact_output("".join(out)), "data": r}, risk="L1")

    def flow_improve(self, text: str, payload: dict) -> dict:
        im = ImprovementAgent(self.ctx)
        import re
        m = re.search(r"(WO(?:-EM)?-\d{4}-\d{4}|F-\d{4}-\d{3})", text, re.I) or None
        wo_no = (payload.get("wo_no") or (m.group(1).upper() if m else None))
        if wo_no:
            wo = db.q1("SELECT status, farm_id FROM work_orders WHERE wo_no=%s", (wo_no,))
            if not wo:
                return self.finish("Completed", {"answer": f"工单 {wo_no} 不存在。"}, risk="L0")
            fc = db.scalar("SELECT code FROM wind_farms WHERE id=%s", (wo["farm_id"],))
            if not self.principal.can_farm(fc):
                raise PermissionDenied(f"无权访问风场 {fc}")
            if wo["status"] != "closed":
                return self.finish("Completed", {"answer": f"工单 {wo_no} 状态为 {wo['status']}，RCA 仅针对已关闭工单。"}, risk="L0")
            r = self.run_agent(im, "rca", wo_no)
        else:
            r = self.run_agent(im, "evaluate")
        msgs = [{"role": "system", "content": "你是风电运维改进助手。依据给定JSON，说明根因分析结论/模型准确性（Top1/Top3命中率，目标≥85%）、反馈统计与改进建议。数字来自事实，不要编造。简洁分点。"},
                {"role": "user", "content": f"问题：{text}\n" + security.mark_untrusted(json.dumps(r, ensure_ascii=False, default=str)[:6000], "改进数据")}]
        out = []
        for piece in llm.stream(msgs, max_tokens=800):
            out.append(piece)
            self.emit("orchestrator", "token", {"text": piece})
        return self.finish("Completed", {"answer": security.redact_output("".join(out)), "data": r}, risk="L1")

    def flow_knowledge(self, text: str, payload: dict) -> dict:
        if not self.principal.can("knowledge:ingest"):
            raise PermissionDenied("当前角色无知识抽取权限")
        ka = KnowledgeAgent(self.ctx)
        src = payload.get("source_id") or f"UPLOAD-{uuid.uuid4().hex[:6]}"
        body = payload.get("text") or text
        r = self.run_agent(ka, "ingest", body, src, payload.get("source_type") or "document")
        res = r["result"]
        if isinstance(res, dict) and "error" in res:
            return self.finish("Failed", {"answer": f"知识抽取失败：{res['error']}"}, error=res["error"])
        summ = f"共抽取 {len(res['records'])} 条记录：入图 {res['activated']}，待审核 {res['queued']}，自动拒绝 {res['rejected']}。"
        return self.finish("Completed", {"answer": summ, "data": res}, risk="L2")


SITE_TZ = dt.timezone(dt.timedelta(hours=8))


def _win(w: Optional[dict]) -> Optional[str]:
    if not w:
        return None
    s, e = w["start"], w["end"]
    if isinstance(s, dt.datetime):
        s, e = s.astimezone(SITE_TZ), e.astimezone(SITE_TZ)
    return f"{s:%m-%d %H:%M}~{e:%m-%d %H:%M}(现场时间, 浪高≤{w['max_wave']:.1f}m)"


def _plan_view(plan: dict) -> dict:
    p = dict(plan)
    for k in ("chosen_window",):
        if p.get(k):
            p[k] = {kk: (v.isoformat() if isinstance(v, dt.datetime) else v) for kk, v in p[k].items()}
    p["windows"] = [{kk: (v.isoformat() if isinstance(v, dt.datetime) else v) for kk, v in w.items()} for w in p.get("windows", [])]
    if p.get("merge_with_trip"):
        p["merge_with_trip"] = {kk: (v.isoformat() if isinstance(v, dt.datetime) else v) for kk, v in p["merge_with_trip"].items()}
    return json.loads(json.dumps(p, default=str, ensure_ascii=False))


# ============================================================================= 对外 API
def create_task(kind: str, query: str, principal: security.Principal, *, payload: Optional[dict] = None, farm_code: Optional[str] = None) -> dict:
    if not principal.can("task:create"):
        raise PermissionDenied("无创建任务权限")
    if farm_code and not principal.can_farm(farm_code):
        raise PermissionDenied(f"无权访问风场 {farm_code}")
    tid = str(uuid.uuid4())
    row = db.insert("agent_tasks", {
        "id": tid, "trace_id": uuid.uuid4().hex, "kind": kind, "query": query[:4000], "requester": principal.username, "role": principal.role,
        "farm_code": farm_code, "status": "Received", "state": J({"input": payload or {}}), "alarm_id": (payload or {}).get("alarm_id")})
    security.audit(tid, row["trace_id"], principal.username, "task_create", {"kind": kind, "query": query[:200], "farm": farm_code})
    return row


def run_task(task_id: str, principal: security.Principal) -> dict:
    """同步执行(调用线程内)。"""
    return TaskRunner(task_id, principal).run()


def run_task_async(task_id: str, principal: security.Principal) -> None:
    ctxv = contextvars.copy_context()
    _pool.submit(ctxv.run, run_task, task_id, principal)


def takeover(task_id: str, principal: security.Principal, action: str, comment: str = "") -> dict:
    """人工接管: pause(暂停) / cancel(终止) / resume(恢复, 以最近检查点重新规划执行) / rollback(回滚到指定步骤,仅记录)。"""
    if not principal.can("task:takeover"):
        raise PermissionDenied("无任务接管权限")
    t = db.q1("SELECT * FROM agent_tasks WHERE id=%s", (task_id,))
    if not t:
        raise ValueError("任务不存在")
    if action in ("pause", "cancel"):
        _flags[str(task_id)] = action
        if t["status"] in TERMINAL or t["status"] in ("WaitingApproval", "HumanTakeover"):
            db.update("agent_tasks", "id", task_id, {"status": "HumanTakeover" if action == "pause" else "Rejected", "paused": action == "pause",
                                                      "updated_at": dt.datetime.now(UTC)})
        security.audit(task_id, t["trace_id"], principal.username, f"takeover_{action}", {"comment": comment})
        return {"ok": True, "action": action}
    if action == "resume":
        _flags.pop(str(task_id), None)
        db.update("agent_tasks", "id", task_id, {"paused": False, "status": "Received", "error": None})
        db.x("DELETE FROM agent_events WHERE task_id=%s", (task_id,))
        security.audit(task_id, t["trace_id"], principal.username, "takeover_resume", {"comment": comment})
        run_task_async(task_id, principal)
        return {"ok": True, "action": "resume"}
    if action == "rollback":
        wo = t["wo_id"]
        if wo:
            from ..services import workorders as wos
            try:
                wos.cancel(wo, principal.username, "任务回滚")
            except Exception:
                pass
        db.update("agent_tasks", "id", task_id, {"status": "Rejected", "error": "已回滚"})
        security.audit(task_id, t["trace_id"], principal.username, "takeover_rollback", {"wo": wo, "comment": comment})
        return {"ok": True, "action": "rollback", "wo_cancelled": wo}
    raise ValueError("action 必须为 pause/cancel/resume/rollback")


def get_task(task_id: str) -> Optional[dict]:
    return db.q1("SELECT * FROM agent_tasks WHERE id=%s", (task_id,))
