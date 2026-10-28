"""术语归一化（文档 3.4）：标准词表(精确/同义词) → 字符相似度 → LLM 判别 三级；结果计入 term_stats 以度量数据标准化率(≥95%，规范 4c)。"""
from __future__ import annotations

import difflib
import re
from typing import Optional

from .. import db, llm
from ..ontology import TERMS

_cache: dict[str, list[tuple[str, str, list[str]]]] = {}
_norm = re.compile(r"[\s_\-·，,。.、:：（）()]")


def n(s: str) -> str:
    return _norm.sub("", (s or "").lower())


def load_dictionary() -> dict[str, list[tuple[str, str, list[str]]]]:
    rows = db.q("SELECT category,std_key,std_name,synonyms FROM term_dictionary")
    d: dict[str, list] = {}
    for r in rows:
        d.setdefault(r["category"], []).append((r["std_key"], r["std_name"], list(r["synonyms"])))
    _cache.clear()
    _cache.update(d)
    return d


def dictionary(category: str) -> list[tuple[str, str, list[str]]]:
    if not _cache:
        load_dictionary()
    return _cache.get(category) or TERMS.get(category, [])


def _record(method: str, term: str, key: Optional[str], record: bool) -> None:
    if record:
        db.insert("term_stats", {"method": method, "term": term[:200], "std_key": key}, returning="id")


def normalize(term: str, category: str, *, use_llm: bool = True, record: bool = True, fuzzy_cut: float = 0.72) -> dict:
    """返回 {'std_key','std_name','method','score'}; 未命中 std_key=None。"""
    t = n(term)
    entries = dictionary(category)
    if not t:
        return {"std_key": None, "std_name": None, "method": "unmatched", "score": 0.0}
    # 1 精确 / 同义词
    for key, name, syns in entries:
        if t == n(key) or t == n(name):
            _record("exact", term, key, record)
            return {"std_key": key, "std_name": name, "method": "exact", "score": 1.0}
        if any(t == n(s) for s in syns):
            _record("synonym", term, key, record)
            return {"std_key": key, "std_name": name, "method": "synonym", "score": 0.97}
    # 2 包含 + 字符相似度
    best, best_s = None, 0.0
    for key, name, syns in entries:
        for cand in [name, *syns]:
            c = n(cand)
            if not c:
                continue
            s = difflib.SequenceMatcher(None, t, c).ratio()
            if len(c) >= 3 and (c in t or t in c):
                s = max(s, 0.85)
            if s > best_s:
                best, best_s = (key, name), s
    if best and best_s >= fuzzy_cut:
        _record("fuzzy", term, best[0], record)
        return {"std_key": best[0], "std_name": best[1], "method": "fuzzy", "score": round(best_s, 3)}
    # 3 LLM 判别(限定在词表内选择, 防止凭空造词)
    if use_llm and llm.available() and entries:
        try:
            opts = [{"key": k, "name": nm} for k, nm, _ in entries]
            res = llm.chat_json([
                {"role": "system", "content": "你是风电运维术语标准化助手。只能从给定候选中选择最匹配的标准术语；若都不匹配返回 null。输出 JSON：{\"std_key\": 字符串或null, \"reason\": 简短理由}"},
                {"role": "user", "content": f"类别：{category}\n待归一化术语：{term}\n候选：{opts}"}], max_tokens=200, retries=1)
            k = res.get("std_key")
            hit = next(((kk, nm) for kk, nm, _ in entries if kk == k), None)
            if hit:
                _record("llm", term, hit[0], record)
                return {"std_key": hit[0], "std_name": hit[1], "method": "llm", "score": 0.7}
        except Exception:
            pass
    _record("unmatched", term, None, record)
    return {"std_key": None, "std_name": None, "method": "unmatched", "score": round(best_s, 3)}


def learn_synonym(category: str, std_key: str, synonym: str) -> bool:
    """人工确认的新说法加入词表(审核台驳回/修改时回流)。"""
    r = db.x("""UPDATE term_dictionary SET synonyms = array_append(synonyms, %s)
                WHERE category=%s AND std_key=%s AND NOT (%s = ANY(synonyms))""", (synonym, category, std_key, synonym))
    _cache.clear()
    return bool(r)
