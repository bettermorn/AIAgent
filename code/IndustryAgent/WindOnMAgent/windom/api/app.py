"""API 层（文档 5.3）：认证、限流、BFF 聚合、SSE/WebSocket、OpenAPI 3，路径前缀 /api/v1。"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import queue
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import db, llm, security
from ..agents import orchestrator as orch
from ..config import settings
from ..jobs import scheduler
from ..ontology import FAULTS, SENSOR_NAME, SENSOR_UNIT, WARNING_LEVELS
from ..services import (documents, efficiency, faults, improve, kg, knowledge_eng, modelreg, reports, resources, rules as rules_svc,
                        settle, timeseries as ts, workorders as wos)
from ..tools.registry import PermissionDenied, registry
from ..tools import defs  # noqa: F401

log = logging.getLogger("windom.api")
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
UTC = dt.timezone.utc


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db.init_db()
    from .. import seed
    if not seed.seeded():
        log.info("首次启动: 写入初始化数据…")
        await asyncio.to_thread(seed.seed_all)
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="海上风电场运维智能体 API", version="1.0.0", lifespan=lifespan,
              description="Offshore Wind O&M Agent — 技术设计方案 V2.0 的工程实现。/api/v1/...")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def J(o: Any) -> JSONResponse:
    return JSONResponse(jsonable_encoder(o, custom_encoder={dt.datetime: lambda d: d.isoformat()}))


# ---------------------------------------------------------------- 限流 / 安全中间件
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        key = (request.client.host if request.client else "?") + ":" + ("llm" if request.method == "POST" and "/agent/tasks" in request.url.path else "api")
        limit = 30 if key.endswith("llm") else 600
        now = time.time()
        with _hits_lock:
            dq = _hits[key]
            while dq and now - dq[0] > 60:
                dq.popleft()
            if len(dq) >= limit:
                return JSONResponse({"detail": "请求过于频繁，请稍后再试"}, status_code=429)
            dq.append(now)
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    return resp


@app.exception_handler(PermissionDenied)
async def _perm(_: Request, e: PermissionDenied):
    return JSONResponse({"detail": str(e)}, status_code=403)


@app.exception_handler(PermissionError)
async def _perm2(_: Request, e: PermissionError):
    return JSONResponse({"detail": str(e)}, status_code=403)


@app.exception_handler(security.AuthError)
async def _auth(_: Request, e: security.AuthError):
    return JSONResponse({"detail": str(e)}, status_code=e.status)


@app.exception_handler(wos.WorkflowError)
async def _wf(_: Request, e: wos.WorkflowError):
    return JSONResponse({"detail": str(e)}, status_code=409)


@app.exception_handler(ValueError)
async def _val(_: Request, e: ValueError):
    return JSONResponse({"detail": str(e)}, status_code=400)


def current(request: Request) -> security.Principal:
    h = request.headers.get("authorization", "")
    token = h[7:] if h.lower().startswith("bearer ") else request.query_params.get("access_token", "")
    if not token:
        raise security.AuthError("未登录")
    return security.principal_from_token(token)


def need(perm: str):
    def dep(p: security.Principal = Depends(current)) -> security.Principal:
        if not p.can(perm):
            raise PermissionDenied(f"当前角色({p.role})缺少权限 {perm}")
        return p
    return dep


def farm_guard(p: security.Principal, farm: Optional[str]) -> None:
    if farm and not p.can_farm(farm):
        raise PermissionDenied(f"无权访问风场 {farm}")


def allowed_farms(p: security.Principal) -> Optional[list[str]]:
    if "*" in p.farms:
        return None
    return p.farms


# ================================================================= 认证
class LoginReq(BaseModel):
    username: str
    password: str


@app.post("/api/v1/auth/login", tags=["auth"])
def login(req: LoginReq):
    token, p = security.login(req.username, req.password)
    return J({"token": token, "user": p.public()})


@app.get("/api/v1/auth/me", tags=["auth"])
def me(p: security.Principal = Depends(current)):
    return J(p.public())


@app.get("/api/v1/health", tags=["system"])
def health():
    return J({"status": "ok", "db": db.health()["ok"], "llm": llm.available(), "time": dt.datetime.now(UTC)})


# ================================================================= Agent 任务
class TaskReq(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    kind: str = "auto"
    farm: Optional[str] = None
    asset: Optional[str] = None
    alarm_id: Optional[int] = None
    fault_key: Optional[str] = None
    period: Optional[str] = None
    source_id: Optional[str] = None
    text: Optional[str] = None
    wait: bool = False


@app.post("/api/v1/agent/tasks", tags=["agent"])
async def create_task(req: TaskReq, p: security.Principal = Depends(need("task:create"))):
    farm_guard(p, req.farm)
    kinds = {"auto", "ask", "qa", "diagnose", "alarm", "stats", "efficiency", "report", "schedule", "improve", "knowledge_extract"}
    if req.kind not in kinds:
        raise HTTPException(400, f"kind 必须是 {sorted(kinds)}")
    payload = {k: v for k, v in req.model_dump().items() if k not in ("query", "kind", "wait") and v is not None}
    if req.kind == "knowledge_extract" and not p.can("knowledge:ingest"):
        raise PermissionDenied("无知识抽取权限")
    if req.asset:
        a = db.q1("SELECT f.code FROM assets a JOIN wind_farms f ON f.id=a.farm_id WHERE a.code=%s", (req.asset.upper(),))
        if a:
            farm_guard(p, a["code"])
        payload["asset"] = req.asset.upper()
    t = orch.create_task(req.kind, req.query, p, payload=payload, farm_code=req.farm)
    if req.wait:
        res = await asyncio.to_thread(orch.run_task, t["id"], p)
        return J({"task_id": str(t["id"]), **res})
    orch.run_task_async(t["id"], p)
    return J({"task_id": str(t["id"]), "status": "Received", "stream": f"/api/v1/agent/tasks/{t['id']}/stream"})


def _task_visible(t: dict, p: security.Principal) -> None:
    if p.role in ("admin", "system") or t["requester"] == p.username:
        return
    if p.can("approve:L1") or p.can("task:takeover"):
        if not t["farm_code"] or p.can_farm(t["farm_code"]):
            return
    raise PermissionDenied("无权查看该任务")


@app.get("/api/v1/agent/tasks", tags=["agent"])
def list_tasks(limit: int = 30, status: Optional[str] = None, p: security.Principal = Depends(current)):
    rows = db.q("""SELECT id, kind, query, requester, status, risk_level, farm_code, wo_id, alarm_id, created_at, finished_at, tokens, tool_calls
                   FROM agent_tasks WHERE (%s::text IS NULL OR status=%s) ORDER BY created_at DESC LIMIT %s""", (status, status, limit * 3))
    out = []
    for r in rows:
        try:
            _task_visible({**r}, p)
            out.append(r)
        except PermissionDenied:
            continue
    return J(out[:limit])


@app.get("/api/v1/agent/tasks/{task_id}", tags=["agent"])
def get_task(task_id: str, p: security.Principal = Depends(current)):
    t = orch.get_task(task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    _task_visible(t, p)
    return J(t)


@app.get("/api/v1/agent/tasks/{task_id}/stream", tags=["agent"])
async def stream_task(task_id: str, request: Request, p: security.Principal = Depends(current)):
    """SSE: 先回放已有事件，再订阅实时事件，直到任务进入终态。"""
    t = orch.get_task(task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    _task_visible(t, p)
    q: queue.Queue = queue.Queue()
    unsub = orch.subscribe(task_id, q.put)
    past = db.q("SELECT seq, ts, agent, type, payload FROM agent_events WHERE task_id=%s ORDER BY seq", (task_id,))
    last_seq = past[-1]["seq"] if past else 0

    async def gen():
        try:
            for e in past:
                yield f"data: {json.dumps(jsonable_encoder({**e, 'task_id': task_id}), ensure_ascii=False)}\n\n"
            idle = 0
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.to_thread(q.get, True, 1.0)
                    idle = 0
                    if ev["seq"] <= last_seq:
                        continue
                    yield f"data: {json.dumps(jsonable_encoder(ev), ensure_ascii=False)}\n\n"
                    if ev["type"] == "final":
                        break
                except queue.Empty:
                    idle += 1
                    cur = orch.get_task(task_id)
                    if cur and cur["status"] in orch.TERMINAL | {"WaitingApproval", "HumanTakeover"} and idle > 2:
                        yield f"data: {json.dumps({'type': 'final', 'status': cur['status'], 'payload': {'status': cur['status']}})}\n\n"
                        break
                    if idle % 10 == 0:
                        yield ": keepalive\n\n"
        finally:
            unsub()
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class ApproveReq(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject|modify)$")
    comment: str = ""
    modifications: Optional[dict] = None


@app.post("/api/v1/agent/tasks/{task_id}/approve", tags=["agent"])
def approve_task(task_id: str, req: ApproveReq, p: security.Principal = Depends(current)):
    t = orch.get_task(task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    if not t["wo_id"]:
        raise HTTPException(409, "该任务没有待审批的工单")
    wo = wos.decide(t["wo_id"], p, req.decision, req.comment, req.modifications)
    nxt = "Completed" if wo["status"] in ("approved", "dispatched") else "Rejected" if wo["status"] == "rejected" else t["status"]
    db.update("agent_tasks", "id", task_id, {"status": nxt, "updated_at": dt.datetime.now(UTC)})
    return J({"task_status": nxt, "workorder": wo})


class TakeoverReq(BaseModel):
    action: str = Field(..., pattern="^(pause|cancel|resume|rollback)$")
    comment: str = ""


@app.post("/api/v1/agent/tasks/{task_id}/takeover", tags=["agent"])
def takeover(task_id: str, req: TakeoverReq, p: security.Principal = Depends(current)):
    return J(orch.takeover(task_id, p, req.action, req.comment))


@app.get("/api/v1/audit/traces/{task_id}", tags=["audit"])
def audit_trace(task_id: str, p: security.Principal = Depends(current)):
    t = orch.get_task(task_id)
    if not t:
        raise HTTPException(404, "任务不存在")
    _task_visible(t, p)
    events = db.q("SELECT seq, ts, agent, type, payload FROM agent_events WHERE task_id=%s ORDER BY seq", (task_id,))
    events = [e for e in events if e["type"] != "token"]
    audit = db.q("SELECT id, ts, actor, action, detail, hash, prev_hash FROM audit_log WHERE task_id=%s ORDER BY id", (task_id,))
    cps = db.q("SELECT step, node, ts FROM agent_checkpoints WHERE task_id=%s ORDER BY step", (task_id,))
    plan = [e["payload"].get("steps") for e in events if e["type"] == "plan"]
    approvals = db.q("SELECT * FROM approvals WHERE task_id=%s ORDER BY id", (task_id,))
    wo = db.q1("SELECT wo_no, status, wo_type, response_minutes, repair_minutes, closed_at FROM work_orders WHERE id=%s", (t["wo_id"],)) if t["wo_id"] else None
    return J({"task": {k: t[k] for k in ("id", "trace_id", "kind", "query", "requester", "role", "status", "risk_level", "tokens", "tool_calls", "steps", "models", "created_at", "finished_at", "error")},
              "intent": t["intent"], "plan": plan, "events": events, "audit": audit, "checkpoints": cps, "approvals": approvals, "workorder": wo,
              "result": {k: t["result"].get(k) for k in ("confidence", "warning_level", "risk", "sources")} if t["result"] else {}})


@app.get("/api/v1/audit/verify", tags=["audit"])
def audit_verify(p: security.Principal = Depends(need("approve:L3"))):
    return J(security.verify_audit_chain())


@app.get("/api/v1/audit/log", tags=["audit"])
def audit_log(limit: int = 100, action: Optional[str] = None, p: security.Principal = Depends(need("approve:L3"))):
    return J(db.q("SELECT id, ts, task_id, actor, action, detail, hash FROM audit_log WHERE (%s::text IS NULL OR action=%s) ORDER BY id DESC LIMIT %s", (action, action, limit)))


@app.get("/api/v1/agent/tools", tags=["agent"])
def tools(agent: Optional[str] = None, p: security.Principal = Depends(current)):
    return J({"agents": {a: sorted(g) for a, g in registry.grants.items()}, "tools": registry.describe(agent)})


# ================================================================= 风场 / 资产 / 时序 / 告警
@app.get("/api/v1/farms", tags=["farms"])
def farms(p: security.Principal = Depends(current)):
    rows = db.q("""SELECT f.id, f.code, f.name, f.lat, f.lon, f.capacity_mw,
                          (SELECT count(*) FROM assets a WHERE a.farm_id=f.id AND a.type='turbine') turbines,
                          (SELECT count(*) FROM alarms al WHERE al.farm_id=f.id AND al.status IN ('open','acknowledged')) open_alarms,
                          (SELECT count(*) FROM work_orders w WHERE w.farm_id=f.id AND w.status IN ('draft','pending_approval','approved','dispatched','in_progress')) open_wo
                   FROM wind_farms f ORDER BY f.code""")
    return J([r for r in rows if p.can_farm(r["code"])])


@app.get("/api/v1/dashboard", tags=["farms"])
def dashboard(farm: str, p: security.Principal = Depends(current)):
    farm_guard(p, farm)
    f = db.q1("SELECT * FROM wind_farms WHERE code=%s", (farm,))
    if not f:
        raise HTTPException(404, "风场不存在")
    fid = f["id"]
    alarms = db.q("""SELECT id, asset_code, title, fault_key, level, value, threshold, status, raised_at, wo_id, task_id FROM alarms
                     WHERE farm_id=%s AND status IN ('open','acknowledged') ORDER BY level DESC, raised_at DESC""", (fid,))
    turbines = db.q("""SELECT a.code, a.lat, a.lon, a.model,
            (SELECT max(level) FROM alarms al WHERE al.asset_code=a.code AND al.status IN ('open','acknowledged')) level,
            (SELECT value FROM ts_realtime t WHERE t.asset_code=a.code AND t.sensor_type='active_power' ORDER BY ts DESC LIMIT 1) power,
            (SELECT value FROM ts_realtime t WHERE t.asset_code=a.code AND t.sensor_type='wind_speed' ORDER BY ts DESC LIMIT 1) wind
            FROM assets a WHERE a.farm_id=%s AND a.type='turbine' ORDER BY a.code""", (fid,))
    others = db.q("SELECT code, type, name, lat, lon FROM assets WHERE farm_id=%s AND type IN ('substation','cable','mast')", (fid,))
    sea = resources.current_sea(fid)
    tot_p = sum(t["power"] or 0 for t in turbines)
    kp = wos.kpis(fid)
    return J({"farm": f, "alarms": alarms, "turbines": turbines, "others": others, "sea": sea, "total_power_kw": tot_p,
              "status_count": {"normal": sum(1 for t in turbines if not t["level"]), "l1": sum(1 for t in turbines if t["level"] == 1),
                               "l2": sum(1 for t in turbines if t["level"] == 2), "l3": sum(1 for t in turbines if t["level"] == 3)},
              "kpi": kp, "warning_levels": {k: v[0] for k, v in WARNING_LEVELS.items()}})


@app.get("/api/v1/assets/{code}", tags=["farms"])
def asset_detail(code: str, minutes: int = 120, p: security.Principal = Depends(current)):
    code = code.upper()
    a = db.q1("SELECT a.*, f.code farm_code FROM assets a JOIN wind_farms f ON f.id=a.farm_id WHERE a.code=%s", (code,))
    if not a:
        raise HTTPException(404, "设备不存在")
    farm_guard(p, a["farm_code"])
    sensors = [r["sensor_type"] for r in db.q("SELECT DISTINCT sensor_type FROM ts_realtime WHERE asset_code=%s ORDER BY 1", (code,))]
    series = {s: [{"ts": x["ts"], "value": round(x["value"], 3)} for x in ts.series(code, s, minutes, max_points=120)] for s in sensors}
    latest = ts.latest(code)
    from ..services import diagnosis_model as dm
    health = dm.health_score(code, a["farm_id"])
    comps = db.q("SELECT code, name, comp_type FROM assets WHERE type='component' AND props->>'host'=%s ORDER BY code", (code,))
    alarms = db.q("SELECT id, title, level, status, raised_at, value, threshold FROM alarms WHERE asset_code=%s ORDER BY raised_at DESC LIMIT 10", (code,))
    wo = db.q("SELECT wo_no, title, status, wo_type, created_at FROM work_orders WHERE asset_code=%s ORDER BY created_at DESC LIMIT 10", (code,))
    return J({"asset": a, "series": series, "latest": latest, "sensor_names": {s: {"name": SENSOR_NAME.get(s), "unit": SENSOR_UNIT.get(s)} for s in sensors},
              "health": health, "components": comps, "alarms": alarms, "workorders": wo})


@app.get("/api/v1/gis/assets", tags=["gis"])
def gis_assets(farm: str, p: security.Principal = Depends(current)):
    """GIS 运维地图: 风机/故障/工单分布/资源部署/AIS（规范 5.5b）。"""
    farm_guard(p, farm)
    f = db.q1("SELECT * FROM wind_farms WHERE code=%s", (farm,))
    if not f:
        raise HTTPException(404, "风场不存在")
    fid = f["id"]
    assets = db.q("""SELECT a.code, a.type, a.name, a.lat, a.lon,
                     (SELECT max(level) FROM alarms al WHERE al.asset_code=a.code AND al.status IN ('open','acknowledged')) level
                     FROM assets a WHERE a.farm_id=%s AND a.type IN ('turbine','substation','cable','mast')""", (fid,))
    wo = db.q("""SELECT w.wo_no, w.asset_code, w.status, w.wo_type, w.title, a.lat, a.lon FROM work_orders w JOIN assets a ON a.code=w.asset_code
                 WHERE w.farm_id=%s AND w.status IN ('draft','pending_approval','approved','dispatched','in_progress')""", (fid,))
    trips = db.q("SELECT * FROM trip_plans WHERE farm_id=%s AND status IN ('suggested','confirmed') ORDER BY window_start", (fid,))
    vessels = db.q("SELECT code, name, vtype, status FROM vessels WHERE farm_id=%s", (fid,))
    return J({"farm": f, "assets": assets, "workorders": wo, "trips": trips, "vessels": vessels, "ais": resources.ais_nearby(fid),
              "sea": resources.current_sea(fid)})


class AckReq(BaseModel):
    comment: str = ""


@app.post("/api/v1/alarms/{alarm_id}/ack", tags=["alarms"])
def ack_alarm(alarm_id: int, req: AckReq, p: security.Principal = Depends(need("alarm:ack"))):
    a = db.q1("SELECT al.*, f.code farm_code FROM alarms al JOIN wind_farms f ON f.id=al.farm_id WHERE al.id=%s", (alarm_id,))
    if not a:
        raise HTTPException(404, "告警不存在")
    farm_guard(p, a["farm_code"])
    db.update("alarms", "id", alarm_id, {"status": "acknowledged", "acked_at": dt.datetime.now(UTC), "acked_by": p.username})
    security.audit(a["task_id"], None, p.username, "alarm_ack", {"alarm": alarm_id, "comment": req.comment})
    return J({"ok": True})


@app.get("/api/v1/alarms", tags=["alarms"])
def alarms(farm: Optional[str] = None, status: str = "open", limit: int = 100, p: security.Principal = Depends(current)):
    farm_guard(p, farm)
    rows = db.q("""SELECT al.*, f.code farm_code FROM alarms al JOIN wind_farms f ON f.id=al.farm_id
                   WHERE (%s::text IS NULL OR f.code=%s) AND (%s='all' OR al.status IN ('open','acknowledged'))
                   ORDER BY al.raised_at DESC LIMIT %s""", (farm, farm, status, limit))
    return J([r for r in rows if p.can_farm(r["farm_code"])])


@app.get("/api/v1/notifications", tags=["alarms"])
def notifications(limit: int = 30, since_id: int = 0, p: security.Principal = Depends(current)):
    rows = db.q("""SELECT n.*, f.code farm_code FROM notifications n LEFT JOIN wind_farms f ON f.id=n.farm_id WHERE n.id > %s
                   ORDER BY n.id DESC LIMIT %s""", (since_id, limit * 2))
    rows = [r for r in rows if (not r["farm_code"] or p.can_farm(r["farm_code"])) and (not r["target_role"] or r["target_role"] == p.role or p.role in ("admin", "approver"))]
    return J(rows[:limit])


@app.websocket("/api/v1/ws/alerts")
async def ws_alerts(ws: WebSocket, token: str = ""):
    """WebSocket：告警/通知推送(规范 5.5c) 与人工控制通道。"""
    try:
        p = await asyncio.to_thread(security.principal_from_token, token)
    except Exception:
        await ws.close(code=4401)
        return
    await ws.accept()
    last = await asyncio.to_thread(db.scalar, "SELECT coalesce(max(id),0) FROM notifications")
    try:
        while True:
            rows = await asyncio.to_thread(db.q, """SELECT n.id, n.ts, n.level, n.title, n.body, n.ref_type, n.ref_id, n.target_role, f.code farm_code
                                                   FROM notifications n LEFT JOIN wind_farms f ON f.id=n.farm_id WHERE n.id > %s ORDER BY n.id""", (last,))
            for r in rows:
                last = max(last, r["id"])
                if (not r["farm_code"] or p.can_farm(r["farm_code"])) and (not r["target_role"] or r["target_role"] == p.role or p.role in ("admin", "approver")):
                    await ws.send_text(json.dumps(jsonable_encoder(r), ensure_ascii=False))
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=2.0)
                cmd = json.loads(msg)
                if cmd.get("type") == "takeover":
                    try:
                        res = await asyncio.to_thread(orch.takeover, cmd["task_id"], p, cmd.get("action", "pause"), cmd.get("comment", ""))
                    except Exception as e:
                        res = {"error": str(e)}
                    await ws.send_text(json.dumps({"type": "takeover_result", **res}, ensure_ascii=False))
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        return


# ================================================================= 知识图谱 / 知识审核 / 文档
@app.get("/api/v1/kg/subgraph", tags=["kg"])
def kg_subgraph(entity: str, depth: int = 2, as_of: Optional[str] = None, p: security.Principal = Depends(current)):
    ent = kg.get_entity(None, entity) or kg.get_entity(None, entity.upper())
    if ent and db.q1("SELECT 1 FROM assets WHERE code=%s", (ent["key"],)):
        a = db.q1("SELECT f.code FROM assets a JOIN wind_farms f ON f.id=a.farm_id WHERE a.code=%s", (ent["key"],))
        farm_guard(p, a["code"])
    g = kg.subgraph(ent["key"] if ent else entity, depth, as_of=dt.datetime.fromisoformat(as_of) if as_of else None)
    if not g["nodes"]:
        raise HTTPException(404, f"图谱中无实体 {entity}")
    return J(g)


@app.get("/api/v1/kg/search", tags=["kg"])
def kg_search(q: str, p: security.Principal = Depends(current)):
    return J(kg.search_entities(q, 20))


@app.get("/api/v1/kg/stats", tags=["kg"])
def kg_stats(p: security.Principal = Depends(current)):
    return J(kg.stats())


@app.get("/api/v1/kg/fault/{fault_key}", tags=["kg"])
def kg_fault(fault_key: str, p: security.Principal = Depends(current)):
    r = kg.fault_knowledge(fault_key)
    if not r:
        raise HTTPException(404, "故障不存在")
    return J(r)


@app.get("/api/v1/knowledge/candidates", tags=["knowledge"])
def candidates(status: Optional[str] = "pending", p: security.Principal = Depends(need("knowledge:review"))):
    return J(knowledge_eng.list_candidates(None if status == "all" else status))


class ReviewReq(BaseModel):
    decision: str = Field(..., pattern="^(approve|modify|reject)$")
    comment: str = ""
    edits: Optional[dict] = None


@app.post("/api/v1/knowledge/candidates/{cid}/review", tags=["knowledge"])
def review(cid: int, req: ReviewReq, p: security.Principal = Depends(need("knowledge:review"))):
    return J(knowledge_eng.review(cid, req.decision, p, req.comment, req.edits))


class IngestReq(BaseModel):
    text: str = Field(..., min_length=10, max_length=20000)
    source_id: str = Field(..., min_length=2, max_length=80)
    source_type: str = "document"


@app.post("/api/v1/knowledge/ingest", tags=["knowledge"])
async def ingest(req: IngestReq, p: security.Principal = Depends(need("knowledge:ingest"))):
    clean, hits = security.guard_input(req.text, 20000)
    # 文档内容不是指令: 注入语句不拒绝文档, 而在抽取提示中屏蔽(mark_untrusted)，同时审计
    if hits:
        security.audit(None, None, p.username, "ingest_injection_flag", {"source": req.source_id, "hits": hits})
    t = orch.create_task("knowledge_extract", f"知识抽取 {req.source_id}", p, payload={"text": clean, "source_id": req.source_id, "source_type": req.source_type})
    res = await asyncio.to_thread(orch.run_task, t["id"], p)
    return J({"task_id": str(t["id"]), "injection_flags": hits, **res})


@app.get("/api/v1/documents", tags=["knowledge"])
def docs(p: security.Principal = Depends(current)):
    return J(documents.list_documents())


@app.get("/api/v1/documents/search", tags=["knowledge"])
def doc_search(q: str, top_k: int = 5, include_deprecated: bool = False, p: security.Principal = Depends(current)):
    return J(documents.search(q, top_k=top_k, only_active=not include_deprecated))


class DocReq(BaseModel):
    doc_no: str
    title: str
    doc_type: str = "regulation"
    version: str
    text: str = Field(..., min_length=10)
    model: Optional[str] = None


@app.post("/api/v1/documents", tags=["knowledge"])
def doc_upload(req: DocReq, p: security.Principal = Depends(need("doc:manage"))):
    r = documents.ingest(req.doc_no, req.title, req.doc_type, req.version, req.text, model=req.model)
    security.audit(None, None, p.username, "document_ingest", {"doc": req.doc_no, "version": req.version, **{k: v for k, v in r.items() if k != 'kg'}})
    return J(r)


@app.get("/api/v1/terms/stats", tags=["knowledge"])
def term_stats(p: security.Principal = Depends(current)):
    return J(ts.standardization_rate())


# ================================================================= 工单 / 审批
@app.get("/api/v1/workorders", tags=["workorders"])
def list_wo(farm: Optional[str] = None, status: Optional[str] = None, limit: int = 100, p: security.Principal = Depends(current)):
    farm_guard(p, farm)
    return J(wos.list_orders(farm, status, limit, allowed_farms(p)))


@app.get("/api/v1/workorders/{wo_id}", tags=["workorders"])
def get_wo(wo_id: int, p: security.Principal = Depends(current)):
    wo = wos.get(wo_id)
    if not wo:
        raise HTTPException(404, "工单不存在")
    farm_guard(p, wos._farm_code(wo["farm_id"]))
    return J({"workorder": wo, "events": wos.events(wo_id), "approvals": db.q("SELECT * FROM approvals WHERE wo_id=%s ORDER BY id", (wo_id,)),
              "rca": db.q("SELECT * FROM rca_reports WHERE wo_id=%s ORDER BY id DESC", (wo_id,))})


@app.post("/api/v1/workorders/{wo_id}/submit", tags=["workorders"])
def submit_wo(wo_id: int, p: security.Principal = Depends(need("wo:create"))):
    wo = wos.get(wo_id)
    farm_guard(p, wos._farm_code(wo["farm_id"]))
    return J(wos.submit(wo_id, p.username))


@app.post("/api/v1/workorders/{wo_id}/decision", tags=["workorders"])
def decide_wo(wo_id: int, req: ApproveReq, p: security.Principal = Depends(current)):
    wo = wos.decide(wo_id, p, req.decision, req.comment, req.modifications)
    if wo["task_id"]:
        nxt = "Completed" if wo["status"] in ("approved", "dispatched") else "Rejected" if wo["status"] == "rejected" else None
        if nxt:
            db.update("agent_tasks", "id", wo["task_id"], {"status": nxt, "updated_at": dt.datetime.now(UTC)})
    return J(wo)


@app.post("/api/v1/workorders/{wo_id}/start", tags=["workorders"])
def start_wo(wo_id: int, p: security.Principal = Depends(need("wo:execute"))):
    return J(wos.start(wo_id, p))


class CloseReq(BaseModel):
    root_cause_key: Optional[str] = None
    root_cause: str = Field(..., min_length=2)
    actual_actions: list[dict] = []
    result: str = Field(..., min_length=2)
    effective: bool = True
    notes: str = ""


@app.post("/api/v1/workorders/{wo_id}/close", tags=["workorders"])
def close_wo(wo_id: int, req: CloseReq, p: security.Principal = Depends(need("wo:close"))):
    wo = wos.close(wo_id, p, root_cause_key=req.root_cause_key, root_cause=req.root_cause, actual_actions=req.actual_actions, result=req.result,
                   effective=req.effective, notes=req.notes)
    sres = None
    try:
        sres = settle.settle(wo_id)
    except Exception as e:
        log.warning("沉淀失败: %s", e)
    return J({"workorder": wo, "knowledge": sres})


@app.get("/api/v1/approvals", tags=["workorders"])
def approvals(p: security.Principal = Depends(current)):
    rows = db.q("""SELECT ap.*, w.wo_no, w.title, w.asset_code, w.wo_type, w.warning_level, w.alarm_time, f.code farm_code,
                          extract(epoch FROM (now()-coalesce(w.alarm_time, w.created_at)))/60 AS waiting_min
                   FROM approvals ap JOIN work_orders w ON w.id=ap.wo_id JOIN wind_farms f ON f.id=w.farm_id
                   WHERE ap.status='pending' ORDER BY w.wo_type, ap.created_at""")
    return J([r for r in rows if p.can_farm(r["farm_code"])])


@app.get("/api/v1/workorders/{wo_id}/rca", tags=["workorders"])
def wo_rca(wo_id: int, p: security.Principal = Depends(need("wo:close"))):
    return J(improve.rca(wo_id))


class FeedbackReq(BaseModel):
    task_id: Optional[str] = None
    wo_id: Optional[int] = None
    rating: Optional[int] = Field(None, ge=1, le=5)
    correct: Optional[bool] = None
    comment: str = ""


@app.post("/api/v1/feedback", tags=["feedback"])
def feedback(req: FeedbackReq, p: security.Principal = Depends(need("feedback"))):
    r = db.insert("feedback", {"task_id": req.task_id, "wo_id": req.wo_id, "username": p.username, "rating": req.rating,
                               "correct": req.correct, "comment": req.comment[:1000]})
    security.audit(req.task_id, None, p.username, "feedback", {"rating": req.rating, "correct": req.correct})
    return J({"ok": True, "id": r["id"]})


# ================================================================= 资源 / 调度 / 策略
@app.get("/api/v1/resources", tags=["resources"])
def resources_view(farm: str, p: security.Principal = Depends(current)):
    farm_guard(p, farm)
    f = db.q1("SELECT id FROM wind_farms WHERE code=%s", (farm,))
    if not f:
        raise HTTPException(404, "风场不存在")
    fid = f["id"]
    return J({"spares": db.q("SELECT code,name,stock,reserved,location,lead_days FROM spare_parts WHERE farm_id=%s ORDER BY code", (fid,)),
              "personnel": db.q("SELECT code,name,role,quals,cert_expire,status FROM personnel WHERE farm_id=%s ORDER BY code", (fid,)),
              "vessels": db.q("SELECT code,name,vtype,capacity,max_wave,max_wind,status FROM vessels WHERE farm_id=%s", (fid,)),
              "trips": db.q("SELECT * FROM trip_plans WHERE farm_id=%s ORDER BY window_start DESC LIMIT 20", (fid,)),
              "windows": resources.windows(fid, 3, 1.5, 12.0, 2.0, 120), "sea": resources.current_sea(fid)})


@app.get("/api/v1/dispatch/cross-farm", tags=["resources"])
def cross_farm(p: security.Principal = Depends(current)):
    farms_ = [c["code"] for c in db.q("SELECT code FROM wind_farms") if p.can_farm(c["code"])]
    return J(resources.cross_farm_dispatch(farms_))


class StrategyReq(BaseModel):
    title: str
    content: dict
    farms: list[str] = ["*"]


@app.get("/api/v1/strategies", tags=["resources"])
def strategies(p: security.Principal = Depends(current)):
    return J(db.q("SELECT * FROM strategies ORDER BY created_at DESC LIMIT 30"))


@app.post("/api/v1/strategies/{sid}/publish", tags=["resources"])
def publish_strategy(sid: int, p: security.Principal = Depends(need("strategy:publish"))):
    s = db.q1("SELECT * FROM strategies WHERE id=%s", (sid,))
    if not s:
        raise HTTPException(404, "策略不存在")
    db.update("strategies", "id", sid, {"status": "published", "published_by": p.username, "published_at": dt.datetime.now(UTC)})
    security.audit(None, None, p.username, "strategy_publish", {"id": sid, "title": s["title"]})
    for f in db.q("SELECT id FROM wind_farms"):
        rules_svc.notify(f["id"], "info", f"统一运维策略已发布：{s['title']}", "", "strategy", str(sid))
    return J({"ok": True})


# ================================================================= 报表 / KPI / 能效 / 模型
@app.get("/api/v1/reports/{period}", tags=["reports"])
def report(period: str, farm: str, key: Optional[str] = Query(None, alias="month"), force: bool = False, p: security.Principal = Depends(current)):
    """GET /api/v1/reports/monthly?farm=EH-01&month=2026-10；quarterly 时 month 传 2026-Q4；yearly 传 2026。"""
    farm_guard(p, farm)
    f = db.q1("SELECT id FROM wind_farms WHERE code=%s", (farm,))
    if not f:
        raise HTTPException(404, "风场不存在")
    if period not in ("monthly", "quarterly", "yearly"):
        raise HTTPException(400, "period 必须为 monthly/quarterly/yearly")
    return J(reports.generate(f["id"], period, key, force))


@app.get("/api/v1/kpi/compliance", tags=["reports"])
def compliance(farm: Optional[str] = None, p: security.Principal = Depends(current)):
    fid = None
    if farm:
        farm_guard(p, farm)
        fid = db.scalar("SELECT id FROM wind_farms WHERE code=%s", (farm,))
    return J(reports.spec_compliance(fid))


@app.get("/api/v1/efficiency", tags=["reports"])
def eff(farm: str, p: security.Principal = Depends(current)):
    farm_guard(p, farm)
    fid = db.scalar("SELECT id FROM wind_farms WHERE code=%s", (farm,))
    return J(efficiency.evaluate_farm(fid, 180))


@app.get("/api/v1/models", tags=["models"])
def models(p: security.Principal = Depends(current)):
    return J({"models": modelreg.list_models(), "eval_runs": db.q("SELECT * FROM eval_runs ORDER BY id DESC LIMIT 10"),
              "jobs": scheduler.last})


@app.post("/api/v1/models/iterate", tags=["models"])
async def iterate(force: bool = True, p: security.Principal = Depends(need("approve:L3"))):
    return J(await asyncio.to_thread(improve.run_iteration, force))


# ================================================================= 仿真 / 边缘（演示与联调）
class InjectReq(BaseModel):
    asset: str
    scenario: str
    ramp_minutes: float = Field(15.0, ge=1, le=240)
    backfill_minutes: float = Field(0, ge=0, le=60, description=">0 时将故障发展回填到过去 N 分钟，便于立即触发告警")


@app.get("/api/v1/sim/scenarios", tags=["sim"])
def sim_scenarios(p: security.Principal = Depends(current)):
    return J({"scenarios": faults.scenarios(), "active": faults.active()})


@app.post("/api/v1/sim/inject", tags=["sim"])
def sim_inject(req: InjectReq, p: security.Principal = Depends(need("approve:L3"))):
    a = db.q1("SELECT f.code FROM assets a JOIN wind_farms f ON f.id=a.farm_id WHERE a.code=%s", (req.asset.upper(),))
    if not a:
        raise HTTPException(404, "设备不存在")
    farm_guard(p, a["code"])
    r = faults.inject(req.asset.upper(), req.scenario, req.ramp_minutes)
    if req.backfill_minutes > 0:
        db.x("UPDATE sim_faults SET started_at = now() - make_interval(secs => %s) WHERE id=%s", (req.backfill_minutes * 60, r["id"]))
        _backfill_fault(req.asset.upper(), int(req.backfill_minutes) + 5)
    security.audit(None, None, p.username, "sim_inject", r)
    return J(r)


def _backfill_fault(asset: str, minutes: int) -> None:
    import random
    from ..edge import simulator as sim
    rows = db.q("SELECT code,type,farm_id,props FROM assets WHERE code=%s", (asset,))
    fl = db.q("SELECT asset_code,scenario,started_at,ramp_minutes FROM sim_faults WHERE active AND asset_code=%s", (asset,))
    now = dt.datetime.now(UTC).replace(microsecond=0)
    start = now - dt.timedelta(minutes=minutes)
    # 先清除该设备回填区间内已存在的“正常”数据，否则新旧数据混杂，窗口均值被拉低，告警迟迟不触发
    db.x("DELETE FROM ts_realtime WHERE asset_code=%s AND ts >= %s", (asset, start))
    t, rng, out = start, random.Random(), []
    while t <= now:
        out += sim.generate_snapshot(t, rows, fl, rng)
        t += dt.timedelta(seconds=30)
    ts.write_points(out)


@app.post("/api/v1/sim/clear", tags=["sim"])
def sim_clear(asset: Optional[str] = None, p: security.Principal = Depends(need("approve:L3"))):
    return J({"cleared": faults.clear(asset.upper() if asset else None)})


@app.get("/api/v1/edge/status", tags=["sim"])
def edge_status(p: security.Principal = Depends(current)):
    s = scheduler.sim
    return J({"edge": s.edge.status() if s else None, "storage": ts.storage_stats(), "jobs": scheduler.last})


class LinkReq(BaseModel):
    up: bool


@app.post("/api/v1/edge/link", tags=["sim"])
def edge_link(req: LinkReq, p: security.Principal = Depends(need("approve:L3"))):
    if not scheduler.sim:
        raise HTTPException(409, "仿真器未启用")
    scheduler.sim.edge.set_link(req.up)
    security.audit(None, None, p.username, "edge_link", {"up": req.up})
    return J(scheduler.sim.edge.status())


@app.post("/api/v1/edge/ingest", tags=["sim"])
def edge_ingest(body: dict, p: security.Principal = Depends(need("approve:L3"))):
    return J(ts.ingest_batch(body["node"], body["batch_id"], body["rows"], body["checksum"], body.get("priority", 0)))


# ================================================================= 静态前端
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(WEB_DIR / "index.html"), headers={"Cache-Control": "no-cache"})
