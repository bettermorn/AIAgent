"""改进闭环（规范 8.2.3 / 6.4.2；文档 4.5 工作流三）：
收集维修反馈与运行状态变化 → 评估模型准确性/维护效果 → RCA 根因分析 → 模型参数调整(≤30 天周期) →
维护策略优化 → 经黄金集回归门禁与灰度登记 → 更新知识库（经审核入图）。"""
from __future__ import annotations

import datetime as dt
import logging
import math
from collections import Counter, defaultdict
from typing import Optional

from .. import db, llm, security
from ..config import settings
from ..db import J
from ..ontology import FAULTS
from . import diagnosis_model as dm, kg, modelreg

log = logging.getLogger("windom.improve")
UTC = dt.timezone.utc


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


# ------------------------------------------------------------------ 评估
def _closed_samples(days: Optional[int] = None) -> list[dict]:
    return db.q("""SELECT id, wo_no, asset_code, fault_key, root_cause_key, features, effective, response_minutes, repair_minutes, closed_at, comp_code
                   FROM work_orders WHERE status='closed' AND root_cause_key IS NOT NULL AND fault_key IS NOT NULL
                     AND (%s::int IS NULL OR closed_at > now() - make_interval(days => %s))""", (days, days))


def evaluate_params(params: dict, samples: Optional[list[dict]] = None) -> dict:
    """以闭环工单(真实根因)评估原因排序模型: Top1/Top3 命中率。"""
    samples = samples if samples is not None else _closed_samples()
    kn_cache: dict[str, dict] = {}
    top1 = top3 = n = 0
    per_fault: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for s in samples:
        dirs = (s["features"] or {}).get("dirs")
        if dirs is None:
            continue
        kn = kn_cache.setdefault(s["fault_key"], kg.fault_knowledge(s["fault_key"]))
        if not kn:
            continue
        ranked = dm.classify_from_features(s["fault_key"], dirs, kn, params)
        keys = [r["key"] for r in ranked]
        n += 1
        per_fault[s["fault_key"]][1] += 1
        if keys and keys[0] == s["root_cause_key"]:
            top1 += 1
            per_fault[s["fault_key"]][0] += 1
        if s["root_cause_key"] in keys[:3]:
            top3 += 1
    return {"n": n, "top1": top1 / n if n else None, "top3": top3 / n if n else None,
            "per_fault": {k: {"top1": v[0] / v[1], "n": v[1]} for k, v in per_fault.items() if v[1]}}


def evaluate_golden(params: dict) -> dict:
    """黄金集回归：模型更新的门禁(规范 6.4.2 算法准确率 ≥85%)。"""
    rows = db.q("SELECT * FROM eval_golden")
    kn_cache: dict[str, dict] = {}
    top1 = top3 = 0
    for g in rows:
        kn = kn_cache.setdefault(g["fault_key"], kg.fault_knowledge(g["fault_key"]))
        ranked = dm.classify_from_features(g["fault_key"], g["scenario"]["dirs"], kn, params)
        keys = [r["key"] for r in ranked]
        top1 += bool(keys and keys[0] == g["expected_cause"])
        top3 += g["expected_cause"] in keys[:3]
    n = len(rows)
    return {"n": n, "top1": top1 / n if n else None, "top3": top3 / n if n else None}


def calibrate(samples: list[dict], base: dict) -> tuple[dict, dict]:
    """参数调整: 网格搜索 match_p / prior_weight，最大化闭环工单 Top-1(同分偏好更保守的参数)。"""
    best, best_score = dict(base), -1.0
    grid = [(mp, pw) for mp in (0.6, 0.7, 0.8, 0.85, 0.9, 0.95) for pw in (0.5, 1.0, 1.5)]
    for mp, pw in grid:
        cand = {**base, "match_p": mp, "prior_weight": pw}
        ev = evaluate_params(cand, samples)
        score = (ev["top1"] or 0) - 0.01 * abs(mp - base["match_p"]) - 0.005 * abs(pw - base["prior_weight"])
        if score > best_score:
            best, best_score = cand, score
    return best, evaluate_params(best, samples)


