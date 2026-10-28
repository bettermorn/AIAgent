"""具体工具实现与 Agent 最小权限授权（文档 3.5 工具表 + 4.2 Agent 权限表）。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .. import db, llm, security
from ..db import J
from ..ontology import FAULTS, SENSOR_NAME, SENSOR_UNIT, TURBINE_SENSORS
from ..services import (diagnosis_model as dm, documents, efficiency, kg, knowledge_eng as ke, modelreg, resources, rules as rules_svc,
                        timeseries as ts, workorders as wos)
from .registry import PermissionDenied, TaskCtx, Tool, ToolError, registry, validate_asset_code

UTC = dt.timezone.utc


# ============================================================ 参数模型
class KgQueryArgs(BaseModel):
    op: Literal["subgraph", "fault_knowledge", "similar_cases", "search", "component_history", "stats"] = "subgraph"
    entity: Optional[str] = Field(None, description="实体编码/名称，如 WT-023")
    fault_key: Optional[str] = None
    depth: int = Field(2, ge=1, le=4)
    limit: int = Field(5, ge=1, le=20)


class KgUpsertArgs(BaseModel):
    text: str = Field(..., min_length=10, max_length=6000)
    source_id: str = Field(..., min_length=2, max_length=80)
    source_type: Literal["document", "workorder", "expert"] = "document"


class DocSearchArgs(BaseModel):
    query: str = Field(..., min_length=2, max_length=300)
    top_k: int = Field(4, ge=1, le=10)
    doc_types: Optional[list[str]] = None
    model: Optional[str] = None


class ScadaArgs(BaseModel):
    asset: str
    sensors: Optional[list[str]] = None
    minutes: float = Field(120, ge=1, le=1440)


class AlarmArgs(BaseModel):
    farm: Optional[str] = None
    asset: Optional[str] = None
    status: Literal["open", "all"] = "open"
    limit: int = Field(20, ge=1, le=100)


class WoSearchArgs(BaseModel):
    fault_key: Optional[str] = None
    asset: Optional[str] = None
    keyword: Optional[str] = Field(None, max_length=60)
    limit: int = Field(5, ge=1, le=20)
    stats: bool = False


class RuleEvalArgs(BaseModel):
    asset: str
    minutes: float = Field(10, ge=1, le=120)


class TsDiagnoseArgs(BaseModel):
    asset: str
    fault_key: str
    minutes: float = Field(120, ge=10, le=720)


class EffArgs(BaseModel):
    farm: str
    asset: Optional[str] = None
    minutes: float = Field(180, ge=30, le=1440)


class SpareArgs(BaseModel):
    farm: str
    codes: list[str] = Field(..., min_length=1, max_length=12)


class ScheduleArgs(BaseModel):
    farm: str
    asset: str
    actions: list[dict]


class WeatherArgs(BaseModel):
    farm: str
    hours: int = Field(48, ge=6, le=120)


class VideoIrArgs(BaseModel):
    asset: str
    kind: Optional[Literal["video", "infrared", "acoustic", "strain"]] = None


class WoDraftArgs(BaseModel):
    asset: str
    fault_key: str
    title: str = Field(..., max_length=200)
    description: str = Field("", max_length=4000)
    warning_level: int = Field(..., ge=1, le=3)
    risk_level: Literal["L1", "L2", "L3", "L4"] = "L2"
    causes: list[dict] = []
    actions: list[dict] = []
    parts: list[dict] = []
    crew: list[dict] = []
    vessel: Optional[str] = None
    window: Optional[dict] = None
    safety: dict = {}
    evidence: list[dict] = []
    features: dict = {}
    alarm_id: Optional[int] = None
    requester: str = "agent"


class WoTrackArgs(BaseModel):
    wo_no: Optional[str] = None
    asset: Optional[str] = None


class NotifyArgs(BaseModel):
    farm: str
    title: str = Field(..., max_length=200)
    body: str = Field("", max_length=1000)
    level: Literal["info", "warn", "critical"] = "info"
    target_role: Optional[str] = None
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None


class IamArgs(BaseModel):
    farm: str
    action: str


class SafetyArgs(BaseModel):
    farm: str
    needs: list[str] = []
    window: Optional[dict] = None
    team: dict = {}
    action_names: list[str] = []


class PermitArgs(BaseModel):
    wo_no: Optional[str] = None
    kind: Optional[str] = None


class RcaArgs(BaseModel):
    wo_no: str


class FeedbackArgs(BaseModel):
    days: int = Field(30, ge=1, le=365)


class ModelEvalArgs(BaseModel):
    pass


class OcrArgs(BaseModel):
    text: str = Field(..., min_length=5, max_length=20000)


class LlmExtractArgs(BaseModel):
    text: str = Field(..., min_length=10, max_length=6000)
    source_id: str


class KpiArgs(BaseModel):
    farm: Optional[str] = None
    days: int = Field(30, ge=1, le=365)


class ReportArgs(BaseModel):
    farm: str
    period: Literal["monthly", "quarterly", "yearly"] = "monthly"
    key: Optional[str] = None


class CrossFarmArgs(BaseModel):
    farms: list[str] = Field(..., min_length=1, max_length=10)


# ============================================================ 实现
def _kg_query(ctx: TaskCtx, a: KgQueryArgs):
    if a.op == "stats":
        return kg.stats()
    if a.op == "fault_knowledge":
        if not a.fault_key:
            raise ToolError("fault_knowledge 需要 fault_key")
        r = kg.fault_knowledge(a.fault_key)
        if not r:
            raise ToolError(f"图谱中无故障: {a.fault_key}")
        return r
    if a.op == "similar_cases":
        if not a.fault_key:
            raise ToolError("similar_cases 需要 fault_key")
        model = None
        if a.entity:
            asset = ctx.require_farm_of_asset(validate_asset_code(a.entity))
            model = asset["model"]
        return kg.similar_cases(a.fault_key, model=model, limit=a.limit)
    if a.op == "component_history":
        if not a.entity:
            raise ToolError("需要 entity=部件编码")
        return kg.component_installed_history(a.entity)
    if a.op == "search":
        return kg.search_entities(a.entity or "", a.limit)
    if not a.entity:
        raise ToolError("subgraph 需要 entity")
    key = a.entity.strip().upper() if kg.get_entity(None, a.entity.strip().upper()) else a.entity.strip()
    ent = kg.get_entity(None, key)
    if ent and ent["type"] in ("Turbine", "Substation", "Cable", "Mast", "Component"):
        ctx.require_farm_of_asset(ent["key"]) if db.q1("SELECT 1 FROM assets WHERE code=%s", (ent["key"],)) else None
    g = kg.subgraph(key, a.depth, max_nodes=120)
    if not g["nodes"]:
        raise ToolError(f"图谱中无实体: {a.entity}")
    return {"nodes": len(g["nodes"]), "edges": len(g["edges"]), "root": g["root"],
            "nodes_sample": [{"type": n["type"], "key": n["key"], "name": n["name"]} for n in g["nodes"][:60]],
            "edges_sample": [{"rel": e["rel"], "src": e["source"], "dst": e["target"]} for e in g["edges"][:80]]}


def _kg_upsert(ctx: TaskCtx, a: KgUpsertArgs):
    # 只写候选区；入图须经审核。使用 LLM 抽取 + 五层校验
    return ke.ingest_text(a.text, a.source_id, a.source_type, actor=ctx.principal.username)


def _doc_search(ctx: TaskCtx, a: DocSearchArgs):
    return documents.search(a.query, top_k=a.top_k, doc_types=a.doc_types, model=a.model, only_active=True)


def _scada(ctx: TaskCtx, a: ScadaArgs):
    code = validate_asset_code(a.asset)
    asset = ctx.require_farm_of_asset(code)
    sensors = a.sensors or (TURBINE_SENSORS if asset["type"] == "turbine" else None)
    if sensors:
        bad = [s for s in sensors if s not in SENSOR_NAME]
        if bad:
            raise ToolError(f"未知传感器: {bad}")
    else:
        sensors = [r["sensor_type"] for r in db.q("SELECT DISTINCT sensor_type FROM ts_realtime WHERE asset_code=%s", (code,))]
    stats = ts.window_stats(code, sensors, a.minutes)
    out = {}
    for s, v in stats.items():
        out[s] = {"name": SENSOR_NAME.get(s, s), "unit": SENSOR_UNIT.get(s, ""), "first": round(v["first"], 2), "last": round(v["last"], 2),
                  "mean": round(v["mean"], 2), "max": round(v["max"], 2), "min": round(v["min"], 2), "slope_per_h": round(v["slope_per_h"], 2)}
    if not out:
        raise ToolError(f"{code} 在近 {a.minutes:.0f} 分钟无时序数据")
    return {"asset": code, "minutes": a.minutes, "sensors": out}


def _alarm_query(ctx: TaskCtx, a: AlarmArgs):
    farm = a.farm
    if farm:
        ctx.require_farm(farm)
    rows = db.q("""SELECT al.id, f.code farm, al.asset_code, al.title, al.fault_key, al.level, al.value, al.threshold, al.status, al.raised_at, al.wo_id
                   FROM alarms al JOIN wind_farms f ON f.id=al.farm_id
                   WHERE (%s::text IS NULL OR f.code=%s) AND (%s::text IS NULL OR al.asset_code=%s)
                     AND (%s='all' OR al.status IN ('open','acknowledged'))
                   ORDER BY al.level DESC, al.raised_at DESC LIMIT %s""",
                (farm, farm, a.asset, a.asset, a.status, a.limit))
    return [r for r in rows if ctx.principal.can_farm(r["farm"])]


def _wo_search(ctx: TaskCtx, a: WoSearchArgs):
    if a.stats:
        return db.q("""SELECT fault_key, root_cause, count(*) n, round(avg(response_minutes)::numeric,1) avg_resp, round(avg(repair_minutes)::numeric,1) mttr
                       FROM work_orders WHERE status='closed' AND (%s::text IS NULL OR fault_key=%s) GROUP BY 1,2 ORDER BY n DESC LIMIT %s""",
                    (a.fault_key, a.fault_key, a.limit))
    rows = db.q("""SELECT w.wo_no, w.asset_code, w.title, w.fault_key, w.root_cause, w.actual_actions, w.result, w.response_minutes, w.repair_minutes, w.closed_at, f.code farm
                   FROM work_orders w JOIN wind_farms f ON f.id=w.farm_id
                   WHERE (%s::text IS NULL OR w.fault_key=%s) AND (%s::text IS NULL OR w.asset_code=%s)
                     AND (%s::text IS NULL OR w.title ILIKE %s OR w.root_cause ILIKE %s OR w.description ILIKE %s) AND w.status='closed'
                   ORDER BY w.closed_at DESC NULLS LAST LIMIT %s""",
                (a.fault_key, a.fault_key, a.asset, a.asset, a.keyword, f"%{a.keyword}%", f"%{a.keyword}%", f"%{a.keyword}%", a.limit))
    return [r for r in rows if ctx.principal.can_farm(r["farm"])]


def _rule_eval(ctx: TaskCtx, a: RuleEvalArgs):
    code = validate_asset_code(a.asset)
    asset = ctx.require_farm_of_asset(code)
    stats = ts.window_stats(code, list(SENSOR_NAME), a.minutes)
    vals = {s: v["mean"] for s, v in stats.items()}
    res = [r for r in rules_svc.rule_eval(vals) if r["sensor"] in vals]
    kind = asset["type"]
    res = [r for r in res if db.q1("SELECT 1 FROM rules WHERE code=%s AND asset_kind=%s", (r["rule"], kind))]
    return {"asset": code, "results": res, "max_level": max([r["level"] for r in res], default=0)}


def _ts_diagnose(ctx: TaskCtx, a: TsDiagnoseArgs):
    code = validate_asset_code(a.asset)
    ctx.require_farm_of_asset(code)
    if a.fault_key not in FAULTS:
        raise ToolError(f"未知故障类型 {a.fault_key}，可选：{list(FAULTS)}")
    return dm.diagnose(code, a.fault_key, a.minutes)


def _efficiency(ctx: TaskCtx, a: EffArgs):
    f = ctx.require_farm(a.farm)
    if a.asset:
        code = validate_asset_code(a.asset)
        ctx.require_farm_of_asset(code)
        return efficiency.evaluate_turbine(code, a.minutes, farm_id=f["id"])
    return efficiency.evaluate_farm(f["id"], a.minutes)


def _spare(ctx: TaskCtx, a: SpareArgs):
    f = ctx.require_farm(a.farm)
    return {"local": resources.spare_query(a.codes, f["id"]), "other_farms": resources.other_farm_stock(a.codes, f["id"])}


def _schedule(ctx: TaskCtx, a: ScheduleArgs):
    f = ctx.require_farm(a.farm)
    validate_asset_code(a.asset)
    return resources.plan_resources(f["id"], a.actions, turbine=a.asset)


def _weather_ais(ctx: TaskCtx, a: WeatherArgs):
    f = ctx.require_farm(a.farm)
    rows = db.q("""SELECT ts, wind_speed, wave_height, visibility_km FROM weather_forecast WHERE farm_id=%s AND ts >= now() - interval '1 hour'
                   AND ts < now() + make_interval(hours => %s) ORDER BY ts""", (f["id"], a.hours))
    step = max(1, len(rows) // 24)
    return {"current": resources.current_sea(f["id"]), "forecast": rows[::step],
            "windows_climb": resources.windows(f["id"], 3, 1.5, 12.0, 2.0, within_hours=a.hours), "ais": resources.ais_nearby(f["id"])}


def _video_ir(ctx: TaskCtx, a: VideoIrArgs):
    code = validate_asset_code(a.asset)
    ctx.require_farm_of_asset(code)
    return db.q("""SELECT kind, ts, summary, object_key FROM monitoring_media WHERE asset_code=%s AND (%s::text IS NULL OR kind=%s)
                   ORDER BY ts DESC LIMIT 8""", (code, a.kind, a.kind))


def _wo_draft(ctx: TaskCtx, a: WoDraftArgs):
    code = validate_asset_code(a.asset)
    asset = ctx.require_farm_of_asset(code)
    if a.fault_key not in FAULTS:
        raise ToolError(f"未知故障: {a.fault_key}")
    spec = FAULTS[a.fault_key]
    comp = db.q1("SELECT code FROM assets WHERE type='component' AND comp_type=%s AND props->>'host'=%s LIMIT 1", (spec["comp"], code))
    # 同一设备同一故障已有未结工单则不重复创建
    dup = db.q1("""SELECT wo_no FROM work_orders WHERE asset_code=%s AND fault_key=%s AND status IN ('draft','pending_approval','approved','dispatched','in_progress') LIMIT 1""",
                (code, a.fault_key))
    if dup:
        raise ToolError(f"设备 {code} 已存在未结工单 {dup['wo_no']}，不重复创建")
    alarm = db.q1("SELECT raised_at FROM alarms WHERE id=%s", (a.alarm_id,)) if a.alarm_id else None
    wo = wos.create_draft(
        farm_id=asset["farm_id"], asset_code=code, comp_code=comp["code"] if comp else None, title=a.title, description=a.description,
        fault_key=a.fault_key, warning_level=a.warning_level, risk_level=a.risk_level, causes=a.causes, actions=a.actions, parts=a.parts,
        crew=a.crew, vessel=a.vessel, window=a.window, safety=a.safety, evidence=a.evidence, features=a.features, alarm_id=a.alarm_id,
        alarm_time=alarm["raised_at"] if alarm else None, task_id=ctx.task_id, requester=ctx.principal.username)
    # 紧急工单直接提交审批(进入 30min 响应计时); 普通工单留草稿由人确认提交
    if wo["wo_type"] == "emergency":
        wo = wos.submit(wo["id"], "workorder-agent")
    return {"wo_id": wo["id"], "wo_no": wo["wo_no"], "type": wo["wo_type"], "status": wo["status"], "warning_level": wo["warning_level"],
            "approval_level": wo["risk_level"]}


def _wo_track(ctx: TaskCtx, a: WoTrackArgs):
    rows = db.q("""SELECT w.wo_no, w.asset_code, w.status, w.wo_type, w.warning_level, w.response_minutes, w.repair_minutes, w.created_at, f.code farm
                   FROM work_orders w JOIN wind_farms f ON f.id=w.farm_id
                   WHERE (%s::text IS NULL OR w.wo_no=%s) AND (%s::text IS NULL OR w.asset_code=%s) ORDER BY w.created_at DESC LIMIT 10""",
                (a.wo_no, a.wo_no, a.asset, a.asset))
    return [r for r in rows if ctx.principal.can_farm(r["farm"])]


def _notify(ctx: TaskCtx, a: NotifyArgs):
    f = ctx.require_farm(a.farm)
    rules_svc.notify(f["id"], a.level, a.title, a.body, a.ref_type, a.ref_id, a.target_role)
    return {"sent": True}


def _iam(ctx: TaskCtx, a: IamArgs):
    p = ctx.principal
    perm = {"create_workorder": "task:create", "approve": "approve:L2", "execute": "wo:execute", "publish_strategy": "strategy:publish"}.get(a.action, a.action)
    return {"user": p.username, "role": p.role, "farm": a.farm, "farm_ok": p.can_farm(a.farm), "action": a.action, "action_ok": p.can(perm),
            "quals": p.quals}


def _safety_eval(ctx: TaskCtx, a: SafetyArgs):
    f = ctx.require_farm(a.farm)
    risky = [n for n in a.action_names if security.contains_l3(n)]
    risky_kw = sorted({k for n in a.action_names for k in security.contains_l3(n)})
    w = a.window
    if w:
        for k in ("start", "end"):
            if isinstance(w.get(k), str):
                w[k] = dt.datetime.fromisoformat(w[k])
    return resources.safety_check(f["id"], a.needs, w, a.team, risky_kw)


def _permit_query(ctx: TaskCtx, a: PermitArgs):
    return db.q("""SELECT p.permit_no, p.kind, p.status, p.holder, p.second_signer, w.wo_no FROM work_permits p LEFT JOIN work_orders w ON w.id=p.wo_id
                   WHERE (%s::text IS NULL OR w.wo_no=%s) ORDER BY p.id DESC LIMIT 10""", (a.wo_no, a.wo_no))


def _rca(ctx: TaskCtx, a: RcaArgs):
    from ..services import improve
    wo = wos.get_by_no(a.wo_no)
    if not wo:
        raise ToolError(f"工单不存在: {a.wo_no}")
    rep = improve.rca(wo["id"])
    return {"report_id": rep["id"], "root_cause": rep["root_cause"], "recommendations": rep["recommendations"], "analysis": rep["analysis"]}


def _feedback(ctx: TaskCtx, a: FeedbackArgs):
    from ..services import improve
    return improve.collect_feedback(a.days)


def _model_eval(ctx: TaskCtx, a: ModelEvalArgs):
    from ..services import improve
    p = modelreg.params("cause_ranker")
    return {"model": modelreg.version_tag("cause_ranker"), "workorders": improve.evaluate_params(p), "golden": improve.evaluate_golden(p)}


def _ocr(ctx: TaskCtx, a: OcrArgs):
    # 文本已由上游解析(MinerU/PaddleOCR)。此处做章节切分 + 版本标记 + 来源标识, 供抽取使用
    chunks = documents.split_sections(a.text)
    return {"chunks": len(chunks), "sections": [c["section"] for c in chunks if c["section"]][:20], "sample": chunks[0]["text"][:200] if chunks else ""}


def _llm_extract(ctx: TaskCtx, a: LlmExtractArgs):
    recs = ke.extract_records(a.text, a.source_id)
    return [r.model_dump() for r in recs]


def _kpi(ctx: TaskCtx, a: KpiArgs):
    fid = None
    if a.farm:
        fid = ctx.require_farm(a.farm)["id"]
    since = dt.datetime.now(UTC) - dt.timedelta(days=a.days)
    k = wos.kpis(fid, since)
    by_status = db.q("""SELECT w.status, count(*) n FROM work_orders w JOIN wind_farms f ON f.id=w.farm_id
                        WHERE (%s::int IS NULL OR w.farm_id=%s) AND w.created_at >= %s AND f.code = ANY(%s) GROUP BY 1 ORDER BY n DESC""",
                     (fid, fid, since, _allowed_farms(ctx)))
    pending = db.q("""SELECT w.wo_no, w.asset_code, w.title, w.status, w.wo_type, w.warning_level FROM work_orders w JOIN wind_farms f ON f.id=w.farm_id
                      WHERE w.status IN ('draft','pending_approval') AND f.code = ANY(%s) ORDER BY w.created_at DESC LIMIT 10""", (_allowed_farms(ctx),))
    return {"kpis": k, "by_status": by_status, "pending": pending, "days": a.days}


def _allowed_farms(ctx: TaskCtx) -> list[str]:
    rows = db.q("SELECT code FROM wind_farms")
    return [r["code"] for r in rows if ctx.principal.can_farm(r["code"])]


def _report(ctx: TaskCtx, a: ReportArgs):
    from ..services import reports
    f = ctx.require_farm(a.farm)
    r = reports.generate(f["id"], a.period, a.key)
    return {"report_id": r["id"], "period": r["period"], "key": r["period_key"], "kpis": r["kpis"], "narrative": r["narrative"]}


def _cross_farm(ctx: TaskCtx, a: CrossFarmArgs):
    allowed = [c for c in a.farms if ctx.principal.can_farm(c)]
    if len(allowed) < len(a.farms):
        raise PermissionDenied("无权访问部分风场(ABAC)，跨场调度需拥有所有涉及风场的授权")
    return resources.cross_farm_dispatch(allowed)


# ============================================================ 注册
def _reg(name, desc, model, fn, mode="read", perm=None):
    registry.register(Tool(name, desc, model, fn, mode, perm))


_reg("kg_query", "知识图谱查询: 设备结构/因果路径/相似故障/部件履历", KgQueryArgs, _kg_query)
_reg("kg_upsert_candidate", "抽取并写入知识图谱候选区(待审核)", KgUpsertArgs, _kg_upsert, "write_candidate", "knowledge:ingest")
_reg("doc_search", "规程/说明书混合检索(默认仅最新有效版本)", DocSearchArgs, _doc_search)
_reg("scada_query", "查询 SCADA/时序库窗口统计", ScadaArgs, _scada)
_reg("alarm_query", "查询当前/历史告警及预警级别", AlarmArgs, _alarm_query)
_reg("workorder_search", "历史工单/相似案例/响应修复时长统计", WoSearchArgs, _wo_search)
_reg("rule_eval", "阈值与规程约束规则评估(多级预警)", RuleEvalArgs, _rule_eval)
_reg("ts_diagnose", "时序诊断模型: 异常检测/原因排序/趋势/健康评分", TsDiagnoseArgs, _ts_diagnose)
_reg("efficiency_eval", "能效评估模型: 发电效率与优化建议", EffArgs, _efficiency)
_reg("spare_query", "备件库存与到货周期(含跨场库存)", SpareArgs, _spare)
_reg("resource_schedule", "人员/船舶/海况窗口/出海合并的资源方案", ScheduleArgs, _schedule)
_reg("weather_ais_query", "海洋气象预报、作业窗口与 AIS 船舶动态", WeatherArgs, _weather_ais)
_reg("video_ir_query", "视频/红外热像/声学/结构应变监测数据检索", VideoIrArgs, _video_ir)
_reg("workorder_create_draft", "创建待审批工单草稿/紧急工单", WoDraftArgs, _wo_draft, "write_draft", "task:create")
_reg("workorder_track", "工单状态与响应/修复时长跟踪", WoTrackArgs, _wo_track)
_reg("notify", "报警推送/决策建议提示", NotifyArgs, _notify, "write")
_reg("iam_check", "校验用户对风场/动作的权限(ABAC)", IamArgs, _iam)
_reg("safety_rule_eval", "作业风险评估: 海况/资质/作业票/L3 动作", SafetyArgs, _safety_eval)
_reg("permit_query", "作业票查询", PermitArgs, _permit_query)
_reg("rca_analyze", "对已关闭工单做根因分析(RCA)", RcaArgs, _rca)
_reg("feedback_collect", "收集维修反馈与运行状态变化", FeedbackArgs, _feedback)
_reg("model_eval", "评估诊断模型准确性(闭环工单+黄金集)", ModelEvalArgs, _model_eval)
_reg("ocr_parse", "文档解析/章节切分(OCR 结果)", OcrArgs, _ocr)
_reg("llm_extract", "LLM 结构化知识抽取", LlmExtractArgs, _llm_extract)
_reg("kpi_query", "工单绩效KPI(自动派发率/响应时间/MTTR)与状态分布", KpiArgs, _kpi)
_reg("report_generate", "生成月/季/年度绩效与KPI报表", ReportArgs, _report)
_reg("cross_farm_dispatch", "跨风场人员/船舶/备件协同调度建议(规范6.4.3)", CrossFarmArgs, _cross_farm)

# ---- 最小权限授权(文档 4.2)；总控 Agent 无任何业务工具 ----
registry.grant("orchestrator", [])
registry.grant("knowledge", ["ocr_parse", "llm_extract", "kg_query", "kg_upsert_candidate"])
registry.grant("diagnosis", ["scada_query", "alarm_query", "ts_diagnose", "rule_eval", "efficiency_eval", "video_ir_query"])
registry.grant("retrieval", ["kg_query", "doc_search", "workorder_search"])
registry.grant("safety", ["iam_check", "safety_rule_eval", "permit_query", "weather_ais_query"])
registry.grant("resource", ["spare_query", "resource_schedule", "weather_ais_query", "cross_farm_dispatch"])
registry.grant("workorder", ["workorder_create_draft", "workorder_track", "notify", "kpi_query"])
registry.grant("improvement", ["workorder_search", "ts_diagnose", "kg_upsert_candidate", "rca_analyze", "feedback_collect", "model_eval",
                               "kpi_query", "report_generate"])
