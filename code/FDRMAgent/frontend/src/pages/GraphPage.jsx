import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { Card, PageHeader, ErrorBox, Empty } from '../components/ui.jsx';

const TYPE_STYLE = {
  company: { color: '#3b82f6', label: '企业', r: 16 },
  person: { color: '#8b5cf6', label: '自然人', r: 13 },
  device: { color: '#ef4444', label: '设备', r: 12 },
  phone: { color: '#f97316', label: '电话', r: 12 },
  account: { color: '#10b981', label: '账户', r: 10 },
  wifi: { color: '#eab308', label: 'Wi-Fi', r: 11 },
};
const REL_COLOR = { 担保: '#ef4444', 转账: '#f59e0b', 实控: '#8b5cf6', 控股: '#3b82f6', 使用: '#94a3b8' };

// 简单力导向布局（确定性初始化，迭代 300 次）
function layout(nodes, edges, W, H) {
  const pos = new Map(nodes.map((n, i) => {
    const a = (2 * Math.PI * i) / nodes.length;
    return [n.id, { x: W / 2 + (W / 3) * Math.cos(a), y: H / 2 + (H / 3) * Math.sin(a), vx: 0, vy: 0 }];
  }));
  const k = Math.sqrt((W * H) / Math.max(1, nodes.length)) * 0.6;
  for (let it = 0; it < 300; it += 1) {
    const t = 1 - it / 300;
    for (const a of nodes) {
      const pa = pos.get(a.id);
      for (const b of nodes) {
        if (a === b) continue;
        const pb = pos.get(b.id);
        const dx = pa.x - pb.x; const dy = pa.y - pb.y;
        const d = Math.max(1, Math.hypot(dx, dy));
        const f = (k * k) / d / 30;
        pa.vx += (dx / d) * f; pa.vy += (dy / d) * f;
      }
    }
    for (const e of edges) {
      const ps = pos.get(e.source); const pt = pos.get(e.target);
      const dx = ps.x - pt.x; const dy = ps.y - pt.y;
      const d = Math.max(1, Math.hypot(dx, dy));
      const f = (d * d) / k / 60;
      ps.vx -= (dx / d) * f; ps.vy -= (dy / d) * f;
      pt.vx += (dx / d) * f; pt.vy += (dy / d) * f;
    }
    for (const n of nodes) {
      const p = pos.get(n.id);
      p.vx += (W / 2 - p.x) * 0.002; p.vy += (H / 2 - p.y) * 0.002;
      p.x = Math.min(W - 40, Math.max(40, p.x + Math.max(-10, Math.min(10, p.vx)) * t));
      p.y = Math.min(H - 30, Math.max(30, p.y + Math.max(-10, Math.min(10, p.vy)) * t));
      p.vx *= 0.5; p.vy *= 0.5;
    }
  }
  return pos;
}

