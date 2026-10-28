import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';

export default function ArticlesPanel({ refreshKey, channels }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ channel: '', q: '', days: 7, onlySummarized: false });
  const [offset, setOffset] = useState(0);
  const LIMIT = 30;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.articles({
        channel: filters.channel,
        q: filters.q,
        days: filters.days,
        onlySummarized: filters.onlySummarized ? 'true' : '',
        limit: LIMIT,
        offset,
      });
      setItems(data.items);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [filters, offset]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  useEffect(() => {
    setOffset(0);
  }, [filters]);

  const update = (patch) => setFilters((f) => ({ ...f, ...patch }));

  return (
    <div className="panel">
      <div className="filters">
        <button
          className={filters.channel === '' ? 'chip active' : 'chip'}
          onClick={() => update({ channel: '' })}
        >
          全部
        </button>
        {channels.map((c) => (
          <button
            key={c.key}
            className={filters.channel === c.key ? 'chip active' : 'chip'}
            onClick={() => update({ channel: c.key })}
          >
            {c.label}
          </button>
        ))}
        <input
          className="search-input"
          placeholder="搜索标题或摘要…"
          value={filters.q}
          onChange={(e) => update({ q: e.target.value })}
        />
        <select value={filters.days} onChange={(e) => update({ days: Number(e.target.value) })}>
          <option value={1}>近 1 天</option>
          <option value={3}>近 3 天</option>
          <option value={7}>近 7 天</option>
          <option value={30}>近 30 天</option>
          <option value={365}>全部</option>
        </select>
        <label className="check">
          <input
            type="checkbox"
            checked={filters.onlySummarized}
            onChange={(e) => update({ onlySummarized: e.target.checked })}
          />
          仅看已总结
        </label>
        <span className="muted">共 {total} 条</span>
      </div>

      {loading && <p className="muted">加载中…</p>}
      {!loading && items.length === 0 && <p className="muted">没有符合条件的信息</p>}

      <div className="article-list">
        {items.map((a) => (
          <article className="article" key={a.id}>
            <div className="article-main">
              <a className="article-title" href={a.url} target="_blank" rel="noreferrer">
                {a.title}
              </a>
              <p className="article-summary">{a.summary || a.snippet || '暂无摘要'}</p>
              <div className="article-meta">
                <span className="tag channel">{channelLabel(a.channel)}</span>
                {a.category && <span className="tag">{a.category}</span>}
                {(a.tags || []).slice(0, 3).map((t) => (
                  <span className="tag ghost" key={t}>
                    #{t}
                  </span>
                ))}
                <span className="muted">{a.source || '未知来源'}</span>
                <span className="muted">
                  {a.published_at
                    ? new Date(a.published_at).toLocaleDateString('zh-CN')
                    : new Date(a.collected_at).toLocaleDateString('zh-CN')}
                </span>
              </div>
            </div>
            {a.score != null && <div className="score">{Number(a.score).toFixed(1)}</div>}
          </article>
        ))}
      </div>

      <div className="pager">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>
          上一页
        </button>
        <span className="muted">
          {Math.floor(offset / LIMIT) + 1} / {Math.max(1, Math.ceil(total / LIMIT))}
        </span>
        <button disabled={offset + LIMIT >= total} onClick={() => setOffset(offset + LIMIT)}>
          下一页
        </button>
      </div>
    </div>
  );
}

function channelLabel(key) {
  const map = {
    international: '国际站点',
    wechat: '微信公众号',
    bilibili: 'B站',
    news: '中文资讯',
  };
  return map[key] || key;
}
