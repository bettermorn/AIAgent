"""初始化数据：风场/台账/知识图谱/规程文档/人员船舶备件/历史工单/黄金集/时序回填。幂等：已有数据时跳过。"""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import math
import random
from typing import Optional

from . import db, ontology as ont, seed_docs, security
from .config import settings
from .db import J
from .edge import simulator as sim
from .services import documents, kg, modelreg, terms, timeseries as ts

log = logging.getLogger("windom.seed")
UTC = dt.timezone.utc

FARMS = [
    # code, name, lat, lon, turbines, prefix, substation, cable, mast, capacity
    ("EH-01", "东海一号海上风电场", 31.05, 122.50, 100, "WT-", "OSS-01", "CAB-01-01", "MAST-01", 600.0),
    ("EH-02", "东海二号海上风电场", 30.62, 122.95, 20, "WT2-", "OSS-02", "CAB-02-01", "MAST-02", 120.0),
]
MODELS = ["SG-6.0-170", "SG-6.0-170", "SG-6.0-170", "MY-6.45-180"]


def seeded() -> bool:
    return bool(db.scalar("SELECT count(*) FROM wind_farms"))


def seed_all(*, backfill_minutes: int = 180, history_hours: int = 24, rng_seed: int = 20260101) -> dict:
    if seeded():
        return {"skipped": True}
    rng = random.Random(rng_seed)
    out = {}
    with db.tx():
        _seed_reference()
        out["users"] = _seed_users()
        farm_ids = _seed_farms_assets(rng)
        out["farms"] = farm_ids
        _seed_resources(farm_ids, rng)
        _seed_knowledge_graph(farm_ids)
        out["docs"] = _seed_documents()
        out["history_wo"] = _seed_history_workorders(farm_ids, rng)
        _seed_weather_ais_media(farm_ids, rng)
        _seed_periodic_plans(farm_ids, rng)
        _seed_golden(rng)
        modelreg.get_active("cause_ranker")
        modelreg.get_active("efficiency")
        modelreg.get_active("health")
    out["backfill"] = backfill_timeseries(backfill_minutes, history_hours)
    return out


# ----------------------------------------------------------------------------- 参考数据
def _seed_reference() -> None:
    db.bulk("INSERT INTO sensor_catalog(sensor_type,name,unit,comp_type,asset_kind,sample_hz,nominal,lo,hi) VALUES %s ON CONFLICT DO NOTHING",
            [(s, n, u, c, k, 1.0, nom, lo, hi) for s, n, u, c, k, nom, lo, hi in ont.SENSORS])
    db.bulk("""INSERT INTO rules(code,name,asset_kind,sensor_type,comp_type,fault_key,direction,l1,l2,l3,window_s,doc_no,doc_section)
               VALUES %s ON CONFLICT (code) DO NOTHING""",
            [(c, f"{ont.FAULTS[fk]['name']}阈值规则", _kind(sensor), sensor, comp, fk, d, l1, l2, l3, w,
              ont.FAULTS[fk]["doc"][0], ont.FAULTS[fk]["doc"][1]) for c, sensor, comp, fk, d, l1, l2, l3, w in ont.RULES])
    rows = []
    for cat, entries in ont.TERMS.items():
        for key, name, syns in entries:
            rows.append((cat, key, name, list(dict.fromkeys(syns))))
    db.bulk("INSERT INTO term_dictionary(category,std_key,std_name,synonyms) VALUES %s ON CONFLICT DO NOTHING", rows)


def _kind(sensor: str) -> str:
    return next(k for s, _, _, _, k, *_ in ont.SENSORS if s == sensor)


