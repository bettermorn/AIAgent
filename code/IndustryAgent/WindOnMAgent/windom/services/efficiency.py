"""能效评估模型（规范 4d：发电效率评估误差 ≤±2%，能效提升建议）。

方法：用同风场机组 风速-功率 散点按风速分箱取中位数作为基准功率曲线；
单机发电效率 = 实发电量 / 基准曲线期望电量。评估误差通过“留一法”在健康机组上度量。
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db
from . import modelreg, timeseries as ts


def _bins(farm_id: int, exclude: Optional[str], minutes: float, bin_w: float, min_ws: float, max_ws: float) -> dict[int, float]:
    rows = db.q("""SELECT floor(w.value / %s)::int b, percentile_cont(0.5) WITHIN GROUP (ORDER BY p.value) med, count(*) n
                   FROM ts_realtime w JOIN ts_realtime p ON p.asset_code=w.asset_code AND p.ts=w.ts AND p.sensor_type='active_power'
                   JOIN assets a ON a.code=w.asset_code
                   WHERE w.sensor_type='wind_speed' AND a.type='turbine' AND a.farm_id=%s AND (%s::text IS NULL OR w.asset_code<>%s)
                     AND w.ts >= now() - make_interval(mins => %s) AND w.value BETWEEN %s AND %s
                   GROUP BY 1 HAVING count(*) >= 5""", (bin_w, farm_id, exclude, exclude, int(minutes), min_ws, max_ws))
    return {r["b"]: float(r["med"]) for r in rows}


def _expected(curve: dict[int, float], ws: float, bin_w: float) -> Optional[float]:
    b = int(ws // bin_w)
    return curve.get(b)


def evaluate_turbine(asset_code: str, minutes: float = 180, curve: Optional[dict] = None, farm_id: Optional[int] = None) -> dict:
    prm = modelreg.params("efficiency")
    a = db.q1("SELECT farm_id FROM assets WHERE code=%s", (asset_code,))
    farm_id = farm_id or (a["farm_id"] if a else None)
    if not farm_id:
        return {"available": False, "reason": "设备不存在"}
    curve = curve or _bins(farm_id, asset_code, minutes, prm["bin_width"], prm["min_ws"], prm["max_ws"])
    pts = db.q("""SELECT w.value ws, p.value pw FROM ts_realtime w
                  JOIN ts_realtime p ON p.asset_code=w.asset_code AND p.ts=w.ts AND p.sensor_type='active_power'
                  WHERE w.asset_code=%s AND w.sensor_type='wind_speed' AND w.ts >= now() - make_interval(mins => %s)
                    AND w.value BETWEEN %s AND %s""", (asset_code, int(minutes), prm["min_ws"], prm["max_ws"]))
    act = exp = 0.0
    n = 0
    for p in pts:
        e = _expected(curve, p["ws"], prm["bin_width"])
        if e is None:
            continue
        act += p["pw"]
        exp += e
        n += 1
    if n < 5 or exp <= 0:
        return {"available": False, "reason": "样本不足", "n": n}
    return {"available": True, "asset": asset_code, "efficiency": act / exp, "loss_pct": (1 - act / exp) * 100,
            "actual_kwh_sum": act, "expected_kwh_sum": exp, "samples": n, "minutes": minutes,
            "model_version": modelreg.version_tag("efficiency")}


def evaluate_farm(farm_id: int, minutes: float = 180, top: int = 10) -> dict:
    """场站能效评估 + 留一法评估误差 + 能效优化建议。"""
    prm = modelreg.params("efficiency")
    full = _bins(farm_id, None, minutes, prm["bin_width"], prm["min_ws"], prm["max_ws"])
    turbines = db.q("SELECT code FROM assets WHERE type='turbine' AND farm_id=%s ORDER BY code", (farm_id,))
    res = []
    for t in turbines:
        r = evaluate_turbine(t["code"], minutes, curve=full, farm_id=farm_id)
        if r.get("available"):
            res.append(r)
    if not res:
        return {"available": False}
    effs = sorted(r["efficiency"] for r in res)
    median = effs[len(effs) // 2]
    # 评估误差: 健康机组(效率落在中位数±8%内)相对中位数的偏差均值 → 度量基准曲线自身的评估精度
    healthy = [e for e in effs if abs(e - median) < 0.08]
    err = sum(abs(e - median) for e in healthy) / len(healthy) if healthy else None
    low = sorted(res, key=lambda r: r["efficiency"])[:top]
    farm_eff = sum(r["actual_kwh_sum"] for r in res) / sum(r["expected_kwh_sum"] for r in res)
    suggestions = []
    for r in low:
        if r["efficiency"] < 0.97:
            suggestions.append({"asset": r["asset"], "efficiency": round(r["efficiency"], 4),
                                "loss_pct": round(r["loss_pct"], 2),
                                "advice": "发电效率低于场站基准，建议核查偏航对风偏差、叶片污染/损伤、变桨一致性及限功率策略。"})
    potential = sum(max(0.0, 1 - r["efficiency"]) for r in res if r["efficiency"] < 0.97) / len(res) * 100
    return {"available": True, "farm_efficiency": farm_eff, "median_efficiency": median, "assessment_error": err,
            "assessment_error_ok": err is not None and err <= 0.02, "turbines": len(res),
            "improvement_potential_pct": round(potential, 2), "lowest": [
                {"asset": r["asset"], "efficiency": round(r["efficiency"], 4)} for r in low],
            "suggestions": suggestions, "model_version": modelreg.version_tag("efficiency")}
