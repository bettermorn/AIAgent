"""模型注册表（文档 5.5 模型治理）：模型版本登记、激活/灰度、Agent 每次调用记录模型版本。"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .. import db
from ..db import J

DEFAULT_PARAMS = {
    "cause_ranker": {"match_p": 0.85, "z_thr": 3.0, "prior_weight": 1.0, "if_weight": 0.0},
    "efficiency": {"bin_width": 0.5, "min_ws": 3.0, "max_ws": 24.0},
    "health": {"w_min": 0.6, "w_mean": 0.4},
}


def get_active(name: str) -> dict:
    r = db.q1("SELECT * FROM model_registry WHERE name=%s AND status='active' ORDER BY promoted_at DESC NULLS LAST, id DESC LIMIT 1", (name,))
    if r:
        return r
    # 首次使用自动登记默认版本
    return register(name, "v1.0", DEFAULT_PARAMS.get(name, {}), status="active", note="默认参数")


def params(name: str) -> dict:
    return {**DEFAULT_PARAMS.get(name, {}), **(get_active(name)["params"] or {})}


def version_tag(name: str) -> str:
    r = get_active(name)
    return f"{r['name']}@{r['version']}"


def register(name: str, version: str, params: dict, *, status: str = "shadow", metrics: Optional[dict] = None, note: str = "") -> dict:
    ex = db.q1("SELECT * FROM model_registry WHERE name=%s AND version=%s", (name, version))
    if ex:
        return ex
    return db.insert("model_registry", {"name": name, "version": version, "status": status, "params": J(params),
                                        "metrics": J(metrics or {}), "note": note,
                                        "promoted_at": dt.datetime.now(dt.timezone.utc) if status == "active" else None})


def promote(model_id: int) -> dict:
    """灰度发布→全量: 同名旧 active 退役。"""
    m = db.q1("SELECT * FROM model_registry WHERE id=%s", (model_id,))
    if not m:
        raise ValueError("模型不存在")
    with db.tx():
        db.x("UPDATE model_registry SET status='retired' WHERE name=%s AND status='active'", (m["name"],))
        db.x("UPDATE model_registry SET status='active', promoted_at=now() WHERE id=%s", (model_id,))
    return db.q1("SELECT * FROM model_registry WHERE id=%s", (model_id,))


def reject(model_id: int, reason: str) -> None:
    db.x("UPDATE model_registry SET status='rejected', note=coalesce(note,'') || %s WHERE id=%s", (f" | 拒绝: {reason}", model_id))


def next_version(name: str) -> str:
    n = db.scalar("SELECT count(*) FROM model_registry WHERE name=%s", (name,)) or 0
    return f"v1.{n}"


def list_models() -> list[dict]:
    return db.q("SELECT * FROM model_registry ORDER BY name, id DESC")


def last_update(name: str) -> Optional[dt.datetime]:
    return db.scalar("SELECT max(coalesce(promoted_at, created_at)) FROM model_registry WHERE name=%s AND status IN ('active','retired')", (name,))
