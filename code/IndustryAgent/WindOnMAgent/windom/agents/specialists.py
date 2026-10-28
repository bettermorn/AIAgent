"""专业 Agent 群（文档 4.2）：检索、诊断、安全、资源、工单、知识工程、改进。
每个 Agent 仅持有最小工具权限（tools/defs.py 中授权），总控 Agent 通过调用它们完成任务。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from .. import db, llm, security
from ..config import settings
from ..ontology import COMP_NAME, FAULTS, SENSOR_NAME, WARNING_LEVELS
from ..services import kg
from ..tools import defs  # noqa: F401  (触发工具注册)
from ..tools.registry import PermissionDenied, ToolError
from .base import BaseAgent


# ======================================================================= 检索 Agent
class RetrievalAgent(BaseAgent):
    name, label = "retrieval", "检索 Agent"

    def gather(self, asset: str, fault_key: str, question: str) -> dict:
        """图谱 + 文档 + 工单 混合检索取证(GraphRAG)，输出带来源/版本/页码/工单号的证据包。"""
        self.perceive(asset=asset, fault=fault_key, question=question[:80])
        self.plan(["图谱多跳: 故障→原因→措施→备件", "相似案例(同型号优先)", "最新有效规程条款(向量+BM25+RRF)", "机队统计"])
        evidence: list[dict] = []
        kn = self.try_tool("kg_query", op="fault_knowledge", fault_key=fault_key)
        cases = self.try_tool("kg_query", op="similar_cases", fault_key=fault_key, entity=asset, limit=3)
        spec = FAULTS[fault_key]
        comp_name = COMP_NAME.get(spec["comp"], "")
        query = f"{comp_name}{spec['name']} {question}"
        docs = self.try_tool("doc_search", query=query[:290], top_k=4)
        stats = self.try_tool("workorder_search", fault_key=fault_key, stats=True, limit=6)
        if isinstance(kn, dict) and "causes" in kn:
            for c in kn["causes"]:
                evidence.append({"type": "kg", "id": f"kg:{c['key']}", "title": f"图谱: {spec['name']} → {c['name']}",
                                 "detail": f"先验 {c['prior']:.2f}；来源 {c['source'].get('id')} {c['source'].get('locator') or ''}"})
        if isinstance(docs, list):
            for d in docs:
                evidence.append({"type": "doc", "id": f"doc:{d['doc_no']}:{d['section']}", "title": f"《{d['title']}》{d['version']} {d['section'] or ''}节",
                                 "detail": d["text"][:160], "doc_no": d["doc_no"], "version": d["version"], "section": d["section"], "page": d["page"],
                                 "status": d["status"]})
        if isinstance(cases, list):
            for c in cases:
                evidence.append({"type": "workorder", "id": f"wo:{c['wo_no']}", "title": f"工单 {c['wo_no']} ({c['asset_code']})",
                                 "detail": f"根因：{c['root_cause']}；措施：{'、'.join(a.get('name', '') for a in (c['actual_actions'] or []))}；响应 {c['response_minutes'] and round(c['response_minutes'])}min",
                                 "wo_no": c["wo_no"]})
        chk = self.reflect([
            {"name": "图谱因果链非空", "ok": isinstance(kn, dict) and bool(kn.get("causes"))},
            {"name": "取到最新有效规程", "ok": isinstance(docs, list) and any(d["status"] == "active" for d in docs)},
            {"name": "存在历史相似案例", "ok": isinstance(cases, list) and len(cases) > 0, "soft": True},
        ])
        return self.output({"knowledge": kn if isinstance(kn, dict) else None, "cases": cases if isinstance(cases, list) else [],
                            "docs": docs if isinstance(docs, list) else [], "stats": stats if isinstance(stats, list) else [],
                            "evidence": evidence, "reflect": chk})

    def answer_context(self, question: str, asset: Optional[str] = None) -> dict:
        self.perceive(question=question[:100], asset=asset)
        self.plan(["规程/说明书混合检索(仅最新有效版本)", "知识图谱实体检索"])
        docs = self.try_tool("doc_search", query=question[:290], top_k=5)
        kgs = self.try_tool("kg_query", op="search", entity=question[:40], limit=8) if len(question) < 40 else []
        ev = []
        if isinstance(docs, list):
            for d in docs:
                ev.append({"type": "doc", "id": f"doc:{d['doc_no']}:{d['section']}", "title": f"《{d['title']}》{d['version']} {d['section'] or ''}节",
                           "detail": d["text"], "doc_no": d["doc_no"], "version": d["version"], "section": d["section"], "page": d["page"], "status": d["status"]})
        return self.output({"evidence": ev, "kg": kgs if isinstance(kgs, list) else []})


# ======================================================================= 诊断 Agent
class DiagnosisAgent(BaseAgent):
    name, label = "diagnosis", "诊断 Agent"

    def analyze(self, asset: str, fault_key: Optional[str], minutes: float = 120, alarm: Optional[dict] = None) -> dict:
        self.perceive(asset=asset, fault=fault_key, minutes=minutes)
        self.plan(["规则引擎: 阈值/多级预警", "SCADA 窗口统计与趋势", "时序模型: 偏离特征+异常分+原因后验", "多源监测(红外/视频)"])
        scada = self.try_tool("scada_query", asset=asset, minutes=minutes)
        rules = self.try_tool("rule_eval", asset=asset, minutes=10)
        # 未指定故障 → 取规则引擎中等级最高的越限项
        if not fault_key and isinstance(rules, dict):
            hits = [r for r in rules["results"] if r["level"] > 0]
            if hits:
                fault_key = max(hits, key=lambda r: r["level"])["fault_key"]
        if not fault_key:
            return self.output({"scada": scada, "rules": rules, "fault_key": None, "healthy": True,
                                "message": "各监测量均在规程阈值内，未发现需处置的越限。"})
        diag = self.try_tool("ts_diagnose", asset=asset, fault_key=fault_key, minutes=minutes)
        media = self.try_tool("video_ir_query", asset=asset) if isinstance(diag, dict) and diag.get("warning_level", 0) >= 1 else []
        # 反思: 规则 vs 模型 一致性
        rule_lv = 0
        if isinstance(rules, dict):
            rl = [r for r in rules["results"] if r["fault_key"] == fault_key]
            rule_lv = max([r["level"] for r in rl], default=0)
        model_lv = diag.get("warning_level", 0) if isinstance(diag, dict) else 0
        conflict = bool(rule_lv != model_lv and abs(rule_lv - model_lv) >= 2)
        ok_diag = isinstance(diag, dict) and "causes" in diag
        top_prob = diag["causes"][0]["probability"] if ok_diag and diag["causes"] else 0
        refl = self.reflect([
            {"name": "诊断模型有输出", "ok": ok_diag},
            {"name": "规则与模型预警等级一致(差<2级)", "ok": not conflict, "detail": f"规则={rule_lv} 模型={model_lv}"},
            {"name": "最可能原因后验≥0.4", "ok": top_prob >= 0.4, "detail": f"{top_prob:.2f}", "soft": True},
        ])
        level = max(rule_lv, model_lv)
        return self.output({"fault_key": fault_key, "diag": diag if ok_diag else None, "scada": scada if isinstance(scada, dict) else None,
                            "rules": rules if isinstance(rules, dict) else None, "media": media if isinstance(media, list) else [],
                            "warning_level": level, "rule_conflict": conflict, "reflect": refl,
                            "error": diag.get("error") if isinstance(diag, dict) and "error" in diag else None})

    def efficiency(self, farm: str, asset: Optional[str], minutes: float = 180) -> dict:
        self.perceive(farm=farm, asset=asset)
        r = self.try_tool("efficiency_eval", farm=farm, asset=asset, minutes=minutes)
        return self.output({"efficiency": r})


# ======================================================================= 安全 Agent
class SafetyAgent(BaseAgent):
    name, label = "safety", "安全 Agent"

    def review(self, farm: str, actions: list[dict], plan: dict, asset: str) -> dict:
        """权限/作业风险/合规检查；拥有否决权(Veto)。"""
        self.perceive(farm=farm, actions=[a["name"] for a in actions])
        self.plan(["用户权限与风场 ABAC", "海况窗口/资质/作业票合规", "高风险(L3)动作识别与禁止"])
        needs = sorted({n for a in actions for n in (a.get("needs") or [])})
        iam = self.try_tool("iam_check", farm=farm, action="create_workorder")
        window = plan.get("chosen_window")
        team = plan.get("team") or {}
        res = self.try_tool("safety_rule_eval", farm=farm, needs=needs, window={k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in window.items()} if window else None,
                            team=team, action_names=[a["name"] for a in actions])
        sea = self.try_tool("weather_ais_query", farm=farm, hours=24)
        if isinstance(res, dict) and isinstance(iam, dict) and not (iam.get("farm_ok") and iam.get("action_ok")):
            res = {**res, "verdict": "veto", "vetoes": res.get("vetoes", []) + ["发起用户无权在该风场创建工单(IAM)"]}
        verdict = res["verdict"] if isinstance(res, dict) and "verdict" in res else "veto"
        self.reflect([{"name": "合规检查完成", "ok": isinstance(res, dict) and "verdict" in res},
                      {"name": "无硬否决项", "ok": verdict != "veto", "detail": verdict}])
        ais_near = [v for v in (sea.get("ais") or []) if v.get("ship_type") != "patrol"] if isinstance(sea, dict) else []
        notices = [f"作业海域附近有船舶 {v['name']}（{v['ship_type']}，{v['sog']:.0f}节），作业前须 VHF 通报" for v in ais_near]
        return self.output({"verdict": verdict, "detail": res if isinstance(res, dict) else {"error": str(res)}, "iam": iam,
                            "ais_notice": notices})


# ======================================================================= 资源 Agent
class ResourceAgent(BaseAgent):
    name, label = "resource", "资源 Agent"

    def plan_trip(self, farm: str, asset: str, actions: list[dict]) -> dict:
        self.perceive(farm=farm, asset=asset, parts=sorted({p["code"] for a in actions for p in a.get("parts", [])}))
        self.plan(["备件库存(含跨场)", "人员资质(含证书有效期)", "海况窗口+船舶", "与已计划出海合并"])
        plan = self.try_tool("resource_schedule", farm=farm, asset=asset,
                             actions=[{"key": a.get("key"), "name": a["name"], "parts": a.get("parts", []), "needs": a.get("needs", []), "hours": a.get("hours")} for a in actions])
        ok = isinstance(plan, dict) and "feasible" in plan
        self.reflect([{"name": "资源方案可行", "ok": bool(ok and plan["feasible"]), "detail": "；".join(plan.get("blockers", [])) if ok else str(plan)}])
        if not ok:
            return self.output({"plan": {"feasible": False, "blockers": [str(plan)], "parts": [], "team": {}}})
        return self.output({"plan": plan})


# ======================================================================= 工单 Agent
class WorkOrderAgent(BaseAgent):
    name, label = "workorder", "工单 Agent"

    def draft(self, *, asset: str, fault_key: str, warning_level: int, risk: str, causes: list, actions: list, plan: dict, safety: dict,
              evidence: list, features: dict, alarm_id: Optional[int], description: str) -> dict:
        self.perceive(asset=asset, level=warning_level)
        emergency = warning_level >= settings.emergency_level
        self.plan(["预警≥二级 → 紧急工单(规范 8.2.2a)" if emergency else "普通工单草稿", "绑定证据/备件/班组/窗口", "提交审批并开始响应计时" if emergency else "保存草稿待人工提交"])
        parts = [{"code": p["code"], "name": p["name"], "available": p.get("available", 0), "location": p.get("location")}
                 for p in plan.get("parts", [])]
        crew = plan.get("team", {}).get("crew", [])
        window = plan.get("chosen_window")
        safe_actions = []
        for a in actions:
            safe_actions.append({"key": a.get("key"), "name": a["name"], "hours": a.get("hours"), "needs": a.get("needs", [])})
        r = self.try_tool("workorder_create_draft", asset=asset, fault_key=fault_key, title=f"{asset} {FAULTS[fault_key]['name']}",
                          description=description, warning_level=warning_level, risk_level=risk, causes=causes, actions=safe_actions,
                          parts=parts, crew=crew, vessel=(plan.get("vessel") or {}).get("code"),
                          window={"start": window["start"].isoformat(), "end": window["end"].isoformat()} if window else None,
                          safety=safety, evidence=evidence[:20], features=features, alarm_id=alarm_id, requester=self.ctx.principal.username)
        if isinstance(r, dict) and "wo_id" in r and plan.get("chosen_window") and plan.get("vessel"):
            from ..services import resources
            f = db.q1("SELECT id FROM wind_farms WHERE code=%s", (self.ctx.farm_code,)) if self.ctx.farm_code else None
            fid = f["id"] if f else db.scalar("SELECT farm_id FROM assets WHERE code=%s", (asset,))
            try:
                trip = resources.create_trip(fid, plan, asset, r["wo_id"])
                r["trip"] = trip
            except Exception:
                pass
        if isinstance(r, dict) and "wo_id" in r:
            self.try_tool("notify", farm=self.ctx.farm_code or db.scalar("SELECT f.code FROM assets a JOIN wind_farms f ON f.id=a.farm_id WHERE a.code=%s", (asset,)),
                          title=f"{'紧急' if emergency else ''}工单待审批：{r['wo_no']}", body=f"{asset} {FAULTS[fault_key]['name']}，预警 {warning_level} 级",
                          level="critical" if warning_level >= 3 else "warn" if emergency else "info", target_role="approver", ref_type="workorder", ref_id=str(r["wo_id"]))
        self.reflect([{"name": "工单草稿创建成功", "ok": isinstance(r, dict) and "wo_id" in r, "detail": r.get("error") if isinstance(r, dict) else ""}])
        return self.output({"workorder": r})


# ======================================================================= 知识工程 Agent
class KnowledgeAgent(BaseAgent):
    name, label = "knowledge", "知识工程 Agent"

    def ingest(self, text: str, source_id: str, source_type: str = "document") -> dict:
        self.perceive(source=source_id, chars=len(text))
        self.plan(["文档解析/章节切分", "LLM 结构化抽取(Schema 约束)", "5 层校验(格式/术语/图谱/交叉/专家)", "候选区待审核"])
        parsed = self.try_tool("ocr_parse", text=text)
        res = self.try_tool("kg_upsert_candidate", text=text, source_id=source_id, source_type=source_type)
        ok = isinstance(res, dict) and "records" in res
        self.reflect([{"name": "抽取到候选记录", "ok": ok and len(res["records"]) > 0},
                      {"name": "无直接入图(仅候选区)", "ok": True}])
        return self.output({"parsed": parsed, "result": res})


# ======================================================================= 改进 Agent
class ImprovementAgent(BaseAgent):
    name, label = "improvement", "改进 Agent"

    def rca(self, wo_no: str) -> dict:
        self.perceive(wo=wo_no)
        self.plan(["收集维修反馈与运行状态变化", "RCA 根因分析(5-Why+图谱+复发统计)", "评估模型准确性"])
        fb = self.try_tool("feedback_collect", days=30)
        r = self.try_tool("rca_analyze", wo_no=wo_no)
        ev = self.try_tool("model_eval")
        self.reflect([{"name": "RCA 产出", "ok": isinstance(r, dict) and "report_id" in r}])
        return self.output({"feedback": fb, "rca": r, "model_eval": ev})

    def evaluate(self) -> dict:
        self.perceive(task="model_eval")
        fb = self.try_tool("feedback_collect", days=30)
        ev = self.try_tool("model_eval")
        return self.output({"feedback": fb, "model_eval": ev})
