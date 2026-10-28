"""知识图谱服务（文档 3.3）：以 PostgreSQL 关系表建模实体/关系，递归/多跳查询，时态与溯源，约束校验。

关系带 valid_from/valid_to/source/version/confidence/status；部件更换不覆盖旧数据，规程新版本发布后旧知识标记失效。
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterable, Optional

from .. import db
from ..db import J

ACTIVE = "(r.status='active' AND (r.valid_to IS NULL OR r.valid_to > now()))"


# ----------------------------------------------------------------------------- 写入
def upsert_entity(etype: str, key: str, name: str, props: dict | None = None, status: str = "active") -> int:
    row = db.q1(
        """INSERT INTO kg_entities(type,key,name,props,status) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT (type,key) DO UPDATE SET name=EXCLUDED.name,
             props = kg_entities.props || EXCLUDED.props,
             status = CASE WHEN EXCLUDED.status='active' THEN 'active' ELSE kg_entities.status END
           RETURNING id""",
        (etype, key, name, J(props or {}), status))
    return row["id"]


def bulk_entities(rows: Iterable[tuple[str, str, str, dict]]) -> dict[tuple[str, str], int]:
    """rows: (type,key,name,props) -> {(type,key): id}"""
    rows = list(rows)
    db.bulk("INSERT INTO kg_entities(type,key,name,props) VALUES %s ON CONFLICT (type,key) DO NOTHING",
            [(t, k, n, J(p)) for t, k, n, p in rows])
    keys = {(t, k) for t, k, _, _ in rows}
    out: dict[tuple[str, str], int] = {}
    types = sorted({t for t, _ in keys})
    for t in types:
        for r in db.q("SELECT id,key FROM kg_entities WHERE type=%s", (t,)):
            if (t, r["key"]) in keys:
                out[(t, r["key"])] = r["id"]
    return out


def get_entity(etype: Optional[str], key: str) -> Optional[dict]:
    if etype:
        return db.q1("SELECT * FROM kg_entities WHERE type=%s AND key=%s", (etype, key))
    return db.q1("SELECT * FROM kg_entities WHERE key=%s ORDER BY (status='active') DESC, id LIMIT 1", (key,))


def add_relation(src: int, rel: str, dst: int, *, props: dict | None = None, source_type: str | None = None,
                 source_id: str | None = None, source_locator: str | None = None, version: str | None = None,
                 extract_model: str | None = None, reviewer: str | None = None, confidence: float = 1.0,
                 status: str = "active", valid_from: Optional[dt.datetime] = None,
                 valid_to: Optional[dt.datetime] = None) -> int:
    """同一(src,rel,dst)已有有效关系则复用并合并属性，避免重复入图。"""
    ex = db.q1("""SELECT id FROM kg_relations WHERE src=%s AND rel=%s AND dst=%s AND status<>'deprecated'
                  AND valid_to IS NULL LIMIT 1""", (src, rel, dst))
    if ex:
        if props:
            db.x("UPDATE kg_relations SET props = props || %s WHERE id=%s", (J(props), ex["id"]))
        return ex["id"]
    r = db.insert("kg_relations", {
        "src": src, "rel": rel, "dst": dst, "props": J(props or {}), "source_type": source_type,
        "source_id": source_id, "source_locator": source_locator, "version": version,
        "extract_model": extract_model, "reviewer": reviewer,
        "review_time": dt.datetime.now(dt.timezone.utc) if reviewer else None, "confidence": confidence,
        "status": status, "valid_from": valid_from or dt.datetime.now(dt.timezone.utc), "valid_to": valid_to,
    }, returning="id")
    return r["id"]


def bulk_relations(rows: Iterable[tuple]) -> int:
    """rows: (src,rel,dst,props,source_type,source_id,source_locator,version[,valid_from])"""
    now = dt.datetime.now(dt.timezone.utc)
    data = []
    for r in rows:
        s, rel, d, p, st, si, sl, v = r[:8]
        vf = r[8] if len(r) > 8 and r[8] else now
        data.append((s, rel, d, J(p or {}), st, si, sl, v, 1.0, "active", vf))
    return db.bulk(
        """INSERT INTO kg_relations(src,rel,dst,props,source_type,source_id,source_locator,version,confidence,status,valid_from)
           VALUES %s""", data)


def close_relation(rel_id: int, when: Optional[dt.datetime] = None) -> None:
    db.x("UPDATE kg_relations SET valid_to=%s WHERE id=%s", (when or dt.datetime.now(dt.timezone.utc), rel_id))


def deprecate_by_source(source_type: str, source_id: str, version: Optional[str] = None) -> int:
    """规程新版本发布：来源于旧版本的知识标记失效(文档 4.7)。"""
    if version:
        return db.x("""UPDATE kg_relations SET status='deprecated', valid_to=now()
                       WHERE source_type=%s AND source_id=%s AND version=%s AND status='active'""",
                    (source_type, source_id, version))
    return db.x("""UPDATE kg_relations SET status='deprecated', valid_to=now()
                   WHERE source_type=%s AND source_id=%s AND status='active'""", (source_type, source_id))


# ----------------------------------------------------------------------------- 查询
def neighbors(eid: int, direction: str = "out", rel: Optional[str] = None, limit: int = 500) -> list[dict]:
    if direction == "out":
        sql = f"""SELECT r.id rid, r.rel, r.props rprops, r.confidence, r.source_type, r.source_id, r.source_locator,
                         r.version, r.valid_from, r.valid_to, e.id, e.type, e.key, e.name, e.props
                  FROM kg_relations r JOIN kg_entities e ON e.id=r.dst
                  WHERE r.src=%s AND {ACTIVE} AND e.status<>'deprecated'"""
    else:
        sql = f"""SELECT r.id rid, r.rel, r.props rprops, r.confidence, r.source_type, r.source_id, r.source_locator,
                         r.version, r.valid_from, r.valid_to, e.id, e.type, e.key, e.name, e.props
                  FROM kg_relations r JOIN kg_entities e ON e.id=r.src
                  WHERE r.dst=%s AND {ACTIVE} AND e.status<>'deprecated'"""
    params: list[Any] = [eid]
    if rel:
        sql += " AND r.rel=%s"
        params.append(rel)
    sql += " LIMIT %s"
    params.append(limit)
    return db.q(sql, params)


def subgraph(key: str, depth: int = 2, max_nodes: int = 300, as_of: Optional[dt.datetime] = None) -> dict:
    """以实体为中心的 BFS 子图(双向)，含时态过滤。as_of 不为空时返回历史时点的有效关系(文档 3.3.2 时态与版本)。"""
    root = get_entity(None, key)
    if not root:
        return {"nodes": [], "edges": [], "root": None}
    nodes: dict[int, dict] = {root["id"]: _node(root)}
    edges: dict[int, dict] = {}
    frontier = [root["id"]]
    for _ in range(max(1, min(depth, 5))):
        if not frontier or len(nodes) >= max_nodes:
            break
        if as_of:
            rows = db.q("""SELECT r.*, s.type st, s.key sk, s.name sn, s.props sp, d.type dtp, d.key dk, d.name dn, d.props dp
                           FROM kg_relations r JOIN kg_entities s ON s.id=r.src JOIN kg_entities d ON d.id=r.dst
                           WHERE (r.src = ANY(%s) OR r.dst = ANY(%s))
                             AND (r.valid_from IS NULL OR r.valid_from <= %s) AND (r.valid_to IS NULL OR r.valid_to > %s)
                             AND r.status IN ('active','deprecated')""", (frontier, frontier, as_of, as_of))
        else:
            rows = db.q(f"""SELECT r.*, s.type st, s.key sk, s.name sn, s.props sp, d.type dtp, d.key dk, d.name dn, d.props dp
                            FROM kg_relations r JOIN kg_entities s ON s.id=r.src JOIN kg_entities d ON d.id=r.dst
                            WHERE (r.src = ANY(%s) OR r.dst = ANY(%s)) AND {ACTIVE}""", (frontier, frontier))
        nxt: list[int] = []
        for r in rows:
            if len(nodes) >= max_nodes:
                break
            for eid, t, k, n, p in ((r["src"], r["st"], r["sk"], r["sn"], r["sp"]), (r["dst"], r["dtp"], r["dk"], r["dn"], r["dp"])):
                if eid not in nodes:
                    nodes[eid] = {"id": eid, "type": t, "key": k, "name": n, "props": p}
                    nxt.append(eid)
            edges[r["id"]] = {"id": r["id"], "source": r["src"], "target": r["dst"], "rel": r["rel"], "props": r["props"],
                              "confidence": r["confidence"], "source_type": r["source_type"], "source_id": r["source_id"],
                              "source_locator": r["source_locator"], "version": r["version"],
                              "valid_from": r["valid_from"], "valid_to": r["valid_to"], "status": r["status"]}
        frontier = nxt
    return {"root": root["id"], "nodes": list(nodes.values()), "edges": list(edges.values())}


def _node(e: dict) -> dict:
    return {"id": e["id"], "type": e["type"], "key": e["key"], "name": e["name"], "props": e["props"]}


def component_installed_history(comp_key: str) -> list[dict]:
    """部件安装履历(含已失效关系)，用于更换追溯。"""
    return db.q("""SELECT r.valid_from, r.valid_to, r.status, t.key turbine, c.key component, r.props
                   FROM kg_relations r JOIN kg_entities c ON c.id=r.src JOIN kg_entities t ON t.id=r.dst
                   WHERE r.rel='installed_on' AND c.key=%s ORDER BY r.valid_from""", (comp_key,))


def fault_knowledge(fault_key: str) -> Optional[dict]:
    """故障 → 可能原因 → 检查项/措施 → 备件/依据 的多跳因果链(仅取 active 且有效的关系)。"""
    f = get_entity("Fault", fault_key)
    if not f:
        return None
    rows = db.q(f"""
        SELECT c.id cid, c.key ckey, c.name cname, c.props cprops, r.props rprops, r.confidence, r.source_type,
               r.source_id, r.source_locator, r.version
        FROM kg_relations r JOIN kg_entities c ON c.id=r.dst
        WHERE r.src=%s AND r.rel='possible_cause' AND {ACTIVE} AND c.status<>'deprecated'""", (f["id"],))
    causes = []
    for c in rows:
        checks = [n["name"] for n in neighbors(c["cid"], "out", "check")]
        actions = []
        for a in neighbors(c["cid"], "out", "remedy"):
            parts = [{"code": p["key"], "name": p["name"]} for p in neighbors(a["id"], "out", "needs_part")]
            docs = [{"doc_no": d["key"], "title": d["name"], "section": d["rprops"].get("section") or d["source_locator"],
                     "version": d["props"].get("version")} for d in neighbors(a["id"], "out", "cites")]
            actions.append({"key": a["key"], "name": a["name"], "parts": parts, "docs": docs,
                            "hours": a["props"].get("hours"), "needs": a["props"].get("needs", []),
                            "l3": a["props"].get("l3", False)})
        causes.append({"key": c["ckey"], "short_key": c["ckey"].split(".")[-1], "name": c["cname"],
                       "prior": float(c["rprops"].get("prior", c["cprops"].get("prior", 0.1))),
                       "signature": c["cprops"].get("signature", {}), "scenario": c["cprops"].get("scenario"),
                       "checks": checks, "actions": actions, "confidence": c["confidence"],
                       "source": {"type": c["source_type"], "id": c["source_id"], "locator": c["source_locator"],
                                  "version": c["version"]}})
    return {"fault": {"key": f["key"], "name": f["name"], "props": f["props"]}, "causes": causes}


def similar_cases(fault_key: str, comp_class: Optional[str] = None, model: Optional[str] = None, limit: int = 5) -> list[dict]:
    """历史相似案例：沿 工单-根因-措施 路径检索(同一故障，优先同型号)。"""
    rows = db.q(f"""
        SELECT w.id, w.wo_no, w.asset_code, w.title, w.root_cause, w.actual_actions, w.result, w.response_minutes,
               w.repair_minutes, w.closed_at, a.model
        FROM work_orders w LEFT JOIN assets a ON a.code = w.asset_code
        WHERE w.fault_key=%s AND w.status='closed' AND w.root_cause IS NOT NULL
        ORDER BY (a.model IS NOT DISTINCT FROM %s) DESC, w.closed_at DESC NULLS LAST LIMIT %s""",
        (fault_key, model, limit))
    return rows


def stats() -> dict:
    return {
        "entities": db.q("SELECT type, count(*) n FROM kg_entities WHERE status<>'deprecated' GROUP BY type ORDER BY n DESC"),
        "relations": db.q("SELECT rel, status, count(*) n FROM kg_relations GROUP BY rel, status ORDER BY n DESC"),
        "total_entities": db.scalar("SELECT count(*) FROM kg_entities"),
        "total_relations": db.scalar("SELECT count(*) FROM kg_relations"),
    }


def search_entities(q: str, limit: int = 20) -> list[dict]:
    like = f"%{q}%"
    return db.q("""SELECT id,type,key,name,status FROM kg_entities
                   WHERE (key ILIKE %s OR name ILIKE %s) AND status<>'deprecated' ORDER BY (key ILIKE %s) DESC, type, key LIMIT %s""",
                (like, like, q, limit))


def exists_relation(src_key: str, rel: str, dst_key: str) -> bool:
    return bool(db.q1("""SELECT 1 FROM kg_relations r JOIN kg_entities s ON s.id=r.src JOIN kg_entities d ON d.id=r.dst
                         WHERE s.key=%s AND d.key=%s AND r.rel=%s AND r.status='active' AND r.valid_to IS NULL LIMIT 1""",
                      (src_key, dst_key, rel)))


def component_class_of(comp_key: str) -> Optional[str]:
    r = db.q1("""SELECT d.key FROM kg_relations r JOIN kg_entities s ON s.id=r.src JOIN kg_entities d ON d.id=r.dst
                 WHERE s.key=%s AND r.rel='instance_of' AND r.status='active' LIMIT 1""", (comp_key,))
    return r["key"] if r else None


def relink_document(doc_no: str, new_version: str, sections: set[str]) -> dict:
    """规程新版本发布(文档 4.7)：指向旧版本的“引用依据”边标记失效；新版本仍存在的章节自动重建引用，
    使问答/诊断始终引用最新有效版本；新版本已删除的章节其依据即失效。"""
    doc = db.q1("SELECT id FROM kg_entities WHERE type='Document' AND key=%s", (doc_no,))
    if not doc:
        return {"deprecated": 0, "relinked": 0}
    db.x("UPDATE kg_entities SET props = props || %s WHERE id=%s", (J({"version": new_version}), doc["id"]))
    old = db.q("""SELECT * FROM kg_relations WHERE dst=%s AND rel='cites' AND status='active'
                  AND (version IS DISTINCT FROM %s)""", (doc["id"], new_version))
    relinked = 0
    for r in old:
        db.x("UPDATE kg_relations SET status='deprecated', valid_to=now() WHERE id=%s", (r["id"],))
        sec = (r["props"] or {}).get("section")
        if sec in sections:
            add_relation(r["src"], "cites", r["dst"], props=r["props"], source_type="document", source_id=doc_no,
                         source_locator=sec, version=new_version, confidence=r["confidence"])
            relinked += 1
    return {"deprecated": len(old), "relinked": relinked}