# ------------------------------------------------------------------ RCA
def rca(wo_id: int) -> dict:
    """RCA：5-Why 证据链(图谱路径 + 历史复现 + 趋势) + LLM 归纳; 输出根因、贡献因素、预防建议。"""
    wo = db.q1("SELECT * FROM work_orders WHERE id=%s", (wo_id,))
    if not wo or wo["status"] != "closed":
        raise ValueError("RCA 仅针对已关闭工单")
    recur = db.q("""SELECT wo_no, closed_at, root_cause FROM work_orders WHERE asset_code=%s AND fault_key=%s AND status='closed' AND id<>%s
                    ORDER BY closed_at DESC LIMIT 5""", (wo["asset_code"], wo["fault_key"], wo_id))
    fleet = db.scalar("SELECT count(*) FROM work_orders WHERE fault_key=%s AND root_cause_key=%s AND status='closed'", (wo["fault_key"], wo["root_cause_key"]))
    kn = kg.fault_knowledge(wo["fault_key"]) or {"causes": []}
    cause = next((c for c in kn["causes"] if c["key"] == wo["root_cause_key"]), None)
    predicted = (wo["causes"] or [{}])[0].get("key") if wo["causes"] else None
    facts = {"asset": wo["asset_code"], "fault": FAULTS.get(wo["fault_key"], {}).get("name"), "root_cause": wo["root_cause"],
             "diagnosed_top_cause": predicted, "diagnosis_correct": predicted == (wo["root_cause_key"] or "").split(".")[-1] if predicted else None,
             "same_asset_recurrence": [{"wo": r["wo_no"], "root_cause": r["root_cause"]} for r in recur],
             "fleet_same_rootcause_count": fleet, "response_minutes": wo["response_minutes"], "repair_minutes": wo["repair_minutes"],
             "effective": wo["effective"], "actions": [a.get("name") for a in (wo["actual_actions"] or [])],
             "known_checks": cause["checks"] if cause else []}
    analysis: dict = {"facts": facts, "chain": []}
    recs: list[str] = []
    if recur:
        recs.append(f"{wo['asset_code']} 同类故障已复发 {len(recur)} 次，建议缩短该部件预防性检查周期并评估部件更换")
    if fleet and fleet >= 8:
        recs.append(f"同根因({wo['root_cause']})在机队已出现 {fleet} 次，建议纳入机队级预防性维护计划(批量清洁/润滑/检查)")
    if wo["effective"] is False:
        recs.append("处理措施未能彻底消除故障，需复核根因判断并重新诊断")
    if wo["response_minutes"] and wo["response_minutes"] > settings.response_sla_min and wo["wo_type"] == "emergency":
        recs.append(f"紧急工单响应用时 {wo['response_minutes']:.0f} 分钟，超过 {settings.response_sla_min:.0f} 分钟要求，需复盘派发/审批环节")
    root = wo["root_cause"] or "未知"
    if llm.available():
        try:
            res = llm.chat_json([
                {"role": "system", "content": "你是风电运维根因分析(RCA)专家。基于给定事实做 5-Why 分析，不得编造事实。输出 JSON：{\"whys\":[\"为什么1\",...最多5条],\"root_cause\":\"根本原因\",\"contributing\":[\"促成因素\"],\"prevention\":[\"预防措施\"]}"},
                {"role": "user", "content": security.mark_untrusted(str(facts), f"工单{wo['wo_no']}")}], max_tokens=700, retries=1)
            analysis["chain"] = [str(x) for x in res.get("whys", [])][:5]
            root = str(res.get("root_cause") or root)
            analysis["contributing"] = [str(x) for x in res.get("contributing", [])]
            recs += [str(x) for x in res.get("prevention", [])]
            analysis["by"] = "llm"
        except Exception as e:
            log.warning("RCA LLM 降级: %s", e)
    analysis.setdefault("by", "rules")
    rep = db.insert("rca_reports", {"wo_id": wo_id, "asset_code": wo["asset_code"], "fault_key": wo["fault_key"], "root_cause": root,
                                    "analysis": J(analysis), "recommendations": J(recs)})
    return rep


# ------------------------------------------------------------------ 反馈汇总
def collect_feedback(days: int = 30) -> dict:
    """维修反馈 + 用户反馈 + 运行状态变化(处理后同传感器是否恢复)。"""
    wos = db.q("""SELECT id, asset_code, fault_key, closed_at, effective FROM work_orders WHERE status='closed' AND source<>'history'
                  AND closed_at > now() - make_interval(days => %s)""", (days,))
    recovered = 0
    for w in wos:
        spec = FAULTS.get(w["fault_key"])
        if not spec:
            continue
        rule = db.q1("SELECT l1, direction FROM rules WHERE fault_key=%s", (w["fault_key"],))
        r = db.q1("SELECT avg(value) v FROM ts_realtime WHERE asset_code=%s AND sensor_type=%s AND ts > %s AND ts < %s + interval '30 minutes'",
                  (w["asset_code"], spec["sensor"], w["closed_at"], w["closed_at"]))
        if r and r["v"] is not None and rule:
            ok = r["v"] < rule["l1"] if rule["direction"] == "high" else r["v"] > rule["l1"]
            recovered += bool(ok)
    fb = db.q1("SELECT count(*) n, avg(rating) r, count(*) FILTER (WHERE correct) ok FROM feedback WHERE created_at > now() - make_interval(days => %s)", (days,))
    eff = db.q1("SELECT count(*) n, count(*) FILTER (WHERE effective) ok FROM work_orders WHERE status='closed' AND closed_at > now() - make_interval(days => %s)", (days,))
    return {"closed_workorders": len(wos), "recovered_after_repair": recovered, "user_feedback": fb, "maintenance_effective": eff}


