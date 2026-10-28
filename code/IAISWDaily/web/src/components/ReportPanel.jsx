import React, { useEffect, useState } from 'react';
import { api } from '../api.js';

export default function ReportPanel({ refreshKey, channels }) {
  const [report, setReport] = useState(null);
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [date, setDate] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([api.latestReport(), api.stats(7), api.reports(20)])
      .then(([r, s, h]) => {
        if (!alive) return;
        setReport(r.report);
        setStats(s);
        setHistory(h.items);
        if (r.report?.report_date) setDate(toDateStr(r.report.report_date));
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  const loadDate = async (d) => {
    setDate(d);
    const { report: r } = await api.report(d).catch(() => ({ report: null }));
    setReport(r);
  };

  const channelLabel = (key) => channels.find((c) => c.key === key)?.label || key;

  return (
    <div className="panel">
      <div className="report-head">
        <div>
          <h2>{report?.title || '暂无日报'}</h2>
          <p className="muted">
            {report
              ? `覆盖 ${report.article_count} 条信息 · 更新于 ${new Date(report.updated_at).toLocaleString('zh-CN')}`
              : '点击右上角「立即采集」生成今日日报'}
          </p>
        </div>
        <input type="date" value={date} onChange={(e) => loadDate(e.target.value)} />
      </div>

      {loading && <Skeleton />}

      {!loading && report && (
        <>
          <section className="card">
            <h3>总体综述</h3>
            <p className="overview">{report.overview}</p>
          </section>

          {report.trends?.length > 0 && (
            <section className="card">
              <h3>趋势洞察</h3>
              <ul className="trends">
                {report.trends.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </section>
          )}

          {report.highlights?.length > 0 && (
            <section className="card">
              <h3>重点信息</h3>
              <div className="highlights">
                {report.highlights.map((h, i) => (
                  <a className="highlight" key={i} href={h.url} target="_blank" rel="noreferrer">
                    <span className="rank">{i + 1}</span>
                    <div>
                      <div className="hl-title">{h.title}</div>
                      <div className="hl-why">{h.why}</div>
                      <div className="hl-meta">{h.source || '未知来源'}</div>
                    </div>
                  </a>
                ))}
              </div>
            </section>
          )}

          <section className="card">
            <h3>近 7 日渠道分布</h3>
            <div className="bars">
              {(stats?.byChannel || []).map((c) => (
                <div className="bar-row" key={c.channel}>
                  <span className="bar-label">{channelLabel(c.channel)}</span>
                  <div className="bar-track">
                    <div
                      className="bar-fill"
                      style={{
                        width: `${Math.max(6, (c.count / Math.max(1, stats.total)) * 100)}%`,
                      }}
                    />
                  </div>
                  <span className="bar-count">{c.count}</span>
                </div>
              ))}
              {!stats?.byChannel?.length && <p className="muted">暂无数据</p>}
            </div>
          </section>
        </>
      )}

      {history.length > 0 && (
        <section className="card">
          <h3>历史日报</h3>
          <div className="history">
            {history.map((h) => (
              <button
                key={h.report_date}
                className={toDateStr(h.report_date) === date ? 'chip active' : 'chip'}
                onClick={() => loadDate(toDateStr(h.report_date))}
              >
                {toDateStr(h.report_date)} · {h.article_count} 条
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

const toDateStr = (v) => String(v).slice(0, 10);

function Skeleton() {
  return (
    <div className="card">
      <div className="sk-line w60" />
      <div className="sk-line" />
      <div className="sk-line w80" />
    </div>
  );
}
