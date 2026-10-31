import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, pct, fmtTime } from '../api.js';
import { Card, PageHeader, StatusTag, LevelTag, Markdown, ErrorBox, Empty } from '../components/ui.jsx';

export default function Reviews() {
  const [list, setList] = useState([]);
  const [filter, setFilter] = useState('待复核');
  const [active, setActive] = useState(null);
  const [form, setForm] = useState({ decision: '否决', reviewer: '', comment: '' });
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');

  const load = () => api.get(`/reviews${filter ? `?status=${encodeURIComponent(filter)}` : ''}`).then((l) => {
    setList(l);
    setActive((a) => (a ? l.find((x) => x.id === a.id) || null : l[0] || null));
  }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [filter]);

  const submit = async () => {
    setError(''); setMsg('');
    try {
      await api.post(`/reviews/${active.id}/decision`, form);
      setMsg(`复核任务 #${active.id} 已提交：${form.decision}`);
      setForm({ ...form, comment: '' });
      load();
    } catch (e) { setError(e.message); }
  };

  return (
    <>
      <PageHeader title="人工复核（人在回路）" desc="PD 超阈值、失信、担保圈 / 资金闭环、团伙线索、提示注入、数字核验未通过 → 必须由人作出最终决定">
        <select className="select" value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">全部</option><option>待复核</option><option>同意</option><option>否决</option><option>补充材料</option>
        </select>
      </PageHeader>
      <ErrorBox error={error} />
      {msg && <div className="ok-alert">{msg}</div>}
      <div className="grid-review">
        <Card title={`复核任务（${list.length}）`}>
          {list.length ? list.map((t) => (
            <div key={t.id} className={`alert-item ${active?.id === t.id ? 'selected' : ''}`} onClick={() => setActive(t)}>
              <div className="ai-head"><StatusTag status={t.status} /><LevelTag level={t.risk_level} /><span className="muted small">#{t.id}</span></div>
              <div className="ai-title">{t.company}</div>
              <div className="muted small">PD {pct(t.pd)} · {fmtTime(t.created_at)}</div>
            </div>
          )) : <Empty text="暂无复核任务" />}
        </Card>
        <div className="col">
          {active ? (
            <>
              <Card title={`${active.company} · 申请 ${active.requested_limit} 万元`} extra={<Link to={`/audit/${active.run_id}`}>查看完整留痕 →</Link>}>
                <div className="kv"><span>PD / 评分</span>{pct(active.pd)} / {active.score}</div>
                <div className="kv"><span>转人工原因</span>
                  <div>{(active.reasons || []).map((r) => <span key={r} className="tag orange">{r}</span>)}</div>
                </div>
                {active.status !== '待复核' && (
                  <div className="kv"><span>复核结论</span><b>{active.status}</b>（{active.reviewer}，{fmtTime(active.decided_at)}）：{active.comment}</div>
                )}
              </Card>
              {active.status === '待复核' && (
                <Card title="复核决定">
                  <div className="form">
                    <div className="radio-row">
                      {['同意', '否决', '补充材料'].map((d) => (
                        <label key={d} className={`radio ${form.decision === d ? 'on' : ''}`}>
                          <input type="radio" name="d" checked={form.decision === d} onChange={() => setForm({ ...form, decision: d })} />{d}
                        </label>
                      ))}
                    </div>
                    <label>复核人<input className="input" value={form.reviewer} onChange={(e) => setForm({ ...form, reviewer: e.target.value })} placeholder="如：授信审批官 李四" /></label>
                    <label>复核意见（必填，写入审计日志）<textarea className="input" rows={3} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} /></label>
                    <button className="btn primary" onClick={submit}>提交复核结论</button>
                  </div>
                </Card>
              )}
              <Card title="智能体尽调报告（供参考）"><Markdown>{active.report}</Markdown></Card>
            </>
          ) : <Card><Empty text="选择左侧任务" /></Card>}
        </div>
      </div>
    </>
  );
}
