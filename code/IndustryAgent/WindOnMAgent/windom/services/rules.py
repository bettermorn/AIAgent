"""规则引擎（文档 5.5 规则引擎）：阈值与规程约束判断、多级预警（规范 6.5.1）、告警生命周期管理。

规则存于 PostgreSQL rules 表（由图谱/规程导入），按窗口均值判断以抑制抖动，带迟滞防止告警震荡。
预警级别：1 关注 / 2 告警 / 3 严重。
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db
from ..config import settings
from ..db import J
from ..ontology import COMP_NAME, FAULTS, SENSOR_NAME, SENSOR_UNIT, WARNING_LEVELS


def level_of(value: float, rule: dict) -> int:
    l1, l2, l3 = rule["l1"], rule["l2"], rule["l3"]
    if rule["direction"] == "high":
        return 3 if value >= l3 else 2 if value >= l2 else 1 if value >= l1 else 0
    return 3 if value <= l3 else 2 if value <= l2 else 1 if value <= l1 else 0


def active_rules() -> list[dict]:
    return db.q("SELECT * FROM rules WHERE status='active' ORDER BY code")


def rule_eval(values: dict[str, float]) -> list[dict]:
    """对一组传感器读数做规则判断(供 rule_eval 工具/诊断交叉验证使用)。"""
    out = []
    for r in active_rules():
        v = values.get(r["sensor_type"])
        if v is None:
            continue
        lv = level_of(v, r)
        out.append({"rule": r["code"], "sensor": r["sensor_type"], "sensor_name": SENSOR_NAME.get(r["sensor_type"]),
                    "value": v, "level": lv, "level_name": WARNING_LEVELS[lv][0] if lv else "正常",
                    "thresholds": {"l1": r["l1"], "l2": r["l2"], "l3": r["l3"], "direction": r["direction"]},
                    "fault_key": r["fault_key"], "doc": {"doc_no": r["doc_no"], "section": r["doc_section"]}})
    return out


def scan(farm_id: Optional[int] = None) -> list[dict]:
    """对所有资产做一次规则扫描: 窗口内均值 → 预警级别。返回当前越限项。"""
    hits: list[dict] = []
    for r in active_rules():
        rows = db.q("""SELECT t.asset_code, a.farm_id, a.parent_code, avg(t.value) v, count(*) n
                       FROM ts_realtime t JOIN assets a ON a.code=t.asset_code
                       WHERE t.sensor_type=%s AND t.ts >= now() - make_interval(secs => %s)
                         AND a.type = %s AND (%s::int IS NULL OR a.farm_id=%s)
                       GROUP BY t.asset_code, a.farm_id, a.parent_code HAVING count(*) >= 3""",
                    (r["sensor_type"], r["window_s"], r["asset_kind"], farm_id, farm_id))
        for x in rows:
            lv = level_of(x["v"], r)
            if lv > 0:
                th = r["l3"] if lv == 3 else r["l2"] if lv == 2 else r["l1"]
                hits.append({"asset": x["asset_code"], "farm_id": x["farm_id"], "rule": r, "level": lv, "value": float(x["v"]),
                             "threshold": th})
    return hits


def _clear_candidates(hit_keys: set[tuple[str, str]]) -> list[dict]:
    open_alarms = db.q("SELECT * FROM alarms WHERE status IN ('open','acknowledged') AND source='monitor'")
    return [a for a in open_alarms if (a["asset_code"], a["fault_key"]) not in hit_keys]


def monitor_cycle(farm_id: Optional[int] = None) -> dict:
    """监测周期: 扫描 → 新建/升级告警 → 清除已恢复告警。返回 {'new': [...], 'escalated': [...], 'cleared': n}"""
    hits = scan(farm_id)
    new, escalated = [], []
    keys: set[tuple[str, str]] = set()
    for h in hits:
        r = h["rule"]
        key = (h["asset"], r["fault_key"])
        keys.add(key)
        comp_code = _component_for(h["asset"], r["comp_type"])
        ex = db.q1("SELECT * FROM alarms WHERE asset_code=%s AND fault_key=%s AND status IN ('open','acknowledged')",
                   (h["asset"], r["fault_key"]))
        title = f"{h['asset']} {FAULTS[r['fault_key']]['name']}"
        if not ex:
            row = db.insert("alarms", {
                "farm_id": h["farm_id"], "asset_code": h["asset"], "comp_code": comp_code, "sensor_type": r["sensor_type"],
                "rule_code": r["code"], "fault_key": r["fault_key"], "title": title, "level": h["level"],
                "value": h["value"], "threshold": h["threshold"], "source": "monitor",
                "detail": J({"sensor_name": SENSOR_NAME.get(r["sensor_type"]), "unit": SENSOR_UNIT.get(r["sensor_type"]),
                             "window_s": r["window_s"], "doc": [r["doc_no"], r["doc_section"]]})})
            new.append(row)
            notify(h["farm_id"], "warn" if h["level"] < 3 else "critical", f"新告警：{title}（{WARNING_LEVELS[h['level']][0]}）",
                   f"当前{SENSOR_NAME.get(r['sensor_type'])}={h['value']:.1f}{SENSOR_UNIT.get(r['sensor_type'], '')}，"
                   f"阈值 {h['threshold']}", "alarm", str(row["id"]))
        elif h["level"] > ex["level"]:
            db.update("alarms", "id", ex["id"], {"level": h["level"], "value": h["value"], "threshold": h["threshold"]})
            ex.update(level=h["level"], value=h["value"])
            escalated.append(ex)
            notify(h["farm_id"], "critical", f"告警升级：{title} → {WARNING_LEVELS[h['level']][0]}",
                   f"当前值 {h['value']:.1f}", "alarm", str(ex["id"]))
        else:
            db.update("alarms", "id", ex["id"], {"value": h["value"]})
    cleared = 0
    for a in _clear_candidates(keys):
        # 迟滞: 取消须连续无命中，且超过创建 3 分钟，避免刚创建即被清除
        if (dt.datetime.now(dt.timezone.utc) - a["raised_at"]).total_seconds() > 180:
            db.update("alarms", "id", a["id"], {"status": "closed", "closed_at": dt.datetime.now(dt.timezone.utc)})
            cleared += 1
    return {"new": new, "escalated": escalated, "cleared": cleared, "hits": len(hits)}


def _component_for(asset_code: str, comp_type: Optional[str]) -> Optional[str]:
    if not comp_type:
        return None
    r = db.q1("SELECT code FROM assets WHERE type='component' AND comp_type=%s AND props->>'host'=%s LIMIT 1",
              (comp_type, asset_code))
    return r["code"] if r else asset_code


def notify(farm_id: Optional[int], level: str, title: str, body: str = "", ref_type: str | None = None,
           ref_id: str | None = None, target_role: str | None = None) -> None:
    """报警推送(规范 5.5c): 写入通知表, 前端通过 WebSocket/轮询获取。"""
    db.insert("notifications", {"farm_id": farm_id, "level": level, "title": title, "body": body,
                                "ref_type": ref_type, "ref_id": ref_id, "target_role": target_role}, returning="id")
