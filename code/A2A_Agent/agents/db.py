"""
PostgreSQL 存储模块：记录每次网络搜索的结果

配置读取自项目根目录 config.env：
    POSTGRES_HOST / POSTGRES_PORT / POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD

数据表 search_results 结构：
    id         自增主键
    query      搜索关键词
    topic      解析出的主题
    title      结果标题
    url        结果链接
    snippet    摘要
    source     搜索源 (serpapi / bocha)
    raw        原始结果 JSONB
    created_at 记录时间

所有函数均为 best-effort：数据库不可用时打日志而不中断业务。
"""
import os
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json, RealDictCursor

# llm_client 在导入时已加载 config.env
from llm_client import DEEPSEEK_MODEL  # noqa: F401  (确保 config.env 已加载)

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "dbname": os.getenv("POSTGRES_DB", "a2a_news"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
}

INIT_SQL = """
CREATE TABLE IF NOT EXISTS search_results (
    id         BIGSERIAL PRIMARY KEY,
    query      TEXT NOT NULL,
    topic      TEXT NOT NULL DEFAULT '',
    title      TEXT NOT NULL,
    url        TEXT NOT NULL DEFAULT '',
    snippet    TEXT NOT NULL DEFAULT '',
    source     VARCHAR(32) NOT NULL DEFAULT '',
    raw        JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_search_results_topic_time
    ON search_results (topic, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_results_url
    ON search_results (url);
"""


@contextmanager
def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> bool:
    """初始化数据表（幂等）。成功返回 True。"""
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(INIT_SQL)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[db] ⚠️ PostgreSQL 初始化失败（搜索结果将不入库）: {e}")
        return False


def save_results(query: str, topic: str, source: str, results: list) -> int:
    """将一次搜索的结果批量写入数据库，返回写入条数。"""
    if not results:
        return 0
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO search_results (query, topic, title, url, snippet, source, raw)
                VALUES (%(query)s, %(topic)s, %(title)s, %(url)s, %(snippet)s, %(source)s, %(raw)s)
                """,
                [
                    {
                        "query": query,
                        "topic": topic,
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("snippet", ""),
                        "source": source,
                        "raw": Json(r),
                    }
                    for r in results
                ],
            )
        print(f"[db] 💾 已保存 {len(results)} 条搜索结果 (query={query!r}, source={source})")
        return len(results)
    except Exception as e:  # noqa: BLE001
        print(f"[db] ⚠️ 保存搜索结果失败: {e}")
        return 0


def recent_results(topic: str = "", limit: int = 20) -> list:
    """查询最近的搜索记录（可按主题过滤）。"""
    try:
        sql = """
            SELECT id, query, topic, title, url, snippet, source, created_at
            FROM search_results
        """
        params: list = []
        if topic:
            sql += " WHERE topic = %s"
            params.append(topic)
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with get_conn() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        for row in rows:
            if row.get("created_at") is not None:
                row["created_at"] = row["created_at"].isoformat()
        return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        print(f"[db] ⚠️ 查询搜索记录失败: {e}")
        return []
