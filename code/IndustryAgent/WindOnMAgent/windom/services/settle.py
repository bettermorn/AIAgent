"""知识更新闭环（文档 4.7）：工单关闭 → LLM 总结(现象—根因—措施—效果) → 与已有知识比对 →
  同类复现：更新故障频率/风险等级；新故障模式：入待审核队列；规程新版本：旧知识失效（见 documents.ingest）。"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from .. import db, llm, security
from ..db import J
from ..ontology import FAULTS
from . import kg, knowledge_eng as ke

log = logging.getLogger("windom.settle")
UTC = dt.timezone.utc


def summarize_workorder(wo: dict) -> dict:
    """LLM 将关闭工单总结为 现象—根因—措施—效果；LLM 不可用时降级为结构化模板。"""
    base = {"symptom": wo["title"], "root_cause": wo["root_cause"], "actions": [a.get("name") for a in (wo["actual_actions"] or [])],
            "result": wo["result"], "effective": wo["effective"]}
    if not llm.available():
        return {**base, "summary": f"{wo['title']}；根因：{wo['root_cause']}；措施：{'、'.join(filter(None, base['actions']))}；效果：{wo['result']}", "by": "template"}
    try:
        text = llm.chat([
            {"role": "system", "content": "你是风电运维知识沉淀助手。把工单整理成一句话的案例总结，格式：故障现象—根因—处理措施—处理效果。只陈述给定事实，不要添加推测。"},
            {"role": "user", "content": security.mark_untrusted(str({**base, "asset": wo["asset_code"], "fault": FAULTS.get(wo["fault_key"], {}).get("name")}), f"工单{wo['wo_no']}")}],
            max_tokens=250, temperature=0.1)
        return {**base, "summary": security.redact_output(text.strip()), "by": "llm"}
    except Exception as e:
        log.warning("工单总结降级: %s", e)
        return {**base, "summary": f"{wo['title']}；根因：{wo['root_cause']}", "by": "template"}


def settle(wo_id: int) -> dict:
    """工单关闭后的知识沉淀。幂等(kg_synced)。"""
    wo = db.q1("SELECT * FROM work_orders WHERE id=%s", (wo_id,))
    if not wo or wo["status"] != "closed":
        raise ValueError("仅已关闭工单可沉淀")
    if wo["kg_synced"]:
        return {"skipped": True}
    summ = summarize_workorder(wo)
    fault_key = wo["fault_key"]
    fe = kg.get_entity("Fault", fault_key) if fault_key else None
    res = {"summary": summ["summary"], "actions": []}
    with db.tx():
        we = kg.upsert_entity("WorkOrder", wo["wo_no"], wo["wo_no"], {"asset": wo["asset_code"], "summary": summ["summary"]})
        kw = dict(source_type="workorder", source_id=wo["wo_no"], reviewer=wo["id"] and "closed-loop", confidence=0.95 if wo["effective"] else 0.6,
                  valid_from=wo["closed_at"])
        if fe:
            kg.add_relation(we, "handles", fe["id"], **kw)
        comp = kg.get_entity("Component", wo["comp_code"]) if wo["comp_code"] else None
        if comp:
            kg.add_relation(we, "on_component", comp["id"], **kw)
        ck = wo["root_cause_key"]
        ce = kg.get_entity("Cause", ck) if ck else None
        if ce and fe:
            kg.add_relation(we, "root_cause", ce["id"], **kw)
            ex = db.q1("SELECT id, props FROM kg_relations WHERE src=%s AND rel='possible_cause' AND dst=%s AND status='active' LIMIT 1", (fe["id"], ce["id"]))
            if ex:
                freq = int(ex["props"].get("freq", 0)) + 1
                db.x("UPDATE kg_relations SET props = props || %s WHERE id=%s", (J({"freq": freq, "last_seen": wo["closed_at"]}), ex["id"]))
                res["actions"].append({"type": "update_frequency", "cause": ck, "freq": freq})
                res["fault_frequency"] = db.scalar("SELECT count(*) FROM work_orders WHERE fault_key=%s AND status='closed'", (fault_key,))
        elif fe and wo["root_cause"]:
            # 新故障模式 → 待审核知识(不直接入图)
            cand = db.insert("knowledge_candidates", {
                "batch_id": f"wo-{wo['wo_no']}", "source_type": "workorder", "source_id": wo["wo_no"], "source_locator": "closing-report",
                "payload": J({"raw": {"equipment": wo["asset_code"], "component": wo["comp_code"], "symptom": wo["title"], "possible_cause": [wo["root_cause"]],
                                       "action": [a.get("name") for a in (wo["actual_actions"] or [])], "result": wo["result"]},
                              "fault": {"std_key": fault_key, "std_name": FAULTS[fault_key]["name"]}, "new_cause_text": wo["root_cause"],
                              "component_code": wo["comp_code"], "cause_keys": [], "action_keys": [a["key"] for a in (wo["actual_actions"] or []) if a.get("key")]}),
                "raw_text": summ["summary"], "confidence": 0.7, "validation": J({"L5_expert": {"required": True, "reasons": ["工单根因不在已有因果库：新故障模式"]}}),
                "needs_expert": True, "risk_reason": "新故障模式，须专家审核", "status": "pending", "extract_model": "closed-loop"})
            res["actions"].append({"type": "new_pattern_candidate", "candidate_id": cand["id"]})
        for a in (wo["actual_actions"] or []):
            ae = kg.get_entity("Action", a.get("key", ""))
            if ae:
                kg.add_relation(we, "adopted", ae["id"], **kw)
        # 故障风险等级: 90天内同类故障次数
        n90 = db.scalar("SELECT count(*) FROM work_orders WHERE fault_key=%s AND asset_code=%s AND created_at > now() - interval '90 days'", (fault_key, wo["asset_code"]))
        if comp:
            risk = "high" if (n90 or 0) >= 3 else "medium" if (n90 or 0) == 2 else "low"
            db.x("UPDATE kg_entities SET props = props || %s WHERE id=%s", (J({"risk_level": risk, "fault_count_90d": n90, "last_fault": fault_key}), comp["id"]))
            res["component_risk"] = risk
        db.update("work_orders", "id", wo_id, {"kg_synced": True})
    security.audit(wo["task_id"], None, "workorder-agent", "knowledge_settle", {"wo": wo["wo_no"], **{k: v for k, v in res.items() if k != "summary"}})
    return res
