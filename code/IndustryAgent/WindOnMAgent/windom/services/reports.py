"""报表与 KPI（规范 5.5c / 6.5.3）：月/季/年度绩效报表、风场 KPI；规范量化指标达标看板（文档 8.1）。"""
from __future__ import annotations

import calendar
import datetime as dt
from typing import Optional

from .. import db, llm, security
from ..config import settings
from ..db import J
from . import efficiency, modelreg, timeseries as ts, workorders as wos

UTC = dt.timezone.utc


def period_range(period: str, key: str) -> tuple[dt.datetime, dt.datetime]:
    if period == "monthly":
        y, m = map(int, key.split("-"))
        s = dt.datetime(y, m, 1, tzinfo=UTC)
        e = dt.datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=UTC)
    elif period == "quarterly":
        y, q = key.split("-Q")
        y, q = int(y), int(q)
        s = dt.datetime(y, 3 * q - 2, 1, tzinfo=UTC)
        e = dt.datetime(y + (q == 4), (3 * q) % 12 + 1, 1, tzinfo=UTC)
    elif period == "yearly":
        y = int(key)
        s, e = dt.datetime(y, 1, 1, tzinfo=UTC), dt.datetime(y + 1, 1, 1, tzinfo=UTC)
    else:
        raise ValueError("period 必须为 monthly/quarterly/yearly")
    return s, e


def current_key(period: str) -> str:
    n = dt.datetime.now(UTC)
    return f"{n.year}-{n.month:02d}" if period == "monthly" else f"{n.year}-Q{(n.month - 1) // 3 + 1}" if period == "quarterly" else str(n.year)


def build(farm_id: int, period: str, key: str) -> dict:
    s, e = period_range(period, key)
    k = wos.kpis(farm_id, s, e)
    alarms = db.q1("""SELECT count(*) n, count(*) FILTER (WHERE level=1) l1, count(*) FILTER (WHERE level=2) l2, count(*) FILTER (WHERE level=3) l3
                      FROM alarms WHERE farm_id=%s AND raised_at >= %s AND raised_at < %s""", (farm_id, s, e))
    top_faults = db.q("""SELECT fault_key, count(*) n FROM work_orders WHERE farm_id=%s AND created_at >= %s AND created_at < %s
                         GROUP BY fault_key ORDER BY n DESC LIMIT 5""", (farm_id, s, e))
    eff = efficiency.evaluate_farm(farm_id, minutes=180)
    # 监控覆盖率(规范 6.1.1 ≥90%): 近10分钟有数据的传感器占台账传感器比
    total_s = db.scalar("SELECT count(*) FROM assets WHERE type='sensor' AND farm_id=%s", (farm_id,)) or 0
    live_s = db.scalar("""SELECT count(*) FROM (SELECT DISTINCT asset_code, sensor_type FROM ts_realtime t JOIN assets a ON a.code=t.asset_code
                          WHERE a.farm_id=%s AND t.ts > now() - interval '10 minutes') x""", (farm_id,)) or 0
    kp = {
        "period": key, "workorders": k, "alarms": alarms, "top_faults": top_faults,
        "monitor_coverage": (live_s / total_s) if total_s else None,
        "efficiency": {k_: eff.get(k_) for k_ in ("farm_efficiency", "assessment_error", "assessment_error_ok", "improvement_potential_pct")} if eff.get("available") else None,
        "knowledge": {"activated": db.scalar("SELECT count(*) FROM knowledge_candidates WHERE status='activated' AND review_time >= %s AND review_time < %s", (s, e)),
                      "pending": db.scalar("SELECT count(*) FROM knowledge_candidates WHERE status='pending'")},
    }
    return kp


def narrative(farm_name: str, kp: dict) -> str:
    wo = kp["workorders"]
    fallback = (f"{farm_name} {kp['period']} 运维概况：工单 {wo['total']} 张（紧急 {wo['emergencies']}，已关闭 {wo['closed']}），"
                f"紧急工单平均响应 {('%.1f 分钟' % wo['avg_response_minutes_emergency']) if wo['avg_response_minutes_emergency'] else '无数据'}，"
                f"平均修复时长 {('%.0f 分钟' % wo['mttr_minutes']) if wo['mttr_minutes'] else '无数据'}；"
                f"告警 {kp['alarms']['n']} 条（三级 {kp['alarms']['l3']}）。")
    if not llm.available():
        return fallback
    try:
        txt = llm.chat([
            {"role": "system", "content": "你是海上风电场运维报告撰写助手。根据给定KPI用简洁中文写 150 字以内的绩效小结，指出达标/不达标项与改进建议。只使用给定数据，不要编造数字。"},
            {"role": "user", "content": str({"farm": farm_name, **kp, "targets": {"auto_dispatch": settings.auto_dispatch_target, "response_min": settings.response_sla_min}})}],
            max_tokens=400, temperature=0.2)
        return security.redact_output(txt.strip())
    except Exception:
        return fallback


