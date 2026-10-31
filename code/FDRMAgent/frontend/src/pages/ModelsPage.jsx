import { useEffect, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, pct } from '../api.js';
import { Card, PageHeader, ErrorBox, Empty } from '../components/ui.jsx';

const ksTone = (l) => ({ 较好: 'green', 可用: 'blue', 偏弱: 'orange' }[l] || 'gray');
const psiTone = (l) => (l === '稳定' ? 'green' : l.startsWith('有变化') ? 'orange' : 'red');

export default function ModelsPage() {
  const [card, setCard] = useState([]);
  const [models, setModels] = useState([]);
  const [sel, setSel] = useState('scorecard_v1');
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([api.get('/scorecard'), api.get('/models')]).then(([c, m]) => { setCard(c); setModels(m); }).catch((e) => setError(e.message));
  }, []);

  const m = models.find((x) => x.name === sel);
  const psiBins = m?.metrics ? m.metrics.psi_bins.expected.map((e, i) => ({ bin: `${i + 1}`, 开发样本: +(e * 100).toFixed(1), 时间外样本: +(m.metrics.psi_bins.actual[i] * 100).toFixed(1) })) : [];

  return (
    <>
      <PageHeader title="评分卡与模型管理" desc="WOE 分箱 + 逻辑回归评分卡；AUC / KS 评区分能力，PSI 评稳定性；OOT 时间外样本验证" />
      <ErrorBox error={error} />

      <Card title="模型注册表">
        <table className="table">
          <thead><tr><th>模型</th><th>算法</th><th>版本</th><th>状态</th><th>OOT AUC</th><th>OOT KS</th><th>PSI</th><th>说明</th></tr></thead>
          <tbody>
            {models.map((x) => (
              <tr key={x.name} className={x.name === sel ? 'row-selected' : ''} onClick={() => x.metrics && setSel(x.name)} style={{ cursor: x.metrics ? 'pointer' : 'default' }}>
                <td className="strong">{x.display_name}</td><td>{x.algorithm}</td><td>{x.version}</td>
                <td><span className={`tag ${x.status === '在线' ? 'green' : 'blue'}`}>{x.status}</span></td>
                <td>{x.metrics?.oot_auc ?? '-'}</td>
                <td>{x.metrics ? <span className={`tag ${ksTone(x.metrics.ks_level)}`}>{x.metrics.oot_ks} {x.metrics.ks_level}</span> : '-'}</td>
                <td>{x.metrics ? <span className={`tag ${psiTone(x.metrics.psi_level)}`}>{x.metrics.psi} {x.metrics.psi_level}</span> : '-'}</td>
                <td className="small muted">{x.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="muted small">点击有指标的模型行查看 ROC 与 PSI 分布。打分样本为模拟数据（违约率约 22%，对应 UCI 信用卡数据集）。</div>
      </Card>

      {m?.metrics && (
        <div className="grid-2">
          <Card title={`${m.display_name} · OOT ROC 曲线（AUC ${m.metrics.oot_auc}）`}>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={m.metrics.roc_oot}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="fpr" type="number" domain={[0, 1]} fontSize={12} label={{ value: 'FPR', position: 'insideBottom', offset: -2, fontSize: 12 }} />
                <YAxis dataKey="tpr" type="number" domain={[0, 1]} fontSize={12} />
                <Tooltip />
                <Line dataKey="tpr" stroke="#3b82f6" dot={false} strokeWidth={2} />
                <Line data={[{ fpr: 0, tpr: 0 }, { fpr: 1, tpr: 1 }]} dataKey="tpr" stroke="#cbd5e1" dot={false} strokeDasharray="4 4" />
              </LineChart>
            </ResponsiveContainer>
            <div className="muted small">开发样本 AUC {m.metrics.dev_auc} / KS {m.metrics.dev_ks}；时间外样本 AUC {m.metrics.oot_auc} / KS {m.metrics.oot_ks}</div>
          </Card>
          <Card title={`分数分布稳定性 PSI = ${m.metrics.psi}（${m.metrics.psi_level}）`}>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={psiBins}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
                <XAxis dataKey="bin" fontSize={12} label={{ value: '分数十分位', position: 'insideBottom', offset: -2, fontSize: 12 }} />
                <YAxis unit="%" fontSize={12} />
                <Tooltip /><Legend />
                <Bar dataKey="开发样本" fill="#93c5fd" />
                <Bar dataKey="时间外样本" fill="#f97316" />
              </BarChart>
            </ResponsiveContainer>
            <div className="muted small">PSI &lt; 0.1 稳定；0.1 ~ 0.25 关注；&gt; 0.25 显著漂移需重训</div>
          </Card>
        </div>
      )}

      <Card title="评分卡分箱（WOE / IV）" extra={<span className="muted small">Score = A − B·ln(p/(1−p))，600 分 ↔ 好坏比 20:1，PDO = 50</span>}>
        {card.length ? (
          <div className="scorecard-grid">
            {card.map((v) => (
              <div key={v.variable} className="sc-var">
                <div className="sc-head"><b>{v.variable_cn}</b><span className="tag blue">IV {v.iv} · {v.iv_level}</span></div>
                <table className="table compact">
                  <thead><tr><th>分箱</th><th>好</th><th>坏</th><th>好占比</th><th>坏占比</th><th>WOE</th><th>分值</th></tr></thead>
                  <tbody>
                    {v.bins.map((b) => (
                      <tr key={b.label}>
                        <td>{b.label}</td><td>{b.good}</td><td>{b.bad}</td><td>{pct(b.good_pct, 1)}</td><td>{pct(b.bad_pct, 1)}</td>
                        <td className={b.woe < 0 ? 'neg' : 'pos'}>{b.woe.toFixed(2)}</td>
                        <td className={b.points < 0 ? 'neg' : 'pos'}>{b.points > 0 ? `+${b.points}` : b.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        ) : <Empty />}
      </Card>
    </>
  );
}
