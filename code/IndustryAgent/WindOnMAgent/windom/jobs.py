"""后台作业（文档 5.4 Temporal 长流程的单机等价实现）：仿真/监控/自动诊断/归档/周期工单/报表/月度模型迭代/知识沉淀。

多进程部署时通过 PostgreSQL advisory lock 保证作业单例。生产环境可将各 job 映射为 Temporal Workflow/Cron。
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from typing import Callable, Optional

from . import db, security
from .config import settings
from .db import J

log = logging.getLogger("windom.jobs")
UTC = dt.timezone.utc


class Scheduler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.sim = None
        self.last: dict[str, dict] = {}
        self._after = threading.local()

    # ---- 单个 job 的统一包装: 单例锁 + 异常隔离 + 运行记录 ----
    def _run(self, name: str, fn: Callable[[], Optional[dict]], lock_key: int, record: bool = True) -> None:
        try:
            after: list = []
            self._after.after = after
            with db.tx():
                if not db.advisory_lock(lock_key):
                    return
                t0 = time.time()
                detail = fn() or {}
            for cb in after:          # 事务提交后再启动异步任务，避免子线程读不到未提交行
                cb()
            self.last[name] = {"ts": dt.datetime.now(UTC).isoformat(), "ok": True, "ms": int((time.time() - t0) * 1000), **detail}
            if record and detail.get("_record"):
                detail.pop("_record", None)
                db.insert("job_runs", {"job": name, "ok": True, "detail": J(detail)}, returning="id")
        except Exception as e:
            log.exception("job %s 失败", name)
            self.last[name] = {"ts": dt.datetime.now(UTC).isoformat(), "ok": False, "error": str(e)}
            try:
                db.insert("job_runs", {"job": name, "ok": False, "detail": J({"error": str(e)})}, returning="id")
            except Exception:
                pass

    def _every(self, name: str, interval: float, fn: Callable[[], Optional[dict]], lock_key: int, initial_delay: float = 3.0) -> None:
        def loop():
            self._stop.wait(initial_delay)
            while not self._stop.is_set():
                self._run(name, fn, lock_key)
                self._stop.wait(interval)
        th = threading.Thread(target=loop, name=f"job-{name}", daemon=True)
        th.start()
        self._threads.append(th)

    # ---- 具体作业 ----
    def job_monitor(self) -> dict:
        from .services import rules
        r = rules.monitor_cycle()
        if settings.auto_diagnose:
            for al in r["new"] + r["escalated"]:
                if al["level"] >= settings.emergency_level:
                    self.auto_diagnose(al)
        return {"new": len(r["new"]), "escalated": len(r["escalated"]), "cleared": r["cleared"]}

    def auto_diagnose(self, alarm: dict) -> None:
        """预警 ≥ 二级自动触发总控 Agent 诊断并生成紧急工单（规范 8.2.2a），响应计时从告警时刻起。"""
        from .agents import orchestrator as orch
        fresh = db.q1("SELECT * FROM alarms WHERE id=%s", (alarm["id"],))
        if fresh["wo_id"] or fresh["task_id"]:
            return
        p = security.SYSTEM
        farm = db.scalar("SELECT code FROM wind_farms WHERE id=%s", (fresh["farm_id"],))
        t = orch.create_task("alarm", f"告警自动诊断：{fresh['title']}", p, payload={"alarm_id": fresh["id"], "asset": fresh["asset_code"],
                                                                                     "fault_key": fresh["fault_key"], "intent": "diagnose"}, farm_code=farm)
        db.x("UPDATE alarms SET task_id=%s WHERE id=%s", (t["id"], fresh["id"]))
        self._after.after.append(lambda tid=t["id"]: orch.run_task_async(tid, p))

    def job_archive(self) -> dict:
        from .services import timeseries as ts
        r = ts.archive_to_history(older_than_hours=6)
        r["_record"] = True
        return r

    def job_weather(self) -> dict:
        from . import seed
        return {"rows": seed.refresh_weather()}

    def job_periodic(self) -> dict:
        """按 GB/T 32128 周期生成例行工单草稿（到期前 7 天）。"""
        from .services import workorders as wos
        due = db.q("""SELECT p.*, f.code farm_code FROM periodic_plans p JOIN wind_farms f ON f.id=p.farm_id
                      WHERE p.next_due <= current_date + 7 AND NOT EXISTS (
                        SELECT 1 FROM work_orders w WHERE w.asset_code=p.asset_code AND w.source='periodic' AND w.title LIKE p.title || '%%'
                          AND w.created_at > now() - interval '60 days') LIMIT 20""")
        n = 0
        for p in due:
            a = db.q1("SELECT farm_id FROM assets WHERE code=%s", (p["asset_code"],))
            wos.create_draft(farm_id=a["farm_id"], asset_code=p["asset_code"], comp_code=None, title=f"{p['title']} {p['asset_code']}",
                             description=f"依据 {p['standard']} 周期 {p['cycle_days']} 天的例行维护，应结合海况窗口合并出海。", fault_key=None,
                             warning_level=0, risk_level="L2", causes=[], actions=[{"name": p["title"]}], parts=[], crew=[], vessel=None, window=None,
                             safety={}, evidence=[{"id": "std:GB/T 32128", "title": "GB/T 32128 海上风电场运行维护规程"}], features={}, alarm_id=None,
                             alarm_time=None, task_id=None, requester="periodic-job", wo_type="routine", source="periodic")
            db.x("UPDATE periodic_plans SET next_due = next_due + cycle_days, last_done = next_due WHERE id=%s", (p["id"],))
            n += 1
        return {"created": n, "_record": bool(n)}

    def job_settle(self) -> dict:
        """工单关闭后知识沉淀（幂等）。"""
        from .services import settle
        rows = db.q("SELECT id FROM work_orders WHERE status='closed' AND NOT kg_synced AND source<>'history' LIMIT 10")
        n = 0
        for r in rows:
            try:
                settle.settle(r["id"])
                n += 1
            except Exception:
                log.exception("沉淀失败 %s", r["id"])
        return {"settled": n, "_record": bool(n)}

    def job_reports(self) -> dict:
        from .services import reports
        n = 0
        for f in db.q("SELECT id FROM wind_farms"):
            for period in ("monthly",):
                key = reports.current_key(period)
                if not db.q1("SELECT 1 FROM reports WHERE farm_id=%s AND period=%s AND period_key=%s", (f["id"], period, key)):
                    reports.generate(f["id"], period, key)
                    n += 1
        return {"generated": n, "_record": bool(n)}

    def job_model_iteration(self) -> dict:
        """规范 6.4.2：模型更新周期 ≤30 天。到期自动触发改进 Agent 月度迭代。"""
        from .services import improve
        if not improve.due_for_iteration():
            return {"due": False}
        r = improve.run_iteration()
        return {"due": True, "decision": r.get("decision"), "_record": True}

    def job_sla_watch(self) -> dict:
        """响应超时提示: 紧急工单未在 SLA 内派发时升级通知。"""
        from .services import rules
        rows = db.q("""SELECT w.id, w.wo_no, w.farm_id, w.asset_code, extract(epoch FROM (now()-w.alarm_time))/60 AS mins
                       FROM work_orders w WHERE w.wo_type='emergency' AND w.status IN ('draft','pending_approval','approved')
                         AND w.alarm_time < now() - make_interval(mins => %s::int)
                         AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.ref_type='sla' AND n.ref_id=w.id::text)""", (int(settings.response_sla_min),))
        for w in rows:
            rules.notify(w["farm_id"], "critical", f"紧急工单超时未响应：{w['wo_no']}", f"{w['asset_code']} 已 {w['mins']:.0f} 分钟，超过 {settings.response_sla_min:.0f} 分钟要求，请授权人员尽快审批",
                         "sla", str(w["id"]), "approver")
        return {"escalated": len(rows)}

    # ---- 生命周期 ----
    def start(self) -> None:
        if settings.simulator_enabled:
            from .services import faults
            self.sim = faults.get_simulator(settings.simulator_interval_s)
            self.sim.start()
        if settings.monitor_enabled:
            self._every("monitor", max(15.0, settings.simulator_interval_s), self.job_monitor, 727101, 20.0)
            self._every("sla_watch", 60.0, self.job_sla_watch, 727102, 30.0)
        self._every("archive", 1800.0, self.job_archive, 727103, 120.0)
        self._every("weather", 3600.0, self.job_weather, 727104, 60.0)
        self._every("periodic", 3600.0, self.job_periodic, 727105, 45.0)
        self._every("settle", 20.0, self.job_settle, 727106, 15.0)
        self._every("reports", 3600.0, self.job_reports, 727107, 90.0)
        self._every("model_iteration", 6 * 3600.0, self.job_model_iteration, 727108, 150.0)

    def stop(self) -> None:
        self._stop.set()
        if self.sim:
            self.sim.stop()


scheduler = Scheduler()
