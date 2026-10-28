"""时序诊断模型（文档 5.5：异常检测、趋势预测、健康评分、剩余寿命评估）。

方法：
1. 同风场同型机组基线(中位数/IQR)偏离 → 去除风速/负荷共因影响，得到每个传感器的偏离方向；
2. IsolationForest 多变量异常分(以同场健康机组近期数据训练)；
3. 原因排序：知识图谱中的原因先验 × 传感器偏离特征签名的似然 → 后验(朴素贝叶斯)，参数由模型注册表管理，
   可被改进 Agent 依据维修反馈校准(规范 6.4.2)；
4. 趋势外推到三级阈值得到剩余时间(RUL 近似)，及部件健康评分。
"""
from __future__ import annotations

import datetime as dt
import math
import threading
import time
from typing import Optional

import numpy as np
from sklearn.ensemble import IsolationForest

from .. import db
from ..ontology import FAULTS, SENSOR_NAME, SENSOR_UNIT, TURBINE_SENSORS
from . import kg, modelreg, rules as rules_svc, timeseries as ts

_if_cache: dict[int, tuple[float, IsolationForest, list[str]]] = {}
_if_lock = threading.Lock()
IF_FEATURES = [s for s in TURBINE_SENSORS if s not in ("wind_speed", "active_power")]


def _scale(med: float, iqr: float, sensor: str) -> float:
    """鲁棒尺度: IQR/1.349，并设下限防止零方差。"""
    floor = max(abs(med) * 0.012, 0.05)
    return max(iqr / 1.349, floor)


def deviations(asset_code: str, farm_id: int, sensors: list[str], recent_min: float = 10, z_thr: float = 3.0) -> dict[str, dict]:
    cur = ts.window_stats(asset_code, sensors, minutes=recent_min)
    base = ts.peer_baseline(asset_code, sensors, farm_id, minutes=30)
    out = {}
    for s in sensors:
        c, b = cur.get(s), base.get(s)
        if not c or not b or b["n_assets"] < 3:
            continue
        z = (c["mean"] - b["median"]) / _scale(b["median"], b["iqr"], s)
        direction = 1 if z > z_thr else -1 if z < -z_thr else 0
        out[s] = {"sensor": s, "name": SENSOR_NAME.get(s, s), "unit": SENSOR_UNIT.get(s, ""), "value": c["mean"],
                  "baseline": b["median"], "z": float(z), "dir": direction, "peers": b["n_assets"]}
    return out


def _fit_forest(farm_id: int) -> Optional[tuple[IsolationForest, list[str]]]:
    with _if_lock:
        hit = _if_cache.get(farm_id)
        if hit and time.time() - hit[0] < 300:
            return hit[1], hit[2]
    rows = db.q("""SELECT r.asset_code, date_trunc('minute', r.ts) m, r.sensor_type, avg(r.value) v
                   FROM ts_realtime r JOIN assets a ON a.code=r.asset_code
                   WHERE a.type='turbine' AND a.farm_id=%s AND r.sensor_type = ANY(%s) AND r.ts >= now() - interval '40 minutes'
                     AND NOT EXISTS (SELECT 1 FROM alarms al WHERE al.asset_code=r.asset_code AND al.status IN ('open','acknowledged'))
                   GROUP BY 1,2,3""", (farm_id, IF_FEATURES))
    pivot: dict[tuple, dict] = {}
    for r in rows:
        pivot.setdefault((r["asset_code"], r["m"]), {})[r["sensor_type"]] = r["v"]
    X = [[d[f] for f in IF_FEATURES] for d in pivot.values() if len(d) == len(IF_FEATURES)]
    if len(X) < 40:
        return None
    X = np.asarray(X, dtype=float)
    model = IsolationForest(n_estimators=100, contamination="auto", random_state=7).fit(X)
    with _if_lock:
        _if_cache[farm_id] = (time.time(), model, IF_FEATURES)
    return model, IF_FEATURES


