import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts';
import { api, pct, fmtTime, AGENT_NAMES } from '../api.js';
import { Card, PageHeader, Stat, LevelTag, StatusTag, Empty, ErrorBox } from '../components/ui.jsx';

const LEVEL_COLORS = { 高: '#ef4444', 中: '#f59e0b', 低: '#22c55e' };

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.get('/dashboard'), api.get('/companies')])
      .then(([d, c]) => { setData(d); setCompanies(c); })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <ErrorBox error={`${error}。请确认后端已启动并执行过 npm run db:init。`} />;
  if (!data) return <div className="muted">加载中…</div>;
  const { counts } = data;
  const pdData = companies.filter((c) => c.pd !== null).map((c) => ({ name: c.name.slice(0, 4), pd: Number((c.pd * 100).toFixed(2)) }));

  return (
    <>
      <PageHeader title="风险驾驶舱" desc="贷前准入 → 贷中监控 → 贷后处置 → 复盘迭代：风控闭环全景">
        <Link className="btn primary" to="/due-diligence">发起授信尽调</Link>
        <Link className="btn" to="/early-warning">运行预警扫描</Link>
      </PageHeader>

      <div className="stats">
        <Stat label="监控企业" value={counts.companies} sub="对公授信客户" />
        <Stat label="未关闭预警" value={counts.open_alerts} sub="高 / 中 / 低" tone={counts.open_alerts ? 'red' : ''} />
        <Stat label="待人工复核" value={counts.pending_reviews} sub="人在回路" tone={counts.pending_reviews ? 'orange' : ''} />
        <Stat label="智能体运行" value={counts.runs} sub={`审计日志 ${counts.audit_logs} 条`} />
      </div>

      <div className="grid-2">
        <Card title="企业最新 PD（%）" extra={<span className="muted small">红线：人工复核阈值 5%</span>}>
          {pdData.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={pdData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="name" fontSize={12} />
                <YAxis fontSize={12} />
                <Tooltip formatter={(v) => `${v}%`} />
                <ReferenceLine y={5} stroke="#ef4444" strokeDasharray="4 4" />
                <Bar dataKey="pd" radius={[4, 4, 0, 0]}>
                  {pdData.map((d) => <Cell key={d.name} fill={d.pd >= 10 ? '#ef4444' : d.pd >= 5 ? '#f97316' : '#3b82f6'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <Empty text="尚无尽调结果，去“授信尽调”运行一次吧" />}
        </Card>
        <Card title="未关闭预警等级分布">
          {data.alertsByLevel.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={data.alertsByLevel} dataKey="n" nameKey="level" innerRadius={55} outerRadius={90} label={(e) => `${e.level} ${e.n}`}>
                  {data.alertsByLevel.map((d) => <Cell key={d.level} fill={LEVEL_COLORS[d.level] || '#94a3b8'} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : <Empty text="暂无预警，去“风险预警”运行扫描" />}
        </Card>
      </div>

      <Card title="客户风险清单">
        <table className="table">
          <thead><tr><th>企业</th><th>行业</th><th>地区</th><th>申请额度(万元)</th><th>最新 PD</th><th>评分</th><th>等级</th><th>未关闭预警</th><th /></tr></thead>
          <tbody>
            {companies.map((c) => (
              <tr key={c.id}>
                <td className="strong">{c.name}</td>
                <td>{c.industry}</td>
                <td>{c.region}</td>
                <td>{c.requested_limit}</td>
                <td>{pct(c.pd)}</td>
                <td>{c.score ?? '-'}</td>
                <td><LevelTag level={c.risk_level} /></td>
                <td>{c.open_alerts ? <span className="tag red">{c.open_alerts}</span> : '-'}</td>
                <td><Link to={`/due-diligence?company=${c.id}`}>尽调</Link> · <Link to={`/graph?company=${c.id}`}>图谱</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="最近智能体运行" extra={<Link to="/audit">全部 →</Link>}>
        {data.recentRuns.length ? (
          <table className="table">
            <thead><tr><th>智能体</th><th>对象</th><th>状态</th><th>PD</th><th>模型</th><th>开始时间</th><th /></tr></thead>
            <tbody>
              {data.recentRuns.map((r) => (
                <tr key={r.id}>
                  <td>{AGENT_NAMES[r.agent]}</td>
                  <td className="ellipsis">{r.target}</td>
                  <td><StatusTag status={r.status} /></td>
                  <td>{pct(r.pd)}</td>
                  <td><span className={`tag ${r.llm_mode === 'deepseek' ? 'blue' : 'gray'}`}>{r.llm_mode}</span></td>
                  <td>{fmtTime(r.started_at)}</td>
                  <td><Link to={`/audit/${r.id}`}>回放</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty />}
      </Card>
    </>
  );
}