def generate(farm_id: int, period: str = "monthly", key: Optional[str] = None, force: bool = False) -> dict:
    key = key or current_key(period)
    ex = db.q1("SELECT * FROM reports WHERE farm_id=%s AND period=%s AND period_key=%s", (farm_id, period, key))
    if ex and not force:
        return ex
    farm = db.q1("SELECT name FROM wind_farms WHERE id=%s", (farm_id,))
    kp = build(farm_id, period, key)
    text = narrative(farm["name"], kp)
    row = db.q1("""INSERT INTO reports(farm_id,period,period_key,kpis,narrative) VALUES (%s,%s,%s,%s,%s)
                   ON CONFLICT (farm_id,period,period_key) DO UPDATE SET kpis=EXCLUDED.kpis, narrative=EXCLUDED.narrative, created_at=now()
                   RETURNING *""", (farm_id, period, key, J(kp), text))
    return row


def spec_compliance(farm_id: Optional[int] = None) -> list[dict]:
    """规范量化指标达标表（文档 8.1）。能由本系统度量的指标给出实测值与是否达标; 属场站建设范畴者标注 ‘场站建设’。"""
    fid = farm_id or db.scalar("SELECT id FROM wind_farms ORDER BY id LIMIT 1")
    k = wos.kpis(fid, now_ := dt.datetime.now(UTC) - dt.timedelta(days=90))
    eff = efficiency.evaluate_farm(fid, 180)
    std = ts.standardization_rate()
    ev = db.q1("SELECT top1, top3, ts FROM eval_runs ORDER BY id DESC LIMIT 1")
    last_upd = modelreg.last_update("cause_ranker")
    age = (dt.datetime.now(UTC) - last_upd).days if last_upd else None
    sensors = db.scalar("SELECT count(DISTINCT sensor_type) FROM ts_realtime WHERE ts > now() - interval '10 minutes'")
    sample_s = db.scalar("""SELECT extract(epoch FROM (max(ts)-min(ts)))/NULLIF(count(*)-1,0) FROM ts_realtime
                            WHERE asset_code='WT-001' AND sensor_type='gearbox_oil_temp' AND ts > now() - interval '30 minutes'""")
    total_s = db.scalar("SELECT count(*) FROM assets WHERE type='sensor' AND farm_id=%s", (fid,)) or 0
    live_s = db.scalar("""SELECT count(*) FROM (SELECT DISTINCT asset_code, sensor_type FROM ts_realtime t JOIN assets a ON a.code=t.asset_code
                          WHERE a.farm_id=%s AND t.ts > now() - interval '10 minutes') x""", (fid,)) or 0
    edge = db.scalar("SELECT count(*) FROM edge_ingest_log")

    def row(clause, name, target, actual, ok, how, scope="系统度量"):
        return {"clause": clause, "name": name, "target": target, "actual": actual, "ok": ok, "how": how, "scope": scope}

    rows = [
        row("4b", "传感器类型数/采样频率", "≥10 类 / ≥1Hz", f"{sensors} 类 / 平均间隔 {sample_s:.0f}s" if sample_s else f"{sensors} 类",
            (sensors or 0) >= 10, "采集网关按秒级设计；仿真器按配置步长近似写入"),
        row("4c", "数据标准化率", "≥95%", f"{std['rate']:.1%}" if std["rate"] is not None else "暂无样本", None if std["rate"] is None else std["rate"] >= 0.95, "术语归一化命中率"),
        row("4d", "发电效率评估误差", "≤±2%", f"{eff['assessment_error']:.2%}" if eff.get("assessment_error") is not None else "n/a",
            eff.get("assessment_error_ok"), "功率曲线基准 + 留一法评估"),
        row("4e", "运维任务自动派发率", "≥95%", f"{k['auto_dispatch_rate']:.1%}" if k["auto_dispatch_rate"] is not None else "暂无样本",
            None if k["auto_dispatch_rate"] is None else k["auto_dispatch_rate"] >= 0.95, "审批后系统自动派发占比"),
        row("4e", "故障响应时间(紧急工单)", "≤30min", f"平均 {k['avg_response_minutes_emergency']:.1f}min / 达标率 {k['response_sla_rate']:.0%}" if k["avg_response_minutes_emergency"] is not None else "暂无样本",
            None if k["response_sla_rate"] is None else k["response_sla_rate"] >= 0.95, "告警至派发"),
        row("6.1.1", "监控覆盖率", "≥90%", f"{live_s / total_s:.1%}" if total_s else "n/a", (live_s / total_s >= 0.9) if total_s else None, "近10分钟有数据测点/台账测点"),
        row("6.3.3", "断链续传(边缘批次)", "本地缓存≥72h、自动续传", f"已接收 {edge} 个校验批次", edge > 0, "边缘节点 SQLite 缓存 + 校验和幂等入库"),
        row("6.4.2", "算法准确率", "≥85%", f"Top1 {ev['top1']:.1%}" if ev and ev["top1"] is not None else "暂无评测", None if not ev else ev["top1"] >= 0.85, "黄金集回归"),
        row("6.4.2", "模型更新周期", "≤30天", f"距上次更新 {age} 天" if age is not None else "n/a", None if age is None else age <= 30, "改进Agent月度迭代"),
        row("4a/6.2", "汇聚链路可用性/链路切换/延迟", "≥99.9% / <30ms / ≤12ms", "—", None, "HSR/PRP 冗余环网由场站网络建设保证", "场站建设"),
        row("7.x", "物理/网络/系统安全", "IP65、等保三级、GB/T 35673", "—", None, "硬件选型与等保测评，系统侧提供审计/隔离设计", "场站建设"),
    ]
    return rows
