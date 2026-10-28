"""PostgreSQL 访问层：线程安全连接池 + 线程内事务 + 初始化(建库/建表)。"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import sql as pgsql

from .config import settings


def _dumps(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, default=_default)


def _default(o: Any):
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, decimal.Decimal):
        return float(o)
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def J(obj: Any) -> psycopg2.extras.Json:
    """显式 JSONB 参数封装(列表/字典均可)。"""
    return psycopg2.extras.Json(obj, dumps=_dumps)


psycopg2.extensions.register_adapter(dict, J)
psycopg2.extras.register_uuid()
# NUMERIC -> float
psycopg2.extensions.register_type(
    psycopg2.extensions.new_type(psycopg2.extensions.DECIMAL.values, "DEC2FLOAT",
                                 lambda v, c: float(v) if v is not None else None))

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()
_local = threading.local()


def _connect_kwargs(database: str | None = None) -> dict:
    kw = dict(host=settings.pg_host, port=settings.pg_port, user=settings.pg_user,
              dbname=database or settings.pg_database, connect_timeout=10,
              application_name="windom-agent")
    if settings.pg_password:
        kw["password"] = settings.pg_password
    return kw


def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(2, settings.pg_pool_max, **_connect_kwargs())
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def tx():
    """事务上下文：同一线程内嵌套使用时复用连接，最外层提交/回滚。"""
    existing = getattr(_local, "conn", None)
    if existing is not None:
        yield existing
        return
    pool = get_pool()
    conn = pool.getconn()
    conn.autocommit = False
    _local.conn = conn
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _local.conn = None
        pool.putconn(conn)


def _cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def q(sql: str, params: Any = None) -> list[dict]:
    with tx() as c:
        with _cur(c) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()] if cur.description else []


def q1(sql: str, params: Any = None) -> Optional[dict]:
    rows = q(sql, params)
    return rows[0] if rows else None


def x(sql: str, params: Any = None) -> int:
    with tx() as c:
        with _cur(c) as cur:
            cur.execute(sql, params)
            return cur.rowcount


def scalar(sql: str, params: Any = None) -> Any:
    r = q(sql, params)
    if not r:
        return None
    return next(iter(r[0].values()))


def insert(table: str, data: dict, returning: str = "*") -> dict:
    cols = list(data.keys())
    stmt = pgsql.SQL("INSERT INTO {t} ({c}) VALUES ({v}) RETURNING " + returning).format(
        t=pgsql.Identifier(table),
        c=pgsql.SQL(", ").join(map(pgsql.Identifier, cols)),
        v=pgsql.SQL(", ").join(pgsql.Placeholder() * len(cols)),
    )
    with tx() as c:
        with _cur(c) as cur:
            cur.execute(stmt, [_wrap(data[k]) for k in cols])
            return dict(cur.fetchone())


def update(table: str, id_col: str, id_val: Any, data: dict) -> int:
    if not data:
        return 0
    cols = list(data.keys())
    stmt = pgsql.SQL("UPDATE {t} SET {s} WHERE {i} = %s").format(
        t=pgsql.Identifier(table),
        s=pgsql.SQL(", ").join(pgsql.SQL("{} = %s").format(pgsql.Identifier(k)) for k in cols),
        i=pgsql.Identifier(id_col),
    )
    with tx() as c:
        with _cur(c) as cur:
            cur.execute(stmt, [_wrap(data[k]) for k in cols] + [id_val])
            return cur.rowcount


def _wrap(v: Any) -> Any:
    if isinstance(v, list) and v and isinstance(v[0], (dict, list)):
        return J(v)
    return v


def bulk(sql: str, rows: Iterable[tuple], page_size: int = 2000) -> int:
    """execute_values 批量写入；sql 中以 VALUES %s 占位。"""
    rows = list(rows)
    if not rows:
        return 0
    with tx() as c:
        with _cur(c) as cur:
            psycopg2.extras.execute_values(cur, sql, rows, page_size=page_size)
    return len(rows)


def advisory_lock(key: int) -> bool:
    """会话级 try-lock，用于多进程下后台作业单例。"""
    return bool(scalar("SELECT pg_try_advisory_xact_lock(%s)", (key,)))


def ensure_database() -> None:
    conn = psycopg2.connect(**_connect_kwargs("postgres"))
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.pg_database,))
            if not cur.fetchone():
                cur.execute(pgsql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(pgsql.Identifier(settings.pg_database)))
    finally:
        conn.close()


def init_schema() -> None:
    ddl = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    with tx() as c:
        with c.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(727001)")
            cur.execute(ddl)


def init_db() -> None:
    ensure_database()
    init_schema()


def health() -> dict:
    try:
        v = scalar("SELECT version()")
        return {"ok": True, "version": v, "database": settings.pg_database}
    except Exception as e:  # pragma: no cover
        return {"ok": False, "error": str(e)}


def reset_schema() -> None:
    """危险：清空本项目专用数据库的 public schema 并重建。仅用于开发/测试。"""
    close_pool()
    with tx() as c:
        with c.cursor() as cur:
            cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    close_pool()
    init_schema()