def anomaly_score(asset_code: str, farm_id: int) -> Optional[float]:
    """多变量异常分: 0~1, 越大越异常(IsolationForest)。"""
    fm = _fit_forest(farm_id)
    if not fm:
        return None
    model, feats = fm
    cur = ts.window_stats(asset_code, feats, minutes=8)
    if len(cur) < len(feats):
        return None
    x = np.asarray([[cur[f]["mean"] for f in feats]])
    raw = -float(model.score_samples(x)[0])  # 约 0.35~0.8
    return float(max(0.0, min(1.0, (raw - 0.4) / 0.3)))


def rank_causes(fault_key: str, devs: dict[str, dict], knowledge: Optional[dict] = None, p: Optional[dict] = None) -> list[dict]:
    """朴素贝叶斯原因排序。签名中缺失观测的传感器按中性处理(不贡献似然)。"""
    p = p or modelreg.params("cause_ranker")
    knowledge = knowledge or kg.fault_knowledge(fault_key)
    if not knowledge or not knowledge["causes"]:
        return []
    match_p = float(p["match_p"])
    mism_p = (1 - match_p) / 2.0
    pw = float(p.get("prior_weight", 1.0))
    scored = []
    for c in knowledge["causes"]:
        lp = pw * math.log(max(c["prior"], 1e-6))
        used, matched = 0, []
        for sensor, expect in (c["signature"] or {}).items():
            d = devs.get(sensor)
            if not d:
                continue
            used += 1
            ok = d["dir"] == int(expect)
            lp += math.log(match_p if ok else mism_p)
            matched.append({"sensor": sensor, "name": d["name"], "expected": int(expect), "observed": d["dir"],
                            "z": round(d["z"], 2), "match": ok})
        scored.append((lp, c, matched, used))
    m = max(s[0] for s in scored)
    z = sum(math.exp(s[0] - m) for s in scored)
    out = []
    for lp, c, matched, used in scored:
        post = math.exp(lp - m) / z
        out.append({"key": c["key"], "short_key": c["short_key"], "name": c["name"], "probability": round(post, 4),
                    "prior": c["prior"], "features": matched, "evidence_features": used, "checks": c["checks"],
                    "actions": c["actions"], "source": c["source"]})
    out.sort(key=lambda x: x["probability"], reverse=True)
    return out


def trend(asset_code: str, sensor: str, minutes: float = 120, rule: Optional[dict] = None) -> dict:
    st = ts.window_stats(asset_code, [sensor], minutes=minutes).get(sensor)
    if not st or st["n"] < 3:
        return {"available": False}
    res = {"available": True, "first": st["first"], "last": st["last"], "slope_per_h": st["slope_per_h"], "minutes": minutes,
           "unit": SENSOR_UNIT.get(sensor, ""), "name": SENSOR_NAME.get(sensor, sensor)}
    if rule:
        sl = st["slope_per_h"]
        toward = sl > 0.05 if rule["direction"] == "high" else sl < -0.05
        if toward:
            cur = st["last"]
            hours = (rule["l3"] - cur) / sl if abs(sl) > 1e-9 else None
            res["hours_to_l3"] = round(max(hours, 0.0), 2) if hours is not None else None
        else:
            res["hours_to_l3"] = None
    return res


def health_score(asset_code: str, farm_id: Optional[int] = None) -> dict:
    """部件健康评分(0-100): 基于各规则监测量相对 额定值→三级阈值 的偏离程度; 总分=加权(最差部件, 平均)。"""
    prm = modelreg.params("health")
    comps = {}
    rls = [r for r in rules_svc.active_rules()]
    cat = {r["sensor_type"]: r for r in db.q("SELECT * FROM sensor_catalog")}
    asset = db.q1("SELECT type FROM assets WHERE code=%s", (asset_code,))
    kind = asset["type"] if asset else "turbine"
    for r in rls:
        if r["asset_kind"] != kind:
            continue
        st = ts.window_stats(asset_code, [r["sensor_type"]], minutes=10).get(r["sensor_type"])
        if not st:
            continue
        nominal = cat.get(r["sensor_type"], {}).get("nominal")
        if nominal is None:
            continue
        v = st["mean"]
        span = (r["l3"] - nominal) or 1.0
        frac = (v - nominal) / span
        # 健康基线按健康运行区间: 额定值到 l1 的一半视为满分
        free = ((r["l1"] - nominal) / span) * 0.5
        loss = max(0.0, min(1.0, (frac - free) / max(1 - free, 1e-6)))
        score = round(100 * (1 - loss), 1)
        comp = r["comp_type"] or "other"
        comps[comp] = min(comps.get(comp, 100.0), score)
    if not comps:
        return {"overall": None, "components": {}}
    vals = list(comps.values())
    overall = prm["w_min"] * min(vals) + prm["w_mean"] * (sum(vals) / len(vals))
    return {"overall": round(overall, 1), "components": comps}


