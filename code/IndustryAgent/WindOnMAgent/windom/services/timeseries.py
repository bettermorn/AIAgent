"""时序数据服务：实时库(热)/历史库(冷)双存储、边缘批次入库(幂等+校验)、降采样归档、窗口统计。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Iterable, Optional

from .. import db
from ..config import settings
from ..edge.node import batch_checksum


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def ingest_batch(node: str, batch_id: str, rows: list[list], checksum: str, priority: int = 0) -> dict:
    """边缘节点上传入口：校验和不符拒收，batch_id 幂等(重传不重复入库)。"""
    if batch_checksum(rows) != checksum:
        return {"ok": False, "error": "checksum_mismatch"}
    with db.tx():
        if db.q1("SELECT 1 FROM edge_ingest_log WHERE node=%s AND batch_id=%s", (node, batch_id)):
            return {"ok": True, "duplicate": True}
        n = write_points([(a, s, dt.datetime.fromisoformat(ts), v, q) for a, s, ts, v, q in rows])
        db.insert("edge_ingest_log", {"node": node, "batch_id": batch_id, "rows": n, "checksum": checksum, "priority": priority})
    return {"ok": True, "rows": n}


def write_points(rows: Iterable[tuple]) -> int:
    rows = list(rows)
    return db.bulk("""INSERT INTO ts_realtime(asset_code,sensor_type,ts,value,quality) VALUES %s
                      ON CONFLICT (asset_code,sensor_type,ts) DO UPDATE SET value=EXCLUDED.value, quality=EXCLUDED.quality""", rows)


def archive_to_history(older_than_hours: Optional[float] = None, delete_realtime: bool = True) -> dict:
    """实时库(热数据)→历史库(1 分钟聚合, 冷数据长期归档); 实时库仅保留 realtime_retention_hours。"""
    hours = older_than_hours if older_than_hours is not None else min(settings.realtime_retention_hours, 24.0)
    cutoff = now() - dt.timedelta(hours=hours)
    with db.tx():
        n = db.x("""INSERT INTO ts_history(asset_code,sensor_type,ts,value,vmin,vmax,n)
                    SELECT asset_code, sensor_type, date_trunc('minute', ts), avg(value), min(value), max(value), count(*)
                    FROM ts_realtime WHERE ts < %s GROUP BY 1,2,3
                    ON CONFLICT (asset_code,sensor_type,ts) DO UPDATE SET
                      value=EXCLUDED.value, vmin=EXCLUDED.vmin, vmax=EXCLUDED.vmax, n=EXCLUDED.n""", (cutoff,))
        deleted = 0
        if delete_realtime:
            deleted = db.x("DELETE FROM ts_realtime WHERE ts < %s", (cutoff,))
    return {"archived_buckets": n, "deleted_realtime": deleted, "cutoff": cutoff}


def latest(asset_code: str, sensors: Optional[list[str]] = None) -> dict[str, dict]:
    rows = db.q("""SELECT DISTINCT ON (sensor_type) sensor_type, ts, value FROM ts_realtime
                   WHERE asset_code=%s AND (%s::text[] IS NULL OR sensor_type = ANY(%s)) ORDER BY sensor_type, ts DESC""",
                (asset_code, sensors, sensors))
    return {r["sensor_type"]: {"ts": r["ts"], "value": r["value"]} for r in rows}


def window_stats(asset_code: str, sensors: list[str], minutes: float = 120, end: Optional[dt.datetime] = None) -> dict[str, dict]:
    """窗口统计: 首/末/均值/最大/最小/斜率(每小时)。跨实时库与历史库。"""
    end = end or now()
    start = end - dt.timedelta(minutes=minutes)
    out: dict[str, dict] = {}
    for s in sensors:
        pts = series(asset_code, s, minutes, end=end, max_points=600)
        if not pts:
            continue
        vals = [p["value"] for p in pts]
        t0 = pts[0]["ts"]
        xs = [(p["ts"] - t0).total_seconds() / 3600 for p in pts]
        slope = 0.0
        if len(pts) >= 3 and xs[-1] > 0:
            mx, my = sum(xs) / len(xs), sum(vals) / len(vals)
            den = sum((x - mx) ** 2 for x in xs)
            slope = sum((x - mx) * (y - my) for x, y in zip(xs, vals)) / den if den else 0.0
        out[s] = {"first": vals[0], "last": vals[-1], "mean": sum(vals) / len(vals), "max": max(vals), "min": min(vals),
                  "slope_per_h": slope, "n": len(vals), "start": start, "end": end}
    return out


def series(asset_code: str, sensor: str, minutes: float = 120, end: Optional[dt.datetime] = None,
           max_points: int = 400) -> list[dict]:
    """取序列：先实时库，不足部分回落历史库；超过 max_points 时按时间桶均值降采样返回。"""
    end = end or now()
    start = end - dt.timedelta(minutes=minutes)
    bucket = max(1, int(minutes * 60 / max_points))
    rows = db.q("""SELECT to_timestamp(floor(extract(epoch FROM ts) / %s) * %s) AS ts, avg(value) AS value
                   FROM ts_realtime WHERE asset_code=%s AND sensor_type=%s AND ts >= %s AND ts <= %s
                   GROUP BY 1 ORDER BY 1""", (bucket, bucket, asset_code, sensor, start, end))
    first_rt = rows[0]["ts"] if rows else end
    if first_rt - start > dt.timedelta(seconds=max(bucket * 2, 120)):
        hist = db.q("""SELECT to_timestamp(floor(extract(epoch FROM ts) / %s) * %s) AS ts, avg(value) AS value
                       FROM ts_history WHERE asset_code=%s AND sensor_type=%s AND ts >= %s AND ts < %s
                       GROUP BY 1 ORDER BY 1""", (bucket, bucket, asset_code, sensor, start, first_rt))
        rows = hist + rows
    return [{"ts": r["ts"], "value": float(r["value"])} for r in rows]


def peer_baseline(asset_code: str, sensors: list[str], farm_id: int, minutes: float = 30) -> dict[str, dict]:
    """同风场同型机组基线(中位数/MAD)，用于去除负荷/风速共因影响的偏离判断。"""
    since = now() - dt.timedelta(minutes=minutes)
    rows = db.q("""SELECT r.sensor_type,
                          percentile_cont(0.5) WITHIN GROUP (ORDER BY r.value) med,
                          percentile_cont(0.75) WITHIN GROUP (ORDER BY r.value) q3,
                          percentile_cont(0.25) WITHIN GROUP (ORDER BY r.value) q1,
                          count(DISTINCT r.asset_code) n_assets
                   FROM ts_realtime r JOIN assets a ON a.code=r.asset_code
                   WHERE a.type='turbine' AND a.farm_id=%s AND r.asset_code<>%s AND r.sensor_type = ANY(%s) AND r.ts >= %s
                   GROUP BY r.sensor_type""", (farm_id, asset_code, sensors, since))
    return {r["sensor_type"]: {"median": r["med"], "iqr": max(r["q3"] - r["q1"], 1e-6), "n_assets": r["n_assets"]} for r in rows}


def storage_stats() -> dict:
    return {
        "realtime_rows": db.scalar("SELECT count(*) FROM ts_realtime"),
        "history_rows": db.scalar("SELECT count(*) FROM ts_history"),
        "realtime_oldest": db.scalar("SELECT min(ts) FROM ts_realtime"),
        "realtime_newest": db.scalar("SELECT max(ts) FROM ts_realtime"),
        "history_oldest": db.scalar("SELECT min(ts) FROM ts_history"),
        "edge_batches": db.scalar("SELECT count(*) FROM edge_ingest_log"),
        "retention_hours": settings.realtime_retention_hours,
    }


def standardization_rate(days: float = 30) -> dict:
    """数据标准化率(规范 4c ≥95%): 术语归一化成功比例。"""
    since = now() - dt.timedelta(days=days)
    rows = db.q("SELECT method, count(*) n FROM term_stats WHERE ts >= %s GROUP BY method", (since,))
    total = sum(r["n"] for r in rows)
    bad = sum(r["n"] for r in rows if r["method"] == "unmatched")
    return {"total": total, "unmatched": bad, "rate": (total - bad) / total if total else None,
            "by_method": {r["method"]: r["n"] for r in rows}}
