import { useEffect, useState } from 'react';
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ReferenceLine, Cell } from 'recharts';
import { api, fmtTime } from '../api.js';
import { Card, PageHeader, ErrorBox, Stat, Empty } from '../components/ui.jsx';

export default function AnomalyPage() {
  const [companies, setCompanies] = useState([]);
  const [companyId, setCompanyId] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { api.get('/companies').then(setCompanies).catch((e) => setError(e.message)); }, []);
  useEffect(() => {
    setData(null);
    api.get(`/anomalies${companyId ? `?company_id=${companyId}` : ''}`).then(setData).catch((e) => setError(e.message));
  }, [companyId]);

  const points = data?.items.map((i) => ({ x: Math.log10(i.amount), y: i.anomaly_score, ...i })) || [];

  return (
    <>
      <PageHeader title="异常检测 · 孤立森林" desc="没有“坏样本”时：用正常样本训练，给新交易打异常分；再叠加业务规则。异常 ≠ 欺诈，只是线索。">
        <select className="select" value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
          <option value="">全部企业</option>
          {companies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </PageHeader>
      <ErrorBox error={error} />
      {data ? (
        <>
          <div className="stats">
            <Stat label="训练样本（正常）" value={data.train_size} sub="contamination = 0.01" />
            <Stat label="待检交易" value={data.total} />
            <Stat label="异常（分数 ≥ 阈值）" value={data.anomaly_count} sub={`阈值 ${data.threshold}`} tone={data.anomaly_count ? 'red' : ''} />
            <Stat label="命中业务规则" value={data.rule_hit_count} tone={data.rule_hit_count ? 'orange' : ''} />
          </div>
          <div className="grid-2">
            <Card title="异常分分布（横轴：log10 金额）">
              <ResponsiveContainer width="100%" height={280}>
                <ScatterChart margin={{ top: 10, right: 10, bottom: 10, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                  <XAxis type="number" dataKey="x" name="log10 金额" domain={['auto', 'auto']} fontSize={12} />
                  <YAxis type="number" dataKey="y" name="异常分" domain={[0.3, 0.85]} fontSize={12} />
                  <ReferenceLine y={data.threshold} stroke="#ef4444" strokeDasharray="4 4" label={{ value: '阈值', fill: '#ef4444', fontSize: 12 }} />
                  <Tooltip content={({ payload }) => payload?.[0] ? (
                    <div className="tooltip">{payload[0].payload.account}<br />金额 {payload[0].payload.amount} 元 · {payload[0].payload.txn_hour} 点<br />异常分 {payload[0].payload.anomaly_score}</div>
                  ) : null} />
                  <Scatter data={points}>
                    {points.map((p) => <Cell key={p.id} fill={p.is_anomaly ? '#ef4444' : p.rule_hits.length ? '#f59e0b' : '#3b82f6'} />)}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </Card>
            <Card title="模型说明">
              <div className="kv"><span>模型</span>{data.model}</div>
              <div className="kv"><span>特征</span>{data.features.map((f) => f.name).join('、')}</div>
              <div className="kv"><span>异常分</span>2^(−E[h(x)]/c(n))，越接近 1 越异常</div>
              <div className="kv"><span>业务规则</span>同设备 1 小时申请 &gt; 5 次、凌晨交易、单笔 ≥ 20 万、24 小时对手 ≥ 8 个</div>
              <div className="warn-box">{data.note}</div>
            </Card>
          </div>
          <Card title="交易明细（按异常分降序）">
            {data.items.length ? (
              <table className="table">
                <thead><tr><th>账户</th><th>企业</th><th>金额(元)</th><th>时段</th><th>1h 申请</th><th>24h 对手</th><th>新设备</th><th>异常分</th><th>规则命中</th><th>时间</th></tr></thead>
                <tbody>
                  {data.items.map((i) => (
                    <tr key={i.id} className={i.is_anomaly ? 'row-alert' : ''}>
                      <td>{i.account}</td><td className="ellipsis">{i.company}</td><td>{i.amount.toLocaleString()}</td><td>{i.txn_hour}:00</td>
                      <td>{i.apply_count_1h}</td><td>{i.counterparties_24h}</td><td>{i.is_new_device ? '是' : '否'}</td>
                      <td><b className={i.is_anomaly ? 'neg' : ''}>{i.anomaly_score}</b></td>
                      <td>{i.rule_hits.map((r) => <span key={r} className="tag orange">{r}</span>)}</td>
                      <td className="small">{fmtTime(i.occurred_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty />}
          </Card>
        </>
      ) : <div className="muted">加载中…</div>}
    </>
  );
}
