"""SCADA/传感器仿真器：为 100 台风机 + 升压站 + 海缆 + 测风塔生成物理自洽的运行数据，并支持故障注入。

真实部署中，这部分由边缘采集网关从 PLC/传感器(OPC UA/Modbus)采集；本仿真器使系统可在无现场数据时端到端运行。
故障场景对应 ontology.FAULTS 各原因的 scenario 键，故障按 ramp_minutes 线性发展。
"""
from __future__ import annotations

import datetime as dt
import math
import random
from typing import Optional

RATED_KW = 6000.0
CUT_IN, RATED_WS, CUT_OUT = 3.0, 12.0, 25.0


def power_curve(ws: float) -> float:
    if ws < CUT_IN or ws >= CUT_OUT:
        return 0.0
    if ws >= RATED_WS:
        return RATED_KW
    return RATED_KW * ((ws - CUT_IN) / (RATED_WS - CUT_IN)) ** 3


def _epoch(t: dt.datetime) -> float:
    return t.timestamp()


def farm_wind(t: dt.datetime, seed: int = 0) -> float:
    """场站风速(确定性函数, 便于重放与历史回填)。"""
    s = _epoch(t)
    w = (8.6 + 2.6 * math.sin(2 * math.pi * s / (7 * 3600) + seed)
         + 1.3 * math.sin(2 * math.pi * s / (47 * 60) + 1.7 * seed)
         + 0.7 * math.sin(2 * math.pi * s / (9 * 60)))
    return max(1.0, w)


# 故障场景: sensor -> (加性增量@满发展, 乘性系数@满发展)
SCENARIOS: dict[str, dict[str, tuple[float, float]]] = {
    "gearbox_cooler_clog": {"gearbox_oil_temp": (42, 1), "cooling_airflow": (-38, 1)},
    "gearbox_low_oil": {"gearbox_oil_temp": (44, 1), "gearbox_oil_pressure": (-1.4, 1)},
    "gearbox_bearing_wear": {"gearbox_oil_temp": (44, 1), "gearbox_vibration": (6.0, 1)},
    "gearbox_oil_degraded": {"gearbox_oil_temp": (46, 1)},
    "gearbox_gear_wear": {"gearbox_vibration": (7.0, 1), "gearbox_oil_temp": (9, 1)},
    "gearbox_misalign": {"gearbox_vibration": (6.5, 1), "tower_vibration": (2.6, 1)},
    "gearbox_vib_sensor": {"gearbox_vibration": (7.0, 1)},
    "gen_fan_fault": {"generator_winding_temp": (72, 1), "cooling_airflow": (-34, 1)},
    "gen_overload": {"generator_winding_temp": (78, 1), "generator_bearing_temp": (18, 1)},
    "gen_insulation": {"generator_winding_temp": (80, 1)},
    "gen_lube": {"generator_bearing_temp": (50, 1)},
    "gen_bearing_damage": {"generator_bearing_temp": (50, 1), "gearbox_vibration": (3.5, 1)},
    "cvt_pump": {"converter_igbt_temp": (50, 1)},
    "cvt_dust": {"converter_igbt_temp": (48, 1), "cooling_airflow": (-30, 1)},
    "cvt_igbt": {"converter_igbt_temp": (46, 1), "generator_winding_temp": (7, 1)},
    "hyd_leak": {"hydraulic_pressure": (-55, 1), "hydraulic_oil_level": (-34, 1)},
    "hyd_pump": {"hydraulic_pressure": (-52, 1)},
    "hyd_accum": {"hydraulic_pressure": (-48, 1)},
    "ms_lube": {"main_bearing_temp": (40, 1)},
    "ms_wear": {"main_bearing_temp": (42, 1), "gearbox_vibration": (3.2, 1)},
    "tw_bolt": {"tower_vibration": (7.0, 1)},
    "tw_blade": {"tower_vibration": (7.6, 1), "gearbox_vibration": (3.0, 1)},
    "tw_scour": {"tower_vibration": (7.6, 1), "rotor_speed": (-2.5, 1)},
    "cable_overload": {"cable_conductor_temp": (55, 1)},
    "cable_damage": {"cable_conductor_temp": (52, 1)},
    "tr_fan": {"transformer_oil_temp": (52, 1)},
    "tr_oil": {"transformer_oil_temp": (50, 1)},
}

# 传感器合理物理范围, 超出视为坏点(边缘预处理过滤)
RANGE = {
    "gearbox_oil_temp": (-20, 160), "gearbox_vibration": (0, 40), "gearbox_oil_pressure": (0, 12),
    "cooling_airflow": (0, 150), "generator_winding_temp": (-20, 220), "generator_bearing_temp": (-20, 160),
    "converter_igbt_temp": (-20, 180), "hydraulic_pressure": (0, 300), "hydraulic_oil_level": (0, 100),
    "main_bearing_temp": (-20, 140), "tower_vibration": (0, 40), "wind_speed": (0, 80), "rotor_speed": (0, 30),
    "active_power": (-200, 8000), "transformer_oil_temp": (-20, 160), "cable_conductor_temp": (-20, 160),
    "mast_wind_speed": (0, 80),
}


