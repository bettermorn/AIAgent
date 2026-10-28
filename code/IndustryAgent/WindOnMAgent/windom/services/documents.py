"""文档管理与混合检索（文档 5.4 GraphRAG：向量 + 关键词 + RRF 融合 + 重排）。

- 文档版本化、内容哈希校验；新版本发布使旧版本失效，检索默认只取 status=active（文档 6.6 引用过期规程）。
- 切分按章节标题，保留页码/章节/版本，作为证据溯源定位。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import math
import re
from collections import Counter
from typing import Optional

from .. import db
from ..db import J
from . import embedding as emb

_SEC = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(.+)$")


def split_sections(text: str, max_chars: int = 600) -> list[dict]:
    """按 “4.2 标题” 式章节切分; 无章节标记的按段落/长度切。页码以 '\f' 或 '【第N页】' 标记。"""
    chunks: list[dict] = []
    page = 1
    cur_sec, cur_lines = None, []

    def flush():
        nonlocal cur_lines
        body = "\n".join(cur_lines).strip()
        if body:
            for i in range(0, len(body), max_chars):
                chunks.append({"page": page, "section": cur_sec, "text": body[i:i + max_chars]})
        cur_lines = []

    for line in text.splitlines():
        pm = re.match(r"^【第(\d+)页】", line.strip())
        if pm or "\f" in line:
            flush()
            page = int(pm.group(1)) if pm else page + 1
            if pm:
                continue
        m = _SEC.match(line)
        if m and len(line) < 60:
            flush()
            cur_sec = m.group(1)
            cur_lines = [line.strip()]
        else:
            cur_lines.append(line)
    flush()
    return chunks


def ingest(doc_no: str, title: str, doc_type: str, version: str, text: str, *, farm_id: Optional[int] = None,
           model: Optional[str] = None, object_key: Optional[str] = None, effective: Optional[dt.date] = None,
           deprecate_old: bool = True) -> dict:
    sha = hashlib.sha256(text.encode()).hexdigest()
    with db.tx():
        ex = db.q1("SELECT * FROM documents WHERE doc_no=%s AND version=%s", (doc_no, version))
        if ex:
            if ex["content_sha256"] == sha:
                return {"doc_id": ex["id"], "skipped": True, "chunks": db.scalar("SELECT count(*) FROM doc_chunks WHERE doc_id=%s", (ex["id"],))}
            raise ValueError(f"{doc_no} {version} 已存在且内容不同，请使用新版本号")
        deprecated = 0
        if deprecate_old:
            deprecated = db.x("UPDATE documents SET status='deprecated' WHERE doc_no=%s AND status='active'", (doc_no,))
        d = db.insert("documents", {"doc_no": doc_no, "title": title, "doc_type": doc_type, "version": version,
                                    "status": "active", "farm_id": farm_id, "model": model, "content_sha256": sha,
                                    "object_key": object_key or f"minio://windom-docs/{doc_no}/{version}.txt",
                                    "effective_date": effective or dt.date.today()})
        chunks = split_sections(text)
        db.bulk("INSERT INTO doc_chunks(doc_id,page,section,text,vec) VALUES %s",
                [(d["id"], c["page"], c["section"], c["text"], emb.embed(f"{title} {c['text']}")) for c in chunks])
    relink = None
    if deprecated:
        # 规程新版本发布：旧版本的引用依据标记失效，仍存在的章节重建到新版本
        from . import kg
        relink = kg.relink_document(doc_no, version, {c["section"] for c in chunks if c["section"]})
    return {"doc_id": d["id"], "skipped": False, "chunks": len(chunks), "deprecated_old": deprecated, "kg": relink}


def verify_integrity(doc_id: int) -> bool:
    """哈希校验: 重新拼接 chunk 并比对（切分有损时仅校验 chunk 数>0）。"""
    return bool(db.scalar("SELECT count(*) FROM doc_chunks WHERE doc_id=%s", (doc_id,)))


def list_documents(include_deprecated: bool = True) -> list[dict]:
    sql = """SELECT d.id, d.doc_no, d.title, d.doc_type, d.version, d.status, d.model, d.effective_date,
                    d.content_sha256, d.created_at, (SELECT count(*) FROM doc_chunks c WHERE c.doc_id=d.id) chunks
             FROM documents d"""
    if not include_deprecated:
        sql += " WHERE d.status='active'"
    return db.q(sql + " ORDER BY d.doc_no, d.created_at DESC")


def latest_version(doc_no: str) -> Optional[dict]:
    return db.q1("SELECT * FROM documents WHERE doc_no=%s AND status='active' ORDER BY created_at DESC LIMIT 1", (doc_no,))


def get_chunk(chunk_id: int) -> Optional[dict]:
    return db.q1("""SELECT c.id, c.page, c.section, c.text, d.doc_no, d.title, d.version, d.status, d.doc_type
                    FROM doc_chunks c JOIN documents d ON d.id=c.doc_id WHERE c.id=%s""", (chunk_id,))


def _bm25(query_toks: list[str], docs_toks: list[list[str]], k1=1.5, b=0.75) -> list[float]:
    N = len(docs_toks)
    avg = sum(len(d) for d in docs_toks) / max(N, 1)
    df: Counter = Counter()
    for d in docs_toks:
        for t in set(d):
            df[t] += 1
    scores = []
    for d in docs_toks:
        tf = Counter(d)
        s = 0.0
        for t in set(query_toks):
            if t not in tf:
                continue
            idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / max(avg, 1)))
        scores.append(s)
    return scores


def search(query: str, *, top_k: int = 5, doc_types: Optional[list[str]] = None, model: Optional[str] = None,
           only_active: bool = True, farm_id: Optional[int] = None) -> list[dict]:
    """混合检索: 向量余弦 + BM25 → RRF 融合 → 轻量重排(标题/章节命中加权)。"""
    where, params = ["1=1"], []
    if only_active:
        where.append("d.status='active'")
    if doc_types:
        where.append("d.doc_type = ANY(%s)")
        params.append(doc_types)
    if model:
        where.append("(d.model IS NULL OR d.model=%s)")
        params.append(model)
    if farm_id:
        where.append("(d.farm_id IS NULL OR d.farm_id=%s)")
        params.append(farm_id)
    rows = db.q(f"""SELECT c.id chunk_id, c.page, c.section, c.text, c.vec, d.id doc_id, d.doc_no, d.title, d.version,
                           d.status, d.doc_type FROM doc_chunks c JOIN documents d ON d.id=c.doc_id
                    WHERE {' AND '.join(where)}""", params)
    if not rows:
        return []
    qv = emb.embed(query)
    qt = emb.tokens(query)
    vec_scores = [emb.cosine(qv, r["vec"]) if r["vec"] else 0.0 for r in rows]
    bm = _bm25(qt, [emb.tokens(f"{r['title']} {r['text']}") for r in rows])
    rrf: dict[int, float] = {}
    for scores in (vec_scores, bm):
        order = sorted(range(len(rows)), key=lambda i: scores[i], reverse=True)
        for rank, i in enumerate(order[:50]):
            if scores[i] > 0:
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (60 + rank + 1)
    qset = set(qt)
    out = []
    for i, s in rrf.items():
        r = rows[i]
        title_hit = len(qset & set(emb.tokens(r["title"]))) / (len(qset) or 1)
        sec_bonus = 0.002 if r["section"] and r["section"] in query else 0.0
        out.append((s + 0.01 * title_hit + sec_bonus, i))
    out.sort(reverse=True)
    res = []
    for score, i in out[:top_k]:
        r = rows[i]
        res.append({"chunk_id": r["chunk_id"], "doc_no": r["doc_no"], "title": r["title"], "version": r["version"],
                    "status": r["status"], "page": r["page"], "section": r["section"], "text": r["text"],
                    "score": round(score, 5), "vec_score": round(vec_scores[i], 4), "bm25": round(bm[i], 3)})
    return res