export default function GraphPage() {
  const [params, setParams] = useSearchParams();
  const [companies, setCompanies] = useState([]);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [hover, setHover] = useState(null);
  const selected = params.get('company') || 'all';

  useEffect(() => { api.get('/companies').then(setCompanies).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    setData(null);
    api.get(`/companies/${selected}/graph`).then(setData).catch((e) => setError(e.message));
  }, [selected]);

  const W = 820; const H = 520;
  const pos = useMemo(() => (data ? layout(data.nodes, data.edges, W, H) : null), [data]);

  const highlight = useMemo(() => {
    const s = new Set();
    if (!data) return s;
    data.analysis.suspicious_rings.forEach((r) => r.members.forEach((m) => s.add(m)));
    data.analysis.guarantee_cycles.forEach((c) => c.forEach((m) => s.add(m)));
    data.analysis.fund_cycles.forEach((c) => c.forEach((m) => s.add(m)));
    return s;
  }, [data]);

  const a = data?.analysis;
  return (
    <>
      <PageHeader title="关联图谱 · 图计算反欺诈" desc="连通分量识别团伙；有向环检测识别担保圈与资金闭环；度中心性定位关键节点">
        <select className="select" value={selected} onChange={(e) => setParams({ company: e.target.value })}>
          <option value="all">全部企业</option>
          {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </PageHeader>
      <ErrorBox error={error} />
      <div className="grid-graph">
        <Card title={`关系网络（${data?.nodes.length || 0} 节点 / ${data?.edges.length || 0} 边）`}
          extra={<div className="legend">{Object.entries(TYPE_STYLE).map(([k, v]) => <span key={k}><i style={{ background: v.color }} />{v.label}</span>)}</div>}>
          {data && pos ? (
            <svg viewBox={`0 0 ${W} ${H}`} className="graph-svg">
              <defs>
                {Object.entries(REL_COLOR).map(([k, c]) => (
                  <marker key={k} id={`arrow-${k}`} viewBox="0 0 10 10" refX="22" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={c} />
                  </marker>
                ))}
              </defs>
              {data.edges.map((e, i) => {
                const s = pos.get(e.source); const t = pos.get(e.target);
                const on = hover && (hover === e.source || hover === e.target);
                return (
                  <g key={i} opacity={hover && !on ? 0.15 : 1}>
                    <line x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke={REL_COLOR[e.relation] || '#94a3b8'} strokeWidth={e.relation === '使用' ? 1.2 : 2}
                      markerEnd={e.directed ? `url(#arrow-${e.relation})` : undefined} strokeDasharray={e.relation === '实控' ? '4 3' : undefined} />
                    {e.relation !== '使用' && <text x={(s.x + t.x) / 2} y={(s.y + t.y) / 2 - 3} className="edge-label" fill={REL_COLOR[e.relation]}>{e.relation}{e.amount ? ` ${e.amount}` : ''}</text>}
                  </g>
                );
              })}
              {data.nodes.map((n) => {
                const p = pos.get(n.id); const st = TYPE_STYLE[n.type] || TYPE_STYLE.account;
                return (
                  <g key={n.id} transform={`translate(${p.x},${p.y})`} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)} className="node">
                    {highlight.has(n.id) && <circle r={st.r + 6} fill="none" stroke="#ef4444" strokeWidth="2" strokeDasharray="3 2" />}
                    <circle r={st.r} fill={st.color} stroke="#fff" strokeWidth="2" />
                    <text y={st.r + 13} textAnchor="middle" className="node-label">{n.id.length > 8 ? `${n.id.slice(0, 8)}…` : n.id}</text>
                  </g>
                );
              })}
            </svg>
          ) : <Empty text="加载中…" />}
          <div className="muted small">红色虚线圈：处于可疑团伙 / 担保圈 / 资金闭环中的节点。悬停节点可高亮其关系。</div>
        </Card>

        <div className="col">
          <Card title="图计算结论">
            {a ? (
              <>
                <div className="flag-row">
                  {[['fraud_ring', '设备共用团伙'], ['guarantee_circle', '循环担保圈'], ['fund_loop', '资金闭环'], ['fund_collector', '资金汇集']].map(([k, label]) => (
                    <span key={k} className={`tag ${a.risk_flags[k] ? 'red' : 'green'}`}>{label}：{a.risk_flags[k] ? '发现' : '无'}</span>
                  ))}
                </div>
                <h4>可疑团伙（连通分量 ≥ 3）</h4>
                {a.suspicious_rings.length ? a.suspicious_rings.map((r, i) => (
                  <div key={i} className="kb-item">团伙 {i + 1}（{r.size} 个节点，共用介质：{r.shared_media.join('、')}）<br /><span className="muted small">{r.members.join('、')}</span></div>
                )) : <div className="muted">无</div>}
                <h4>担保圈</h4>
                {a.guarantee_cycles.length ? a.guarantee_cycles.map((c, i) => <div key={i} className="kb-item">{c.join(' → ')}</div>) : <div className="muted">无</div>}
                <h4>资金闭环</h4>
                {a.fund_cycles.length ? a.fund_cycles.map((c, i) => <div key={i} className="kb-item">{c.join(' → ')}</div>) : <div className="muted">无</div>}
                <h4>隐性实控人</h4>
                {a.hidden_controllers.length ? a.hidden_controllers.map((h) => <div key={h.person} className="kb-item"><b>{h.person}</b> 实控：{h.companies.join('、')}</div>) : <div className="muted">无</div>}
                <h4>资金汇集账户</h4>
                {a.fund_collectors.length ? a.fund_collectors.map((f) => <div key={f.account} className="kb-item"><b>{f.account}</b> ← {f.sources.join('、')}</div>) : <div className="muted">无</div>}
              </>
            ) : <Empty text="加载中…" />}
          </Card>
          <Card title="度中心性 Top 5">
            {a && (
              <table className="table">
                <thead><tr><th>节点</th><th>类型</th><th>度</th></tr></thead>
                <tbody>{a.top_degree.map((d) => <tr key={d.id}><td>{d.id}</td><td>{TYPE_STYLE[d.type]?.label}</td><td>{d.degree}</td></tr>)}</tbody>
              </table>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