def _seed_users() -> list[str]:
    h = security.hash_password(settings.demo_password)
    users = [
        ("operator1", "值班运维-张伟", "operator", ["EH-01", "EH-02"], ["offshore"]),
        ("operator2", "值班运维-李娜(仅二号场)", "operator", ["EH-02"], ["offshore"]),
        ("engineer1", "检修工程师-王强", "engineer", ["EH-01", "EH-02"], ["offshore", "climb"]),
        ("approver1", "审批人-赵主任", "approver", ["*"], ["offshore", "climb", "hv_electric"]),
        ("approver2", "审批人-钱总工", "approver", ["*"], ["offshore", "climb", "hv_electric"]),
        ("kadmin1", "知识管理员-孙丽", "knowledge_admin", ["*"], []),
        ("expert1", "领域专家-周工", "expert", ["*"], ["offshore", "climb"]),
        ("admin", "系统管理员", "admin", ["*"], ["offshore", "climb", "hv_electric"]),
    ]
    db.bulk("INSERT INTO users(username,display_name,password_hash,role,farms,quals) VALUES %s ON CONFLICT DO NOTHING",
            [(u, n, h, r, f, q) for u, n, r, f, q in users])
    return [u[0] for u in users]


# ----------------------------------------------------------------------------- 台账
def _seed_farms_assets(rng: random.Random) -> dict[str, int]:
    ids: dict[str, int] = {}
    asset_rows = []
    for code, name, lat, lon, n, prefix, oss, cab, mast, cap in FARMS:
        r = db.insert("wind_farms", {"code": code, "name": name, "lat": lat, "lon": lon, "capacity_mw": cap, "meta": J({"turbines": n})})
        fid = r["id"]
        ids[code] = fid
        cols = 10 if n >= 100 else 5
        for i in range(1, n + 1):
            tc = f"{prefix}{i:03d}"
            row, col = divmod(i - 1, cols)
            tl, tn = lat + 0.012 * row, lon + 0.015 * col
            eff = 0.935 if i in (37, 68) and code == "EH-01" else 1 + rng.gauss(0, 0.004)
            props = {"wbias": 1 + rng.gauss(0, 0.012), "eff": eff, "rated_kw": 6000}
            asset_rows.append((tc, f"{code} {i}号风机", "turbine", fid, None, None, MODELS[i % len(MODELS)], tl, tn, J(props), dt.date(2022, 6, 1) + dt.timedelta(days=i)))
            for ctype in ont.TURBINE_COMPONENT_ORDER:
                cname, sub = ont.COMPONENT_TYPES[ctype]
                suffix = {"blade": "BL", "main_shaft": "MS", "gearbox": "GB", "generator": "GN", "converter": "CV", "hydraulic": "HY", "tower": "TW"}[ctype]
                asset_rows.append((f"{tc}-{suffix}", f"{tc} {cname}", "component", fid, tc, ctype, MODELS[i % len(MODELS)], tl, tn,
                                   J({"host": tc, "subsystem": sub}), dt.date(2022, 6, 1) + dt.timedelta(days=i)))
            for s in ont.TURBINE_SENSORS:
                comp = next(x[3] for x in ont.SENSORS if x[0] == s)
                asset_rows.append((f"{tc}:{s}", f"{tc} {ont.SENSOR_NAME[s]}", "sensor", fid, tc, comp, None, tl, tn, J({"host": tc, "sensor_type": s}), None))
        # 升压站 / 海缆 / 测风塔
        mid_r, mid_c = (n // cols) / 2 * 0.012, -0.012
        asset_rows.append((oss, f"{name}海上升压站", "substation", fid, None, None, None, lat + mid_r, lon + mid_c, J({}), dt.date(2022, 3, 1)))
        asset_rows.append((f"{oss}-TR", f"{oss} 主变压器", "component", fid, oss, "transformer", None, lat + mid_r, lon + mid_c, J({"host": oss}), dt.date(2022, 3, 1)))
        asset_rows.append((f"{oss}:transformer_oil_temp", f"{oss} 主变油温", "sensor", fid, oss, "transformer", None, lat + mid_r, lon + mid_c, J({"host": oss, "sensor_type": "transformer_oil_temp"}), None))
        asset_rows.append((cab, f"{name}送出海缆", "cable", fid, None, None, None, lat + mid_r * 0.6, lon + mid_c - 0.02, J({}), dt.date(2022, 3, 1)))
        asset_rows.append((f"{cab}-BD", f"{cab} 海缆本体", "component", fid, cab, "cable_body", None, lat + mid_r * 0.6, lon + mid_c - 0.02, J({"host": cab}), dt.date(2022, 3, 1)))
        asset_rows.append((f"{cab}:cable_conductor_temp", f"{cab} 导体温度", "sensor", fid, cab, "cable_body", None, lat + mid_r * 0.6, lon + mid_c - 0.02, J({"host": cab, "sensor_type": "cable_conductor_temp"}), None))
        asset_rows.append((mast, f"{name}测风塔", "mast", fid, None, None, None, lat - 0.02, lon + 0.02, J({}), dt.date(2021, 12, 1)))
        asset_rows.append((f"{mast}-AN", f"{mast} 测风仪", "component", fid, mast, "anemometer", None, lat - 0.02, lon + 0.02, J({"host": mast}), dt.date(2021, 12, 1)))
        asset_rows.append((f"{mast}:mast_wind_speed", f"{mast} 风速", "sensor", fid, mast, "anemometer", None, lat - 0.02, lon + 0.02, J({"host": mast, "sensor_type": "mast_wind_speed"}), None))
    db.bulk("""INSERT INTO assets(code,name,type,farm_id,parent_code,comp_type,model,lat,lon,props,install_date) VALUES %s""", asset_rows)
    return ids


def _seed_resources(farm_ids: dict[str, int], rng: random.Random) -> None:
    today = dt.date.today()
    for code, fid in farm_ids.items():
        big = code == "EH-01"
        db.bulk("INSERT INTO spare_parts(code,name,comp_type,stock,location,lead_days,farm_id) VALUES %s ON CONFLICT DO NOTHING",
                [(c, n, ct, st if big else max(0, st // 2), loc, ld if big else ld + 2, fid) for c, n, ct, st, loc, ld in ont.SPARE_PARTS])
        people = [
            ("P01", "陈刚", "技术员", ["offshore", "climb"], today + dt.timedelta(days=400)),
            ("P02", "刘洋", "技术员", ["offshore", "climb"], today + dt.timedelta(days=200)),
            ("P03", "杨帆", "高压电工", ["offshore", "climb", "hv_electric"], today + dt.timedelta(days=300)),
            ("P04", "黄磊", "技术员", ["offshore"], today + dt.timedelta(days=500)),
            ("P05", "吴迪", "技术员", ["offshore", "climb"], today - dt.timedelta(days=10)),  # 证书过期
            ("P06", "徐静", "高压电工", ["offshore", "climb", "hv_electric"], today + dt.timedelta(days=150)),
            ("P07", "郑凯", "安全员", ["offshore", "climb"], today + dt.timedelta(days=250)),
            ("P08", "冯涛", "技术员", ["offshore", "climb"], today + dt.timedelta(days=330)),
        ]
        if not big:
            people = people[:5]
        db.bulk("INSERT INTO personnel(code,name,role,quals,cert_expire,farm_id) VALUES %s ON CONFLICT DO NOTHING",
                [(f"{code}-{c}", n, r, q, ce, fid) for c, n, r, q, ce in people])
        db.bulk("INSERT INTO vessels(code,name,vtype,capacity,max_wave,max_wind,farm_id) VALUES %s ON CONFLICT DO NOTHING",
                [(f"{code}-CTV1", f"{code}交通船1号", "CTV", 12, 1.5, 12.0, fid),
                 (f"{code}-CTV2", f"{code}交通船2号", "CTV", 12, 1.5, 12.0, fid)] +
                ([(f"{code}-SOV1", "运维母船SOV1", "SOV", 60, 2.5, 18.0, fid)] if big else []))


# ----------------------------------------------------------------------------- 知识图谱
def _seed_knowledge_graph(farm_ids: dict[str, int]) -> None:
    ent: dict[tuple[str, str], int] = {}

    def E(t: str, k: str, n: str, p: dict | None = None) -> int:
        key = (t, k)
        if key not in ent:
            ent[key] = kg.upsert_entity(t, k, n, p or {})
        return ent[key]

    rels: list[tuple] = []
    now = dt.datetime.now(UTC)
    ledger = ("ledger", "EAM-台账")

    def R(s, rel, d, props=None, st="ledger", si="EAM", sl=None, ver=None, vf=None):
        rels.append((s, rel, d, props or {}, st, si, sl, ver, vf))

    # ---- 本体: 部件类型 / 故障 / 原因 / 措施 / 备件 / 文档 / 预警等级 ----
    for lv, (nm, tag, resp) in ont.WARNING_LEVELS.items():
        E("WarningLevel", f"L{lv}", nm, {"level": lv, "tag": tag, "response": resp})
    doc_ver = {k: v[2] for k, v in seed_docs.DOCS.items()}
    for dno, (title, dtyp, ver, _, _) in seed_docs.DOCS.items():
        E("Document", dno, title, {"version": ver, "doc_type": dtyp})
    for ct, nm in ont.COMP_NAME.items():
        E("ComponentClass", ct, nm, {})
    for code, name, comp, stock, loc, lead in [(c, n, ct, s, l, d) for c, n, ct, s, l, d in ont.SPARE_PARTS]:
        E("SparePart", code, name, {"comp_type": comp, "lead_days": lead})
    for fk, f in ont.FAULTS.items():
        fe = E("Fault", fk, f["name"], {"comp": f["comp"], "sensor": f["sensor"], "synonyms": f["synonyms"]})
        R(E("ComponentClass", f["comp"], ont.COMP_NAME[f["comp"]]), "has_fault", fe, st="expert", si="本体设计")
        rule = next(r for r in ont.RULES if r[3] == fk)
        for lv, th in zip((1, 2, 3), rule[5:8]):
            R(fe, "warning_level", E("WarningLevel", f"L{lv}", ""), {"threshold": th, "direction": rule[4]}, "document", f["doc"][0], f["doc"][1], doc_ver[f["doc"][0]])
        for c in f["causes"]:
            ck = f"{fk}.{c['key']}"
            ce = E("Cause", ck, c["name"], {"signature": c["signature"], "scenario": c["scenario"], "short_key": c["key"]})
            R(fe, "possible_cause", ce, {"prior": c["prior"], "freq": 0}, "document", f["doc"][0], f["doc"][1], doc_ver[f["doc"][0]])
            for chk in c["checks"]:
                h = hashlib.md5(chk.encode()).hexdigest()[:8]
                R(ce, "check", E("CheckItem", f"CHK-{h}", chk), {}, "document", f["doc"][0], f["doc"][1], doc_ver[f["doc"][0]])
            for a in c["actions"]:
                ae = E("Action", a["key"], a["name"], {"hours": a["hours"], "needs": a["needs"], "l3": False})
                R(ce, "remedy", ae, {}, "document", a["doc"][0], a["doc"][1], doc_ver[a["doc"][0]])
                for pc in a["parts"]:
                    R(ae, "needs_part", E("SparePart", pc, ""), {}, "ledger", "EAM")
                R(ae, "cites", E("Document", a["doc"][0], ""), {"section": a["doc"][1]}, "document", a["doc"][0], a["doc"][1], doc_ver[a["doc"][0]])
    # ---- 资产树 ----
    assets = db.q("SELECT a.code,a.name,a.type,a.comp_type,a.parent_code,a.props,a.install_date,f.code farm FROM assets a JOIN wind_farms f ON f.id=a.farm_id ORDER BY a.id")
    farm_e: dict[str, int] = {}
    for c, fid in farm_ids.items():
        fr = db.q1("SELECT name FROM wind_farms WHERE id=%s", (fid,))
        farm_e[c] = E("WindFarm", c, fr["name"], {})
    type_map = {"turbine": "Turbine", "substation": "Substation", "cable": "Cable", "mast": "Mast", "component": "Component", "sensor": "Sensor"}
    sub_e: dict[tuple[str, str], int] = {}
    for a in assets:
        et = type_map[a["type"]]
        ae = E(et, a["code"], a["name"], {"comp_type": a["comp_type"], "model": None} if a["comp_type"] else {})
        if a["type"] in ("turbine", "substation", "cable", "mast"):
            R(farm_e[a["farm"]], "contains", ae)
        elif a["type"] == "component":
            host = a["props"].get("host")
            he = E(type_map[next(x["type"] for x in assets if x["code"] == host)], host, "")
            sub = a["props"].get("subsystem")
            vf = dt.datetime.combine(a["install_date"], dt.time(), tzinfo=UTC) if a["install_date"] else None
            if sub:
                sk = (host, sub)
                if sk not in sub_e:
                    sub_e[sk] = E("SubSystem", f"{host}:{sub}", f"{host} {sub}")
                    R(he, "contains", sub_e[sk])
                R(sub_e[sk], "contains", ae)
            else:
                R(he, "contains", ae)
            R(ae, "installed_on", he, {}, "ledger", "EAM", None, None, vf)
            if a["comp_type"] in ont.COMP_NAME:
                R(ae, "instance_of", E("ComponentClass", a["comp_type"], ""))
        elif a["type"] == "sensor":
            host = a["props"]["host"]
            comp_code = next((x["code"] for x in assets if x["type"] == "component" and x["props"].get("host") == host and x["comp_type"] == a["comp_type"]), None)
            target = E("Component", comp_code, "") if comp_code else E(type_map[next(x["type"] for x in assets if x["code"] == host)], host, "")
            R(ae, "monitors", target)
    # ---- 部件更换履历(时态与版本): WT-023 齿轮箱 2025-08 更换 ----
    old = E("Component", "WT-023-GB-OLD", "WT-023 旧齿轮箱(2023-05 至 2025-08)", {"comp_type": "gearbox", "replaced": True})
    R(old, "installed_on", E("Turbine", "WT-023", ""), {"note": "因轴承磨损更换"}, "ledger", "EAM-W2025-0815", None, None, dt.datetime(2023, 5, 1, tzinfo=UTC))
    kg.bulk_relations([(ent[(s[0], s[1])] if isinstance(s, tuple) else s, rel, ent[(d[0], d[1])] if isinstance(d, tuple) else d, p, st, si, sl, ver, vf)
                       for s, rel, d, p, st, si, sl, ver, vf in rels])
    # 旧部件关系设置失效日期
    db.x("""UPDATE kg_relations SET valid_to='2025-08-15' WHERE src=%s AND rel='installed_on'""", (ent[("Component", "WT-023-GB-OLD")],))
    # 旧齿轮箱不应再有 instance_of 的有效意义, 仅保留安装履历
    db.x("UPDATE kg_entities SET status='deprecated' WHERE key='WT-023-GB-OLD' AND FALSE")


# ----------------------------------------------------------------------------- 文档
def _seed_documents() -> dict:
    n = 0
    for dno, (title, dtyp, ver, sections) in seed_docs.DOC_OLD_VERSIONS.items():
        documents.ingest(dno, title, dtyp, ver, seed_docs.render(sections), effective=dt.date(2022, 1, 1))
        n += 1
    for dno, (title, dtyp, ver, model, sections) in seed_docs.DOCS.items():
        documents.ingest(dno, title, dtyp, ver, seed_docs.render(sections), model=model, effective=dt.date(2025, 1, 1))
        n += 1
    return {"documents": n}


# ----------------------------------------------------------------------------- 历史工单
def _seed_history_workorders(farm_ids: dict[str, int], rng: random.Random, n: int = 160) -> int:
    fid = farm_ids["EH-01"]
    turbs = [r["code"] for r in db.q("SELECT code FROM assets WHERE type='turbine' AND farm_id=%s ORDER BY code", (fid,))]
    now = dt.datetime.now(UTC)
    fk_list = [k for k in ont.FAULTS if ont.FAULTS[k]["comp"] not in ("transformer", "cable_body")]
    ent_rows = []
    wo_rows = []
    sig_flip = 0.08
    for i in range(n):
        fk = rng.choice(fk_list)
        f = ont.FAULTS[fk]
        cause = rng.choices(f["causes"], weights=[c["prior"] for c in f["causes"]])[0]
        asset = rng.choice(turbs)
        closed = now - dt.timedelta(days=rng.uniform(3, 360), hours=rng.uniform(0, 20))
        alarm_t = closed - dt.timedelta(hours=rng.uniform(8, 72))
        level = rng.choices([1, 2, 3], [0.35, 0.5, 0.15])[0]
        resp = rng.uniform(6, 41) if level >= 2 else rng.uniform(20, 180)
        repair = rng.uniform(120, 900)
        action = cause["actions"][0]
        # 诊断时特征快照(带少量噪声), 供改进 Agent 评估与校准
        dirs = {}
        for s, d in cause["signature"].items():
            dirs[s] = d if rng.random() > sig_flip else rng.choice([-1, 0, 1])
        wo_no = f"F-{closed.year}-{i + 1:03d}"
        wo_rows.append((wo_no, fid, asset, f"{asset}-{ {'gearbox':'GB','generator':'GN','converter':'CV','hydraulic':'HY','main_shaft':'MS','blade':'BL','tower':'TW'}[f['comp']] }",
                        "emergency" if level >= 2 else "normal", "closed", level, f"{asset}{f['name']}",
                        f"{f['name']}，处理措施：{action['name']}。", fk, J([{"key": cause["key"], "name": cause["name"]}]),
                        J([{"key": action["key"], "name": action["name"]}]), alarm_t, alarm_t + dt.timedelta(minutes=2), closed,
                        resp, repair, "处理后运行恢复正常", cause["name"], f"{fk}.{cause['key']}",
                        J([{"key": action["key"], "name": action["name"]}]), True, "history", J({"dirs": dirs}), True))
    db.bulk("""INSERT INTO work_orders(wo_no,farm_id,asset_code,comp_code,wo_type,status,warning_level,title,description,fault_key,
                 causes,actions,alarm_time,created_at,closed_at,response_minutes,repair_minutes,result,root_cause,root_cause_key,
                 actual_actions,effective,source,features,kg_synced) VALUES %s""",
            [(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8], a[9], a[10], a[11], a[12], a[13], a[14], a[15], a[16], a[17], a[18],
              a[19], a[20], a[21], a[22], a[23], a[24]) for a in wo_rows])
    # 经典案例 F-2023-018: WT-023 齿轮箱油温高 → 冷却器堵塞 → 清理滤网
    t0 = now - dt.timedelta(days=500)
    db.insert("work_orders", {
        "wo_no": "F-2023-018", "farm_id": fid, "asset_code": "WT-023", "comp_code": "WT-023-GB", "wo_type": "emergency", "status": "closed",
        "warning_level": 2, "title": "WT-023 齿轮箱油温过高", "description": "高负荷运行期间油温持续升高，冷却器进风口积尘严重。",
        "fault_key": "GearboxOilTempHigh", "causes": J([{"key": "CoolerClogged", "name": "冷却器堵塞/积尘"}]),
        "actions": J([{"key": "CleanFilter", "name": "清理冷却器滤网"}]), "alarm_time": t0, "created_at": t0, "closed_at": t0 + dt.timedelta(hours=9),
        "response_minutes": 22, "repair_minutes": 210, "result": "温度恢复正常", "root_cause": "冷却器堵塞/积尘",
        "root_cause_key": "GearboxOilTempHigh.CoolerClogged", "actual_actions": J([{"key": "CleanFilter", "name": "清理冷却器滤网"}]),
        "effective": True, "source": "history", "features": J({"dirs": {"cooling_airflow": -1, "gearbox_vibration": 0, "gearbox_oil_pressure": 0}}), "kg_synced": True})
    # 历史工单进入图谱(WorkOrder 实体), 形成 告警→工单→根因→措施 路径
    for r in db.q("SELECT wo_no, fault_key, root_cause_key, actual_actions, comp_code, asset_code, closed_at FROM work_orders WHERE source='history'"):
        we = kg.upsert_entity("WorkOrder", r["wo_no"], r["wo_no"], {"asset": r["asset_code"]})
        fe, ce = kg.get_entity("Fault", r["fault_key"]), kg.get_entity("Cause", r["root_cause_key"])
        comp = kg.get_entity("Component", r["comp_code"]) if r["comp_code"] else None
        kw = dict(source_type="workorder", source_id=r["wo_no"], reviewer="history-import", confidence=1.0, valid_from=r["closed_at"])
        kg.add_relation(we, "handles", fe["id"], **kw)
        if ce:
            kg.add_relation(we, "root_cause", ce["id"], **kw)
        if comp:
            kg.add_relation(we, "on_component", comp["id"], **kw)
        for a in r["actual_actions"]:
            ae = kg.get_entity("Action", a["key"])
            if ae:
                kg.add_relation(we, "adopted", ae["id"], **kw)
    # 将历史工单计入因果关系频次
    for r in db.q("SELECT fault_key, root_cause_key, count(*) n FROM work_orders WHERE source='history' GROUP BY 1,2"):
        fe, ce = kg.get_entity("Fault", r["fault_key"]), kg.get_entity("Cause", r["root_cause_key"])
        if fe and ce:
            db.x("UPDATE kg_relations SET props = props || %s WHERE src=%s AND dst=%s AND rel='possible_cause'",
                 (J({"freq": r["n"]}), fe["id"], ce["id"]))
    return n + 1


# ----------------------------------------------------------------------------- 气象 / AIS / 多源监测
def sea_state(farm_id: int, t: dt.datetime) -> tuple[float, float, float]:
    """确定性海况预报: (风速, 有效波高, 能见度km)。每约36小时出现一个适宜窗口。"""
    s = t.timestamp() / 3600.0
    wave = 1.15 + 0.85 * math.sin(2 * math.pi * s / 36 + farm_id) + 0.25 * math.sin(2 * math.pi * s / 11)
    wind = 8.5 + 4.5 * math.sin(2 * math.pi * s / 36 + farm_id + 0.4) + 1.2 * math.sin(2 * math.pi * s / 7)
    vis = 9.0 + 4.0 * math.sin(2 * math.pi * s / 52 + farm_id)
    return max(0.2, wind), max(0.2, wave), max(0.5, vis)


def _seed_weather_ais_media(farm_ids: dict[str, int], rng: random.Random) -> None:
    refresh_weather(farm_ids)
    ships = [("413000001", "东海巡检1号", "patrol"), ("413000002", "海运货轮A", "cargo"), ("413000003", "渔船B", "fishing")]
    for code, fid in farm_ids.items():
        f = db.q1("SELECT lat, lon FROM wind_farms WHERE id=%s", (fid,))
        db.bulk("""INSERT INTO ais_vessels(mmsi,farm_id,name,ship_type,lat,lon,sog) VALUES %s ON CONFLICT (mmsi) DO NOTHING""",
                [(f"{m}{fid}", fid, n, t, f["lat"] + rng.uniform(-0.05, 0.12), f["lon"] + rng.uniform(-0.05, 0.12), rng.uniform(0, 12)) for m, n, t in ships])
    rows = []
    for a in db.q("SELECT code, farm_id FROM assets WHERE code IN ('WT-023','WT-017','WT-068','OSS-01','CAB-01-01')"):
        for kind in ("video", "infrared", "acoustic", "strain"):
            rows.append((a["farm_id"], a["code"], kind, f"minio://windom-media/{a['code']}/{kind}/latest.bin",
                         hashlib.sha256(f"{a['code']}{kind}".encode()).hexdigest(), dt.datetime.now(UTC) - dt.timedelta(minutes=rng.randint(5, 600)),
                         {"video": "视频巡检画面正常", "infrared": "红外热像：最高温点位于冷却器附近，较环境高 18K", "acoustic": "声学：未见异常啸叫", "strain": "塔筒应变在正常范围"}[kind], J({})))
    db.bulk("INSERT INTO monitoring_media(farm_id,asset_code,kind,object_key,sha256,ts,summary,meta) VALUES %s", rows)


def refresh_weather(farm_ids: Optional[dict[str, int]] = None, hours: int = 120) -> int:
    farm_ids = farm_ids or {r["code"]: r["id"] for r in db.q("SELECT id, code FROM wind_farms")}
    start = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    rows = []
    for _, fid in farm_ids.items():
        for h in range(-6, hours):
            t = start + dt.timedelta(hours=h)
            w, wave, vis = sea_state(fid, t)
            rows.append((fid, t, round(w, 2), round(wave, 2), round(vis, 1)))
    return db.bulk("""INSERT INTO weather_forecast(farm_id,ts,wind_speed,wave_height,visibility_km) VALUES %s
                      ON CONFLICT (farm_id,ts) DO UPDATE SET wind_speed=EXCLUDED.wind_speed, wave_height=EXCLUDED.wave_height,
                      visibility_km=EXCLUDED.visibility_km""", rows)


def _seed_periodic_plans(farm_ids: dict[str, int], rng: random.Random) -> None:
    today = dt.date.today()
    rows = []
    for code, fid in farm_ids.items():
        for t in db.q("SELECT code FROM assets WHERE type='turbine' AND farm_id=%s ORDER BY code", (fid,)):
            for title, cyc in (("半年定期检查(传动/液压/电气)", 182), ("年度全面检修", 365)):
                nd = today + dt.timedelta(days=rng.randint(-3, 90) if cyc == 182 else rng.randint(20, 300))
                rows.append((fid, t["code"], title, cyc, "GB/T 32128", nd - dt.timedelta(days=cyc), nd))
    db.bulk("INSERT INTO periodic_plans(farm_id,asset_code,title,cycle_days,standard,last_done,next_due) VALUES %s", rows)


def _seed_golden(rng: random.Random) -> None:
    """黄金测试集: 每种故障原因若干特征组合(少量噪声), 用于模型更新门禁回归。"""
    rows = []
    for fk, f in ont.FAULTS.items():
        for c in f["causes"]:
            for i in range(6):
                dirs = {s: (d if rng.random() > 0.05 else 0) for s, d in c["signature"].items()}
                rows.append((f"{fk}.{c['key']}#{i}", J({"dirs": dirs}), f"{fk}.{c['key']}", fk))
    db.bulk("INSERT INTO eval_golden(name,scenario,expected_cause,fault_key) VALUES %s", rows)


# ----------------------------------------------------------------------------- 时序回填
def backfill_timeseries(minutes: int = 180, history_hours: int = 24, step_s: int = 60) -> dict:
    assets = db.q("SELECT code, type, farm_id, props FROM assets WHERE type IN ('turbine','substation','cable','mast')")
    rng = random.Random(7)
    end = dt.datetime.now(UTC).replace(microsecond=0)
    start = end - dt.timedelta(minutes=minutes)
    n = 0
    t = start
    while t <= end:
        rows = sim.generate_snapshot(t, assets, [], rng)
        n += ts.write_points(rows)
        t += dt.timedelta(seconds=step_s)
    # 历史库(冷数据): 更早的 history_hours 小时, 10 分钟聚合
    h_end = start
    h_start = h_end - dt.timedelta(hours=history_hours)
    hist = []
    t = h_start
    hrng = random.Random(11)
    while t < h_end:
        for r in sim.generate_snapshot(t, assets, [], hrng):
            hist.append((r[0], r[1], t, r[3], r[3], r[3], 1))
        t += dt.timedelta(minutes=10)
    nh = db.bulk("""INSERT INTO ts_history(asset_code,sensor_type,ts,value,vmin,vmax,n) VALUES %s ON CONFLICT DO NOTHING""", hist, page_size=5000)
    return {"realtime_rows": n, "history_rows": nh}
