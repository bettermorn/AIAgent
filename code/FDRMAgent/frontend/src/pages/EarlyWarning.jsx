import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, pct, fmtTime, streamAgent } from '../api.js';
import { Card, PageHeader, LevelTag, StatusTag, Markdown, Timeline, ErrorBox, Empty } from '../components/ui.jsx';

export default function EarlyWarning() {
  const [alerts, setAlerts] = useState([]);
  const [steps, setSteps] = useState([]);
  const [running, setRunning] = useState('');
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [active, setActive] = useState(null);
  const [form, setForm] = useState({ status: '处置中', handler: '', disposal_note: '' });
  const [filter, setFilter] = useState('');
  const ctrlRef = useRef(null);

  const load = () => api.get(`/alerts${filter ? `?status=${encodeURIComponent(filter)}` : ''}`).then(setAlerts).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [filter]);
  useEffect(() => () => ctrlRef.current?.abort(), []);

  const scan = () => {
    setSteps([]); setSummary(null); setError(''); setRunning('预警扫描启动…');
    ctrlRef.current = streamAgent('/agents/early-warning', {}, (ev) => {
      if (ev.type === 'step_started') setRunning(`${ev.step}…`);
      if (ev.type === 'step') setSteps((s) => [...s, ev]);
      if (ev.type === 'done') { setSummary(ev.result); setRunning(''); load(); }
      if (ev.type === 'error') { setError(ev.error); setRunning(''); }
    });
  };

  const openAlert = (a) => {
    setActive(a);
    setForm({ status: a.status === '待处置' ? '处置中' : a.status, handler: a.handler || '', disposal_note: a.disposal_note || '' });
  };

  const save = async () => {
    try {
      const updated = await api.patch(`/alerts/${active.id}`, form);
      setActive({ ...active, ...updated });
      load();
    } catch (e) { setError(e.message); }
  };

  return (
    <>
      <PageHeader title="风险预警智能体" desc="图计算（关联穿透）+ 异常检测（交易信号）+ 机器学习（风险评分）→ 智能体汇总研判 → 预警触发 → 处置留痕 → 复盘">
        <button className="btn primary" onClick={scan} disabled={!!running}>{running ? '扫描中…' : '运行全量预警扫描'}</button>
      </PageHeader>
      <ErrorBox error={error} />

      {summary && (
        <div className="stats">
          <div className="stat"><div className="stat-label">扫描企业</div><div className="stat-value">{summary.scanned}</div></div>
          <div className="stat red"><div className="stat-label">高等级</div><div className="stat-value">{summary.high}</div></div>
          <div className="stat orange"><div className="stat-label">中等级</div><div className="stat-value">{summary.medium}</div></div>
          <div className="stat"><div className="stat-label">运行记录</div><div className="stat-value small"><Link to={`/audit/${summary.run_id}`}>审计回放 →</Link></div></div>
        </div>
      )}

      {summary && (
        <Card title="本次扫描结果">
          <table className="table">
            <thead><tr><th>企业</th><th>预警等级</th><th>风险积分</th><th>命中信号</th><th>PD</th></tr></thead>
            <tbody>
              {summary.items.map((i) => (
                <tr key={i.company.id}>
                  <td className="strong">{i.company.name}</td>
                  <td><LevelTag level={i.level} /></td>
                  <td>{i.points}</td>
                  <td>{i.reasons.join('、') || '-'}</td>
                  <td>{pct(i.pd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <div className="grid-2">
        <Card title="预警队列" extra={(
          <select className="select small" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">全部状态</option><option>待处置</option><option>处置中</option><option>已关闭</option>
          </select>
        )}>
          {alerts.length ? (
            <div className="alert-list">
              {alerts.map((a) => (
                <div key={a.id} className={`alert-item ${active?.id === a.id ? 'selected' : ''}`} onClick={() => openAlert(a)}>
                  <div className="ai-head"><LevelTag level={a.level} /><span className="tag gray">{a.signal_type}</span><StatusTag status={a.status} /></div>
                  <div className="ai-title">{a.title}</div>
                  <div className="muted small">#{a.id} · {fmtTime(a.created_at)}{a.handler ? ` · 处置人 ${a.handler}` : ''}</div>
                </div>
              ))}
            </div>
          ) : <Empty text="暂无预警，点击右上角运行扫描" />}
        </Card>

        <Card title={active ? `预警 #${active.id} 研判与处置` : '预警详情'}>
          {active ? (
            <>
              <div className="ai-title">{active.company} </div>
              {active.detail?.analysis ? <Markdown>{active.detail.analysis}</Markdown>
                : <pre className="pre">{JSON.stringify(active.detail, null, 2)}</pre>}
              <div className="form">
                <label>处置状态
                  <select className="select" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                    <option>待处置</option><option>处置中</option><option>已关闭</option>
                  </select>
                </label>
                <label>处置人<input className="input" value={form.handler} onChange={(e) => setForm({ ...form, handler: e.target.value })} placeholder="如：风险经理 张三" /></label>
                <label>处置措施 / 复盘记录<textarea className="input" rows={3} value={form.disposal_note} onChange={(e) => setForm({ ...form, disposal_note: e.target.value })} placeholder="如：已暂停用信，追加实控人连带担保" /></label>
                <button className="btn primary" onClick={save}>保存处置（写入审计日志）</button>
              </div>
            </>
          ) : <Empty text="从左侧选择一条预警" />}
        </Card>
      </div>

      {(steps.length > 0 || running) && (
        <Card title="扫描执行轨迹"><Timeline steps={steps} running={running} /></Card>
      )}
    </>
  );
}
