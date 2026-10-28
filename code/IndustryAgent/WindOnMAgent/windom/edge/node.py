"""边缘节点（规范 5.3 / 6.3）：升压站边缘预处理 + ≥72h 本地缓存 + 断链续传。

- 预处理：坏点过滤(超物理范围/NaN)、信号校准(线性)、采样压缩(死区去重)、异常识别(标记 quality)
- 本地缓存：SQLite 持久化，保留 ≥72 小时(可配置)，断链时继续写入
- 上传：批次带 SHA256 校验和与 batch_id(幂等)，失败自动重试，恢复后按优先级(异常数据优先)补传
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Iterable, Optional

from .simulator import RANGE

log = logging.getLogger("windom.edge")
CACHE_HOURS = 72


def batch_checksum(rows: list[list]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=False, separators=(",", ":")).encode()).hexdigest()


class EdgeNode:
    def __init__(self, name: str, uploader: Callable[[str, str, list[list], str, int], dict],
                 cache_path: str | Path = "data/edge_cache.sqlite", cache_hours: int = CACHE_HOURS,
                 deadband: float = 0.0, calibration: Optional[dict[str, tuple[float, float]]] = None):
        self.name = name
        self.uploader = uploader
        self.cache_hours = cache_hours
        self.deadband = deadband
        self.calibration = calibration or {}
        self.link_up = True
        self._last: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(cache_path), check_same_thread=False)
        self._db.execute("""CREATE TABLE IF NOT EXISTS buf (
            id INTEGER PRIMARY KEY AUTOINCREMENT, node TEXT, ts REAL, asset TEXT, sensor TEXT, value REAL,
            quality INTEGER, priority INTEGER DEFAULT 0, sent INTEGER DEFAULT 0)""")
        self._db.execute("CREATE INDEX IF NOT EXISTS buf_sent ON buf(node, sent, priority DESC, ts)")
        self._db.commit()

    # ------------------------------------------------------------------ 预处理
    def preprocess(self, rows: Iterable[tuple]) -> list[tuple]:
        out = []
        for asset, sensor, ts, value, quality in rows:
            if value is None or value != value:
                continue  # NaN 坏点
            lo, hi = RANGE.get(sensor, (-1e9, 1e9))
            if value < lo or value > hi:
                continue  # 超物理范围
            k, b = self.calibration.get(sensor, (1.0, 0.0))
            value = value * k + b  # 信号校准
            if self.deadband > 0:
                last = self._last.get((asset, sensor))
                if last is not None and abs(value - last) < self.deadband:
                    continue  # 死区压缩
                self._last[(asset, sensor)] = value
            out.append((asset, sensor, ts, value, quality))
        return out

    def _priority(self, sensor: str, value: float, thresholds: dict[str, float]) -> int:
        th = thresholds.get(sensor)
        return 1 if th is not None and value >= th else 0  # 异常识别: 接近/超阈值数据优先上传

    def collect(self, rows: Iterable[tuple], hot_thresholds: Optional[dict[str, float]] = None) -> int:
        rows = self.preprocess(rows)
        hot = hot_thresholds or {}
        with self._lock:
            self._db.executemany(
                "INSERT INTO buf(node,ts,asset,sensor,value,quality,priority) VALUES (?,?,?,?,?,?,?)",
                [(self.name, ts.timestamp(), a, s, float(v), int(q), self._priority(s, v, hot)) for a, s, ts, v, q in rows])
            self._db.commit()
            self._purge()
        return len(rows)

    def _purge(self) -> None:
        cutoff = time.time() - self.cache_hours * 3600
        self._db.execute("DELETE FROM buf WHERE ts < ? ", (cutoff,))
        self._db.commit()

    # ------------------------------------------------------------------ 上传
    def pending(self) -> int:
        return self._db.execute("SELECT count(*) FROM buf WHERE node=? AND sent=0", (self.name,)).fetchone()[0]

    def flush(self, batch_size: int = 5000, max_batches: int = 50, retries: int = 3) -> dict:
        """按优先级(高→低)、时间(早→晚)补传；链路断开则直接保留本地缓存。"""
        if not self.link_up:
            return {"uploaded": 0, "pending": self.pending(), "link": "down"}
        uploaded, batches = 0, 0
        while batches < max_batches:
            with self._lock:
                cur = self._db.execute(
                    "SELECT id,ts,asset,sensor,value,quality,priority FROM buf WHERE node=? AND sent=0 "
                    "ORDER BY priority DESC, ts LIMIT ?", (self.name, batch_size))
                got = cur.fetchall()
            if not got:
                break
            payload = [[a, s, dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(), v, q] for _, ts, a, s, v, q, _ in got]
            checksum = batch_checksum(payload)
            batch_id = uuid.uuid4().hex
            prio = max(r[6] for r in got)
            ok = False
            for attempt in range(retries):
                try:
                    resp = self.uploader(self.name, batch_id, payload, checksum, prio)
                    ok = bool(resp.get("ok"))
                    if ok:
                        break
                except Exception as e:
                    log.warning("边缘上传失败(第%d次): %s", attempt + 1, e)
                time.sleep(0.2 * (attempt + 1))
            if not ok:
                return {"uploaded": uploaded, "pending": self.pending(), "link": "error"}
            ids = [r[0] for r in got]
            with self._lock:
                self._db.executemany("UPDATE buf SET sent=1 WHERE id=?", [(i,) for i in ids])
                self._db.commit()
            uploaded += len(got)
            batches += 1
        with self._lock:
            self._db.execute("DELETE FROM buf WHERE sent=1 AND ts < ?", (time.time() - 3600,))
            self._db.commit()
        return {"uploaded": uploaded, "pending": self.pending(), "link": "up"}

    def set_link(self, up: bool) -> None:
        self.link_up = up

    def status(self) -> dict:
        row = self._db.execute("SELECT min(ts), max(ts), count(*) FROM buf WHERE node=?", (self.name,)).fetchone()
        return {"node": self.name, "link_up": self.link_up, "pending": self.pending(),
                "cached_rows": row[2], "oldest": row[0], "newest": row[1],
                "cache_hours": self.cache_hours,
                "cache_span_hours": round((row[1] - row[0]) / 3600, 2) if row[0] and row[1] else 0}
