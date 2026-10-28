"""资源服务（资源 Agent / 安全 Agent 的后端）：备件、人员资质、船舶、海况窗口、出海合并、跨场调度、AIS。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db
from ..db import J
from ..ontology import SAFETY_LIMITS

UTC = dt.timezone.utc
SITE_TZ = dt.timezone(dt.timedelta(hours=8))


def now() -> dt.datetime:
    return dt.datetime.now(UTC)


# ---------------------------------------------------------------- 备件
def spare_query(codes: list[str], farm_id: int) -> list[dict]:
    rows = db.q("""SELECT code,name,stock,reserved,location,lead_days FROM spare_parts WHERE farm_id=%s AND code = ANY(%s)""", (farm_id, codes))
    out = []
    got = {r["code"] for r in rows}
    for r in rows:
        avail = r["stock"] - r["reserved"]
        out.append({**r, "available": avail, "ok": avail >= 1, "eta_days": 0 if avail >= 1 else r["lead_days"]})
    for c in codes:
        if c not in got:
            out.append({"code": c, "name": c, "stock": 0, "reserved": 0, "available": 0, "ok": False, "location": "-", "lead_days": 30, "eta_days": 30})
    return out


def other_farm_stock(codes: list[str], farm_id: int) -> list[dict]:
    """跨场调拨(规范 6.4.3): 本场缺件时查找其他风场库存。"""
    return db.q("""SELECT s.code, s.name, s.stock - s.reserved available, f.code farm_code, s.location
                   FROM spare_parts s JOIN wind_farms f ON f.id=s.farm_id
                   WHERE s.farm_id<>%s AND s.code = ANY(%s) AND s.stock - s.reserved >= 1""", (farm_id, codes))


def reserve_parts(codes: list[str], farm_id: int) -> list[str]:
    done = []
    for c in codes:
        if db.x("UPDATE spare_parts SET reserved=reserved+1 WHERE farm_id=%s AND code=%s AND stock-reserved>=1", (farm_id, c)):
            done.append(c)
    return done


def release_parts(codes: list[str], farm_id: int, consume: bool = False) -> None:
    for c in codes:
        if consume:
            db.x("UPDATE spare_parts SET reserved=GREATEST(reserved-1,0), stock=GREATEST(stock-1,0) WHERE farm_id=%s AND code=%s", (farm_id, c))
        else:
            db.x("UPDATE spare_parts SET reserved=GREATEST(reserved-1,0) WHERE farm_id=%s AND code=%s", (farm_id, c))


# ---------------------------------------------------------------- 人员
def personnel_for(farm_id: int, needs: list[str], count: int = 2, busy_codes: Optional[list[str]] = None) -> dict:
    """按资质(含证书有效期)匹配人员; 返回可用名单与不合格原因。"""
    today = dt.date.today()
    rows = db.q("SELECT * FROM personnel WHERE farm_id=%s ORDER BY code", (farm_id,))
    busy = set(busy_codes or [])
    ok, rejected = [], []
    req = set(needs)
    for p in rows:
        reasons = []
        if p["status"] != "available":
            reasons.append("当前不可用")
        if p["code"] in busy:
            reasons.append("已被其他任务占用")
        if p["cert_expire"] and p["cert_expire"] < today:
            reasons.append(f"证书已于 {p['cert_expire']} 过期")
        missing = req - set(p["quals"])
        if missing:
            reasons.append("缺少资质：" + "、".join(sorted(missing)))
        (rejected if reasons else ok).append({**p, "reasons": reasons})
    # 综合资质: 一人不够时拼班组(需 hv 的至少一名高压电工)
    crew = ok[:count]
    return {"crew": [{"code": p["code"], "name": p["name"], "role": p["role"], "quals": p["quals"]} for p in crew],
            "enough": len(crew) >= count, "available": len(ok), "rejected": [{"code": r["code"], "name": r["name"], "reasons": r["reasons"]} for r in rejected if r["reasons"]]}


def team_for(farm_id: int, needs: list[str], count: int = 2) -> dict:
    """班组构成: 每项资质至少 1 人具备且证书有效; 所有人都需 offshore。"""
    today = dt.date.today()
    rows = [p for p in db.q("SELECT * FROM personnel WHERE farm_id=%s AND status='available' ORDER BY code", (farm_id,))
            if not p["cert_expire"] or p["cert_expire"] >= today]
    must = set(needs) | {"offshore"}
    crew: list[dict] = []
    for q in sorted(must - {"offshore"}):
        if any(q in c["quals"] for c in crew):
            continue
        cand = next((p for p in rows if q in p["quals"] and "offshore" in p["quals"] and p not in crew), None)
        if cand:
            crew.append(cand)
    for p in rows:
        if len(crew) >= count:
            break
        if p not in crew and "offshore" in p["quals"]:
            crew.append(p)
    covered = {q for c in crew for q in c["quals"]}
    missing = sorted(must - covered)
    expired = [p["name"] for p in db.q("SELECT name FROM personnel WHERE farm_id=%s AND cert_expire < %s", (farm_id, today))]
    return {"crew": [{"code": c["code"], "name": c["name"], "role": c["role"], "quals": c["quals"]} for c in crew[:max(count, len(crew))]],
            "enough": not missing and len(crew) >= min(count, 1), "missing_quals": missing, "expired_cert_people": expired}


# ---------------------------------------------------------------- 海况窗口
def windows(farm_id: int, need_hours: float, max_wave: float, max_wind: float, min_vis: float, within_hours: int = 96,
            start_from: Optional[dt.datetime] = None) -> list[dict]:
    """在预报中找连续满足阈值的窗口(白天 06:00-18:00 作业)，长度 ≥ need_hours。"""
    start = (start_from or now()).replace(minute=0, second=0, microsecond=0)
    rows = db.q("""SELECT ts, wind_speed, wave_height, visibility_km FROM weather_forecast
                   WHERE farm_id=%s AND ts >= %s AND ts < %s ORDER BY ts""", (farm_id, start, start + dt.timedelta(hours=within_hours)))
    out, cur = [], []
    for r in rows:
        hr = r["ts"].astimezone(SITE_TZ).hour  # 现场时区(UTC+8)白天作业
        ok = (r["wave_height"] <= max_wave and r["wind_speed"] <= max_wind and r["visibility_km"] >= min_vis and 6 <= hr < 18)
        if ok:
            cur.append(r)
        else:
            if cur:
                out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    res = []
    for seg in out:
        hours = len(seg)
        if hours >= need_hours:
            res.append({"start": seg[0]["ts"], "end": seg[-1]["ts"] + dt.timedelta(hours=1), "hours": hours,
                        "max_wave": max(s["wave_height"] for s in seg), "max_wind": max(s["wind_speed"] for s in seg),
                        "min_visibility": min(s["visibility_km"] for s in seg)})
    return res


def current_sea(farm_id: int) -> dict:
    r = db.q1("""SELECT ts, wind_speed, wave_height, visibility_km FROM weather_forecast WHERE farm_id=%s AND ts <= now()
                 ORDER BY ts DESC LIMIT 1""", (farm_id,))
    return r or {}


def ais_nearby(farm_id: int) -> list[dict]:
    return db.q("SELECT mmsi,name,ship_type,lat,lon,sog,ts FROM ais_vessels WHERE farm_id=%s ORDER BY name", (farm_id,))


# ---------------------------------------------------------------- 船舶
def pick_vessel(farm_id: int, wave: float, wind: float, crew_size: int) -> Optional[dict]:
    rows = db.q("""SELECT * FROM vessels WHERE farm_id=%s AND status='available' AND max_wave >= %s AND max_wind >= %s AND capacity >= %s
                   ORDER BY capacity""", (farm_id, wave, wind, crew_size))
    return rows[0] if rows else None


def vessel_busy(farm_id: int, start: dt.datetime, end: dt.datetime) -> set[str]:
    rows = db.q("""SELECT vessel_code FROM trip_plans WHERE farm_id=%s AND status IN ('suggested','confirmed')
                   AND window_start < %s AND window_end > %s""", (farm_id, end, start))
    return {r["vessel_code"] for r in rows}


def plan_resources(farm_id: int, actions: list[dict], urgency: str = "normal", turbine: Optional[str] = None,
                   hv_needed: bool = False) -> dict:
    """综合资源方案: 备件 + 人员 + 船舶 + 海况窗口; 与同风场已计划出海合并(提升人员调度效率, 规范 4e)。"""
    parts = sorted({p["code"] for a in actions for p in a.get("parts", [])})
    needs: set[str] = set()
    hours = 0.0
    for a in actions:
        needs.update(a.get("needs") or [])
        hours += float(a.get("hours") or 2)
    qual_needs = {"climb" if n == "climb" else "hv_electric" if n == "hv" else "offshore" for n in needs}
    lim = {"max_wave": 9.0, "max_wind": 99.0, "min_vis": 0.0}
    for n in needs:
        l = SAFETY_LIMITS.get(n)
        if l:
            lim["max_wave"] = min(lim["max_wave"], l["max_wave"])
            lim["max_wind"] = min(lim["max_wind"], l["max_wind"])
            lim["min_vis"] = max(lim["min_vis"], l["min_visibility_km"])
    need_offshore = bool(needs)
    spares = spare_query(parts, farm_id) if parts else []
    missing_parts = [s for s in spares if not s["ok"]]
    alt = other_farm_stock([s["code"] for s in missing_parts], farm_id) if missing_parts else []
    team = team_for(farm_id, sorted(qual_needs), count=2) if need_offshore else {"crew": [], "enough": True, "missing_quals": [], "expired_cert_people": []}
    ws = windows(farm_id, max(hours, 2), lim["max_wave"], lim["max_wind"], lim["min_vis"]) if need_offshore else []
    chosen = ws[0] if ws else None
    vessel = None
    if chosen:
        busy = vessel_busy(farm_id, chosen["start"], chosen["end"])
        for v in db.q("SELECT * FROM vessels WHERE farm_id=%s AND status='available' ORDER BY capacity", (farm_id,)):
            if v["code"] not in busy and v["max_wave"] >= chosen["max_wave"] and v["max_wind"] >= chosen["max_wind"] and v["capacity"] >= max(len(team["crew"]), 2):
                vessel = v
                break
    merge = None
    if chosen:
        merge = db.q1("""SELECT id, vessel_code, window_start, window_end, turbines FROM trip_plans
                         WHERE farm_id=%s AND status IN ('suggested','confirmed') AND window_start <= %s AND window_end >= %s
                         ORDER BY window_start LIMIT 1""", (farm_id, chosen["end"], chosen["start"]))
    parts_eta = max([s["eta_days"] for s in spares], default=0)
    # 备件缺货且需等待 → 窗口顺延
    earliest = now() + dt.timedelta(days=parts_eta)
    if chosen and parts_eta > 0:
        later = [w for w in windows(farm_id, max(hours, 2), lim["max_wave"], lim["max_wind"], lim["min_vis"], within_hours=24 * 14 if False else 96, start_from=earliest)]
        chosen = later[0] if later else chosen
    return {"parts": spares, "other_farm_parts": alt, "team": team, "limits": lim, "windows": ws[:3], "chosen_window": chosen,
            "vessel": {"code": vessel["code"], "name": vessel["name"], "type": vessel["vtype"]} if vessel else None,
            "merge_with_trip": merge, "est_hours": hours, "need_offshore": need_offshore, "parts_eta_days": parts_eta,
            "feasible": (not need_offshore) or bool(chosen and vessel and team["enough"]),
            "blockers": ([f"备件 {s['code']} 本场缺货(到货约 {s['eta_days']} 天)" for s in missing_parts]
                         + ([] if (not need_offshore or chosen) else ["未来 96 小时无满足安全限值的出海窗口"])
                         + ([] if (not need_offshore or vessel or not chosen) else ["无可用船舶"])
                         + ([f"班组缺少资质：{'、'.join(team['missing_quals'])}"] if team["missing_quals"] else []))}


def create_trip(farm_id: int, plan: dict, turbine: str, wo_id: int, status: str = "suggested") -> Optional[dict]:
    w = plan.get("chosen_window")
    if not w or not plan.get("vessel"):
        return None
    merge = plan.get("merge_with_trip")
    if merge:
        db.x("""UPDATE trip_plans SET turbines = (SELECT array(SELECT DISTINCT unnest(turbines || %s))), wo_ids = wo_ids || %s WHERE id=%s""",
             ([turbine], [wo_id], merge["id"]))
        return {"merged": True, "trip_id": merge["id"]}
    r = db.insert("trip_plans", {"farm_id": farm_id, "vessel_code": plan["vessel"]["code"], "window_start": w["start"], "window_end": w["end"],
                                 "turbines": [turbine], "wo_ids": [wo_id], "crew": [c["code"] for c in plan["team"]["crew"]], "status": status})
    return {"merged": False, "trip_id": r["id"]}


def cross_farm_dispatch(farm_codes: list[str]) -> dict:
    """跨场调度(规范 6.4.3)：统筹多风场未处理任务与人员/船舶/备件，给出协同配置建议。"""
    out = []
    for fc in farm_codes:
        f = db.q1("SELECT id, code, name FROM wind_farms WHERE code=%s", (fc,))
        if not f:
            continue
        open_wo = db.q("""SELECT wo_no, asset_code, wo_type, status, title FROM work_orders
                          WHERE farm_id=%s AND status IN ('pending_approval','approved','dispatched','in_progress','draft') ORDER BY wo_type, created_at""", (f["id"],))
        crew = db.scalar("SELECT count(*) FROM personnel WHERE farm_id=%s AND status='available' AND (cert_expire IS NULL OR cert_expire>=current_date)", (f["id"],))
        ves = db.scalar("SELECT count(*) FROM vessels WHERE farm_id=%s AND status='available'", (f["id"],))
        out.append({"farm": f["code"], "name": f["name"], "open_workorders": open_wo, "crew_available": crew, "vessels_available": ves,
                    "load_per_crew": round(len(open_wo) / max(crew, 1), 2)})
    suggestions = []
    if len(out) >= 2:
        hi = max(out, key=lambda o: o["load_per_crew"])
        lo = min(out, key=lambda o: o["load_per_crew"])
        if hi["farm"] != lo["farm"] and hi["load_per_crew"] > lo["load_per_crew"] * 1.5 and lo["crew_available"] > 2:
            suggestions.append(f"{lo['farm']} 负荷较低(人均 {lo['load_per_crew']}), 建议向 {hi['farm']}(人均 {hi['load_per_crew']}) 支援 1-2 名持证人员与共享备件")
    return {"farms": out, "suggestions": suggestions}


# ---------------------------------------------------------------- 安全合规
def safety_check(farm_id: int, needs: list[str], window: Optional[dict], team: dict, risky_actions: list[str],
                 permit_status: Optional[dict] = None) -> dict:
    """安全 Agent 的合规检查: 海况/资质/作业票/L3 动作。返回 verdict ∈ pass | conditional | veto。"""
    reasons, conditions, vetoes = [], [], []
    req_permits = sorted({SAFETY_LIMITS[n]["permit"] for n in needs if n in SAFETY_LIMITS})
    for n in needs:
        lim = SAFETY_LIMITS.get(n)
        if not lim:
            continue
        reasons.append(f"{n}作业限值：浪高≤{lim['max_wave']}m、风速≤{lim['max_wind']}m/s、能见度≥{lim['min_visibility_km']}km")
    if needs and not window:
        vetoes.append("未来可预报时段内无满足海况限值的作业窗口")
    elif window:
        conditions.append(f"仅在窗口 {window['start'].astimezone(SITE_TZ):%m-%d %H:%M} ~ {window['end'].astimezone(SITE_TZ):%m-%d %H:%M} 内作业，浪高<{window['max_wave']:.1f}m")
    if team and team.get("missing_quals"):
        vetoes.append("班组缺少资质：" + "、".join(team["missing_quals"]))
    if team and team.get("expired_cert_people"):
        conditions.append("已排除证书过期人员：" + "、".join(team["expired_cert_people"]))
    for p in req_permits:
        conditions.append(f"须办理{ {'climb': '登塔', 'offshore': '出海', 'hv': '高压'}.get(p, p)}作业票并做安全交底")
    if risky_actions:
        vetoes.append("包含高风险操作（" + "、".join(risky_actions) + "），Agent 无权执行，须走正式审批流程（作业票+双人确认）")
    verdict = "veto" if vetoes else "conditional" if conditions else "pass"
    # 高风险动作被“禁止 Agent 执行”不等于否决整个工单: 剥离后可继续，因此区分硬否决
    hard = [v for v in vetoes if not v.startswith("包含高风险操作")]
    if not hard and vetoes:
        verdict = "conditional"
        conditions.extend(vetoes)
        vetoes = []
    return {"verdict": verdict, "vetoes": vetoes, "conditions": conditions, "limits": reasons, "required_permits": req_permits,
            "l3_actions": risky_actions}