def healthy_turbine(ws_farm: float, meta: dict, rng: random.Random) -> dict[str, float]:
    ws = max(0.0, ws_farm * float(meta.get("wbias", 1.0)) + rng.gauss(0, 0.25))
    eff = float(meta.get("eff", 1.0))
    p = power_curve(ws) * eff * (1 + rng.gauss(0, 0.008))
    f = max(0.0, min(1.0, p / RATED_KW))
    g = rng.gauss
    return {
        "wind_speed": ws,
        "active_power": p,
        "rotor_speed": 6 + 10 * f + g(0, 0.08),
        "gearbox_oil_temp": 46 + 24 * f + g(0, 0.5),
        "gearbox_vibration": 1.8 + 1.2 * f + g(0, 0.08),
        "gearbox_oil_pressure": 3.2 + g(0, 0.04),
        "cooling_airflow": 100 + g(0, 1.2),
        "generator_winding_temp": 60 + 45 * f + g(0, 0.7),
        "generator_bearing_temp": 46 + 26 * f + g(0, 0.5),
        "converter_igbt_temp": 42 + 26 * f + g(0, 0.5),
        "hydraulic_pressure": 180 + g(0, 1.2),
        "hydraulic_oil_level": 92 + g(0, 0.25),
        "main_bearing_temp": 34 + 22 * f + g(0, 0.4),
        "tower_vibration": 2.2 + 1.6 * f + g(0, 0.08),
    }


def healthy_substation(load: float, rng: random.Random) -> dict[str, float]:
    return {"transformer_oil_temp": 45 + 25 * load + rng.gauss(0, 0.5)}


def healthy_cable(load: float, rng: random.Random) -> dict[str, float]:
    return {"cable_conductor_temp": 40 + 25 * load + rng.gauss(0, 0.5)}


def healthy_mast(ws_farm: float, rng: random.Random) -> dict[str, float]:
    return {"mast_wind_speed": max(0.0, ws_farm + rng.gauss(0, 0.2))}


def fault_fraction(started_at: dt.datetime, ramp_minutes: float, t: dt.datetime) -> float:
    if t <= started_at:
        return 0.0
    return min(1.0, (t - started_at).total_seconds() / 60.0 / max(ramp_minutes, 0.1))


def apply_fault(vals: dict[str, float], scenario: str, frac: float) -> dict[str, float]:
    spec = SCENARIOS.get(scenario)
    if not spec or frac <= 0:
        return vals
    out = dict(vals)
    for sensor, (add, mul) in spec.items():
        if sensor in out:
            out[sensor] = out[sensor] * (1 + (mul - 1) * frac) + add * frac
    return out


def generate_snapshot(t: dt.datetime, assets: list[dict], faults: list[dict], rng: Optional[random.Random] = None,
                      farm_seed: dict[int, int] | None = None) -> list[tuple]:
    """assets: [{code,type,farm_id,props}]; faults: [{asset_code,scenario,started_at,ramp_minutes}]
    返回 [(asset_code, sensor_type, ts, value, quality)]"""
    rng = rng or random.Random()
    farm_seed = farm_seed or {}
    by_asset: dict[str, list[dict]] = {}
    for f in faults:
        by_asset.setdefault(f["asset_code"], []).append(f)
    ws_cache: dict[int, float] = {}
    load_cache: dict[int, float] = {}
    rows: list[tuple] = []
    for a in assets:
        fid = a["farm_id"]
        if fid not in ws_cache:
            ws_cache[fid] = farm_wind(t, farm_seed.get(fid, fid))
            load_cache[fid] = min(1.0, power_curve(ws_cache[fid]) / RATED_KW)
        ws, load = ws_cache[fid], load_cache[fid]
        if a["type"] == "turbine":
            vals = healthy_turbine(ws, a.get("props") or {}, rng)
        elif a["type"] == "substation":
            vals = healthy_substation(load, rng)
        elif a["type"] == "cable":
            vals = healthy_cable(load, rng)
        elif a["type"] == "mast":
            vals = healthy_mast(ws, rng)
        else:
            continue
        for f in by_asset.get(a["code"], []):
            vals = apply_fault(vals, f["scenario"], fault_fraction(f["started_at"], f["ramp_minutes"], t))
        for s, v in vals.items():
            rows.append((a["code"], s, t, round(v, 3), 0))
    return rows