def diagnose(asset_code: str, fault_key: str, minutes: float = 120) -> dict:
    """综合诊断: 偏离特征 + 异常分 + 原因后验 + 趋势/剩余时间 + 健康评分。"""
    asset = db.q1("SELECT code, farm_id, type FROM assets WHERE code=%s", (asset_code,))
    if not asset:
        raise ValueError(f"设备不存在: {asset_code}")
    spec = FAULTS.get(fault_key)
    if not spec:
        raise ValueError(f"未知故障类型: {fault_key}")
    knowledge = kg.fault_knowledge(fault_key)
    sensors = {spec["sensor"]}
    for c in (knowledge or {}).get("causes", []):
        sensors.update((c["signature"] or {}).keys())
    sensors = sorted(sensors)
    prm = modelreg.params("cause_ranker")
    is_turbine = asset["type"] == "turbine"
    devs = deviations(asset_code, asset["farm_id"], sensors, z_thr=float(prm["z_thr"])) if is_turbine else {}
    # 非风机资产(升压站/海缆)无同型对比, 仅用自身趋势
    rule = db.q1("SELECT * FROM rules WHERE fault_key=%s AND status='active' LIMIT 1", (fault_key,))
    cur = ts.window_stats(asset_code, [spec["sensor"]], minutes=10).get(spec["sensor"])
    causes = rank_causes(fault_key, devs, knowledge, prm) if knowledge else []
    ascore = anomaly_score(asset_code, asset["farm_id"]) if is_turbine else None
    tr = trend(asset_code, spec["sensor"], minutes, rule)
    lv = rules_svc.level_of(cur["mean"], rule) if (cur and rule) else 0
    top = causes[0]["probability"] if causes else 0.0
    obs = sum(1 for c in causes[:1] for _ in c["features"]) if causes else 0
    # 证据充足度: 有观测到的签名传感器越多, 置信度越高
    evid_ratio = min(1.0, (causes[0]["evidence_features"] / max(len(causes[0]["features"]) or 1, 1))) if causes else 0.0
    conf = round(0.15 + 0.7 * top * (0.55 + 0.45 * evid_ratio) + (0.1 if lv else 0.0) + (0.05 if (ascore or 0) > 0.5 else 0.0), 3)
    conf = max(0.0, min(0.97, conf))
    return {"asset": asset_code, "fault_key": fault_key, "fault_name": spec["name"], "primary_sensor": spec["sensor"],
            "current": cur, "warning_level": lv, "causes": causes, "deviations": devs, "anomaly_score": ascore,
            "trend": tr, "health": health_score(asset_code, asset["farm_id"]), "confidence": conf,
            "model_version": modelreg.version_tag("cause_ranker"), "observed_signatures": obs,
            "rule": {"code": rule["code"], "l1": rule["l1"], "l2": rule["l2"], "l3": rule["l3"],
                     "direction": rule["direction"], "doc": [rule["doc_no"], rule["doc_section"]]} if rule else None}


def classify_from_features(fault_key: str, devs_dirs: dict[str, int], knowledge: dict, p: dict) -> list[dict]:
    """离线评估用: 直接由偏离方向特征排序原因(黄金集回归/参数校准)。"""
    devs = {s: {"dir": d, "name": s, "z": float(d) * 5} for s, d in devs_dirs.items()}
    return rank_causes(fault_key, devs, knowledge, p)
