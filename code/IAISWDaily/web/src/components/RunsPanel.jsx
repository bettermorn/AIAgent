import React, { useEffect, useState } from 'react';
import { api } from '../api.js';

export default function RunsPanel({ refreshKey }) {
  const [data, setData] = useState({ items: [], running: false });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const res = await api.runs();
        if (alive) setData(res);
      } finally {
        alive && setLoading(false);
      }
    };
    load();
    const timer = setInterval(load, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [refreshKey]);

  const statusText = { running: '进行中', success: '成功', failed: '失败' };

  return (
    <div className="panel">
      <div className="card">
        <h3>采集任务记录 {data.running && <span className="live">运行中</span>}</h3>
        {loading && <p className="muted">加载中…</p>}
        {!loading && data.items.length === 0 && <p className="muted">暂无采集记录</p>}
        <table className="table">
          <thead>
            <tr>
              <th>开始时间</th>
              <th>状态</th>
              <th>渠道</th>
              <th>检索</th>
              <th>新增</th>
              <th>耗时</th>
              <th>错误</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.id}>
                <td>{new Date(r.started_at).toLocaleString('zh-CN')}</td>
                <td>
                  <span className={`status ${r.status}`}>{statusText[r.status] || r.status}</span>
                </td>
                <td>{(r.channels || []).map((c) => CH_MAP[c] || c).join('、')}</td>
                <td>{r.collected_count}</td>
                <td>{r.inserted_count}</td>
                <td>
                  {r.finished_at
                    ? `${Math.round((new Date(r.finished_at) - new Date(r.started_at)) / 1000)}s`
                    : '-'}
                </td>
                <td className="err">{r.error || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const CH_MAP = {
  international: '国际',
  wechat: '公众号',
  bilibili: 'B站',
  news: '资讯',
};
