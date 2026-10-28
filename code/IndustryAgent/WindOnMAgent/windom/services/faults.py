"""故障注入与仿真循环（演示/联调用）：向 sim_faults 写入场景，仿真循环经边缘节点→入库管线持续生成数据。"""
from __future__ import annotations

import datetime as dt
import logging
import random
import threading
import time
from typing import Optional

from .. import db
from ..edge import simulator as sim
from ..edge.node import EdgeNode
from ..ontology import CAUSE_SCENARIO
from . import timeseries as ts

log = logging.getLogger("windom.sim")
UTC = dt.timezone.utc


def inject(asset_code: str, scenario: str, ramp_minutes: float = 15.0) -> dict:
    if scenario not in sim.SCENARIOS:
        raise ValueError(f"未知场景 {scenario}，可选：{sorted(sim.SCENARIOS)}")
    a = db.q1("SELECT code FROM assets WHERE code=%s", (asset_code,))
    if not a:
        raise ValueError(f"设备不存在: {asset_code}")
    db.x("UPDATE sim_faults SET active=FALSE WHERE asset_code=%s AND active", (asset_code,))
    r = db.insert("sim_faults", {"asset_code": asset_code, "scenario": scenario, "ramp_minutes": ramp_minutes})
    return {"id": r["id"], "asset": asset_code, "scenario": scenario, "ramp_minutes": ramp_minutes}


def clear(asset_code: Optional[str] = None) -> int:
    if asset_code:
        return db.x("UPDATE sim_faults SET active=FALSE WHERE asset_code=%s AND active", (asset_code,))
    return db.x("UPDATE sim_faults SET active=FALSE WHERE active")


def active() -> list[dict]:
    return db.q("SELECT * FROM sim_faults WHERE active ORDER BY id DESC")


def scenarios() -> list[dict]:
    from ..ontology import FAULTS
    by_sc = {c["scenario"]: (fk, f["name"], c["name"]) for fk, f in FAULTS.items() for c in f["causes"]}
    return [{"scenario": k, "fault_key": v[0], "fault_name": v[1], "cause": v[2]} for k, v in by_sc.items()]


class Simulator:
    """后台线程：每 interval 秒生成一个采样点；写入经由边缘节点预处理/缓存/校验上传，可模拟断链。"""

    def __init__(self, interval_s: float = 30.0, step_s: float = 10.0):
        self.interval_s = interval_s
        self.step_s = step_s
        self._stop = threading.Event()
        self._t: Optional[threading.Thread] = None
        self.edge = EdgeNode("oss-edge-01", self._upload, cache_path="data/edge_cache.sqlite")
        self.rng = random.Random()
        self.last_tick: Optional[dt.datetime] = None
        self.hot = {"gearbox_oil_temp": 75, "generator_winding_temp": 115, "converter_igbt_temp": 75}

    @staticmethod
    def _upload(node: str, batch_id: str, rows: list, checksum: str, priority: int) -> dict:
        return ts.ingest_batch(node, batch_id, rows, checksum, priority)

    def start(self) -> None:
        if self._t and self._t.is_alive():
            return
        self._stop.clear()
        self._t = threading.Thread(target=self._loop, name="simulator", daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._stop.set()

    def tick(self, now: Optional[dt.datetime] = None) -> dict:
        now = now or dt.datetime.now(UTC).replace(microsecond=0)
        assets = db.q("SELECT code,type,farm_id,props FROM assets WHERE type IN ('turbine','substation','cable','mast')")
        faults = db.q("SELECT asset_code,scenario,started_at,ramp_minutes FROM sim_faults WHERE active")
        # 每个周期补齐 [last_tick, now] 内每 step_s 秒的采样(≥1Hz 在生产由采集网关保证, 仿真器按 step_s 近似)
        start = self.last_tick + dt.timedelta(seconds=self.step_s) if self.last_tick else now
        t, n = start, 0
        while t <= now:
            n += self.edge.collect(sim.generate_snapshot(t, assets, faults, self.rng), self.hot)
            t += dt.timedelta(seconds=self.step_s)
        self.last_tick = now
        res = self.edge.flush()
        return {"collected": n, **res}

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("仿真周期失败")
            self._stop.wait(self.interval_s)


_sim: Optional[Simulator] = None


def get_simulator(interval_s: float = 30.0) -> Simulator:
    global _sim
    if _sim is None:
        _sim = Simulator(interval_s)
    return _sim
