import React, { useEffect, useState } from 'react';
import { api } from '../api.js';

export default function HistoryView({ onOpen, onError }) {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listHistory()
      .then(setRecords)
      .catch((e) => onError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="panel">
      <h2 className="panel-title">历史测评记录</h2>
      {loading ? (
        <div className="loading-inline">加载中…</div>
      ) : records.length === 0 ? (
        <div className="advice-empty">
          <p>暂无测评记录，先完成一次测评吧。</p>
        </div>
      ) : (
        <table className="history-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>学生</th>
              <th>年级</th>
              <th>百分制得分</th>
              <th>能力水平</th>
              <th>学习建议</th>
              <th>时间</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td>
                <td>{r.student_name}</td>
                <td>{r.grade}</td>
                <td><strong>{r.percentage}</strong></td>
                <td>{r.level}</td>
                <td>{r.has_advice ? '✅ 已生成' : '—'}</td>
                <td>{new Date(r.created_at).toLocaleString('zh-CN')}</td>
                <td><button className="btn-link" onClick={() => onOpen(r.id)}>查看报告</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