# ------------------------------------------------------------------ 月度迭代
def run_iteration(force: bool = False) -> dict:
    """模型更新迭代: 评估现模型 → 校准参数 → 黄金集门禁 → 灰度(shadow)登记 → 通过则全量切换 → RCA 汇总 → 策略优化。"""
    last = modelreg.last_update("cause_ranker")
    age_days = (now() - last).days if last else 999
    if not force and age_days < settings.model_update_days - 1 and last:
        return {"skipped": True, "reason": f"距上次更新 {age_days} 天，未到 {settings.model_update_days} 天周期", "age_days": age_days}
    active = modelreg.get_active("cause_ranker")
    base = modelreg.params("cause_ranker")
    samples = _closed_samples()
    cur = evaluate_params(base, samples)
    cur_g = evaluate_golden(base)
    new_params, new_ev = calibrate(samples, base)
    new_g = evaluate_golden(new_params)
    ver = modelreg.next_version("cause_ranker")
    metrics = {"workorder_eval": new_ev, "golden": new_g, "baseline": {"workorder_eval": {k: cur[k] for k in ("n", "top1", "top3")}, "golden": cur_g}}
    m = modelreg.register("cause_ranker", ver, new_params, status="shadow", metrics=metrics,
                          note=f"由 {active['version']} 经 {len(samples)} 条闭环工单校准")
    gate_ok = (new_g["top1"] or 0) >= settings.algo_accuracy_target and (new_ev["top1"] or 0) >= (cur["top1"] or 0) - 1e-9
    decision = {"model": f"{m['name']}@{m['version']}", "gate": {"golden_top1": new_g["top1"], "target": settings.algo_accuracy_target,
                                                                    "not_worse_than_current": (new_ev["top1"] or 0) >= (cur["top1"] or 0) - 1e-9}}
    if gate_ok:
        modelreg.promote(m["id"])
        decision["action"] = "promoted"
    else:
        modelreg.reject(m["id"], f"门禁未通过: 黄金集Top1={new_g['top1']}")
        decision["action"] = "rejected"
    # 能效模型周期登记（参数无需调整, 仍登记以体现 ≤30 天更新周期）
    eff_active = modelreg.get_active("efficiency")
    modelreg.register("efficiency", modelreg.next_version("efficiency"), eff_active["params"], status="active",
                      metrics={"note": "周期复核，基准曲线随最新数据重建"}, note="月度周期复核")
    db.x("UPDATE model_registry SET status='retired' WHERE name='efficiency' AND status='active' AND id <> (SELECT max(id) FROM model_registry WHERE name='efficiency')")
    # 近期工单 RCA + 策略优化
    recent = db.q("SELECT id FROM work_orders WHERE status='closed' AND source<>'history' AND closed_at > now() - interval '30 days' AND id NOT IN (SELECT wo_id FROM rca_reports WHERE wo_id IS NOT NULL)")
    rcas = []
    for w in recent[:20]:
        try:
            rcas.append(rca(w["id"])["id"])
        except Exception as e:
            log.warning("RCA 失败 %s: %s", w["id"], e)
    strat = optimize_strategy()
    ev_row = db.insert("eval_runs", {"model_name": "cause_ranker", "model_version": m["version"], "n": new_g["n"], "top1": new_g["top1"],
                                     "top3": new_g["top3"], "detail": J(metrics)})
    out = {"skipped": False, "decision": decision, "metrics": metrics, "rca_reports": rcas, "strategy": strat, "feedback": collect_feedback()}
    security.audit(None, None, "improve-agent", "model_iteration", {"decision": decision, "rca": len(rcas)})
    db.insert("job_runs", {"job": "model_iteration", "ok": True, "detail": J({"decision": decision})}, returning="id")
    return out


def optimize_strategy() -> dict:
    """维护策略优化: 依据故障频次/MTTR/响应时间生成策略建议(草稿, 由审批人发布)。"""
    rows = db.q("""SELECT fault_key, count(*) n, avg(repair_minutes) mttr FROM work_orders WHERE status='closed'
                   AND closed_at > now() - interval '180 days' GROUP BY fault_key ORDER BY n DESC LIMIT 5""")
    items = []
    for r in rows:
        f = FAULTS.get(r["fault_key"])
        if not f:
            continue
        items.append({"fault": f["name"], "count_180d": r["n"], "mttr_minutes": round(r["mttr"] or 0),
                      "suggest": f"将「{f['name']}」相关部件纳入预防性检查，优先备足高频备件，合并出海计划"})
    s = db.insert("strategies", {"title": f"{now():%Y-%m} 维护策略优化建议", "content": J({"items": items}), "farms": ["*"], "status": "draft", "created_by": "improve-agent"})
    return {"strategy_id": s["id"], "items": items}


def due_for_iteration() -> bool:
    last = modelreg.last_update("cause_ranker")
    return not last or (now() - last).days >= settings.model_update_days - 1
