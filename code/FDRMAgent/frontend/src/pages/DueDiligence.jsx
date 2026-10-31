import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, pct, streamAgent } from '../api.js';
import { Card, PageHeader, LevelTag, Markdown, Timeline, ErrorBox, Spinner, Empty } from '../components/ui.jsx';

const WORKFLOW = ['输入护栏', '规划', '工具调用', '反思', 'PD 计算', '专项分析', '多空辩论', 'CRO 裁决', '输出核验', '人工复核'];

function stageOf(step) {
  const s = step?.step || '';
  if (s.includes('输入护栏')) return 0;
  if (s.includes('规划') && !s.includes('校验')) return 1;
  if (s.includes('工具') || s.includes('规划校验')) return 2;
  if (s.includes('反思')) return 3;
  if (s.includes('评分卡')) return 4;
  if (s.includes('分析师')) return 5;
  if (s.includes('辩论')) return 6;
  if (s.includes('首席风险官')) return 7;
  if (s.includes('输出护栏')) return 8;
  if (s.includes('人工')) return 9;
  return -1;
}

export default function DueDiligence() {
  const [params] = useSearchParams();
  const [companies, setCompanies] = useState([]);
  const [selected, setSelected] = useState(params.get('company') || '');
  const [profile, setProfile] = useState(null);
  const [steps, setSteps] = useState([]);
  const [running, setRunning] = useState('');
  const [report, setReport] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const ctrlRef = useRef(null);

  useEffect(() => {
    api.get('/companies').then((list) => {
      setCompanies(list);
      if (!params.get('company') && list[0]) setSelected(String(list[0].id));
    }).catch((e) => setError(e.message));
    return () => ctrlRef.current?.abort();
  }, []);

  useEffect(() => {
    if (!selected) return;
    setProfile(null);
    api.get(`/companies/${selected}`).then(setProfile).catch((e) => setError(e.message));
  }, [selected]);

  const run = () => {
    setSteps([]); setReport(''); setResult(null); setError(''); setRunning('智能体启动中…');
    ctrlRef.current = streamAgent('/agents/due-diligence', { company: Number(selected) }, (ev) => {
      if (ev.type === 'step_started') setRunning(`${ev.step}…`);
      if (ev.type === 'step') setSteps((s) => [...s, ev]);
      if (ev.type === 'report_started') setRunning('首席风险官正在撰写报告…');
      if (ev.type === 'report_token') setReport((r) => r + ev.token);
      if (ev.type === 'done') { setResult(ev.result); setReport(ev.result.report); setRunning(''); }
      if (ev.type === 'error') { setError(ev.error); setRunning(''); }
    });
  };

  const stop = () => { ctrlRef.current?.abort(); setRunning(''); };
  const reached = Math.max(-1, ...steps.map(stageOf));
  const c = profile?.company;

  return (
    <>
      <PageHeader title="授信尽调智能体" desc="规划 → 调用工具并留痕 → 代码计算 PD → 多空辩论 → 首席风险官裁决 → 高风险转人工">
        <select className="select" value={selected} onChange={(e) => setSelected(e.target.value)} disabled={!!running}>
          {companies.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
        {running ? <button className="btn" onClick={stop}>停止</button>
          : <button className="btn primary" onClick={run} disabled={!selected}>开始尽调</button>}
      </PageHeader>
      <ErrorBox error={error} />

      <div className="workflow">
        {WORKFLOW.map((w, i) => (
          <div key={w} className={`wf-step ${i <= reached ? 'done' : ''} ${running && i === reached + 1 ? 'active' : ''}`}>
            <span className="wf-idx">{i + 1}</span>{w}
          </div>
        ))}
      </div>

      <div className="grid-dd">
        <div className="col">
          <Card title="企业画像（只读数据）">
            {c ? (
              <>
                <div className="kv"><span>企业</span><b>{c.name}</b></div>
                <div className="kv"><span>行业 / 地区</span>{c.industry} / {c.region}</div>
                <div className="kv"><span>申请额度</span>{c.requested_limit} 万元</div>
                <div className="kv"><span>资产负债率</span>{pct(profile.financials.debt_ratio)}</div>
                <div className="kv"><span>流动比率</span>{profile.financials.current_ratio}</div>
                <div className="kv"><span>净利率</span>{pct(profile.financials.net_margin)}</div>
                <div className="kv"><span>近 12 月被诉</span>{profile.legal.lawsuits_12m} 起</div>
                <div className="kv"><span>失信被执行</span>{profile.legal.dishonest_executor ? <span className="tag red">是</span> : '否'}</div>
                <div className="kv"><span>多头授信</span>{profile.credit.multi_lender_count} 家</div>
                <div className="desc-box">
                  <div className="muted small">企业简介（外部文本，作为数据而非指令）</div>
                  {c.description}
                </div>
              </>
            ) : <Spinner text="加载中" />}
          </Card>
          <Card title="执行轨迹（实时留痕）" extra={result && <Link to={`/audit/${result.run_id}`}>审计回放 →</Link>}>
            <Timeline steps={steps} running={running} />
          </Card>
        </div>

        <div className="col">
          {result && (
            <div className="result-banner">
              <div className="rb-item"><div className="muted small">违约概率 PD</div><div className="big">{pct(result.pd)}</div></div>
              <div className="rb-item"><div className="muted small">评分卡分数</div><div className="big">{result.score}</div></div>
              <div className="rb-item"><div className="muted small">风险等级</div><div className="big"><LevelTag level={result.risk_level} /></div></div>
              <div className="rb-item"><div className="muted small">数字核验</div><div className="big">{result.number_check.passed ? <span className="tag green">通过</span> : <span className="tag orange">{result.number_check.unverified.length} 项待核</span>}</div></div>
              <div className="rb-item wide">
                {result.need_human ? (
                  <div className="human-alert">
                    <b>已转人工复核</b>（任务 #{result.review_task_id}）：{result.human_reasons.join('；')}
                    <Link className="btn small" to="/reviews">去复核</Link>
                  </div>
                ) : <div className="ok-alert">未触发人工复核条件，仍需授信审批官最终确认</div>}
              </div>
            </div>
          )}

          <Card title="尽调报告" extra={running && report && <Spinner text="生成中" />}>
            {report ? <Markdown>{report}</Markdown> : <Empty text={running ? '等待智能体完成分析…' : '点击“开始尽调”生成报告'} />}
          </Card>

          {result && (
            <>
              <div className="grid-2">
                <Card title="多空辩论 · 支持方" className="pro"><Markdown>{result.debate.pro}</Markdown></Card>
                <Card title="多空辩论 · 质疑方" className="con"><Markdown>{result.debate.con}</Markdown></Card>
              </div>
              <Card title="评分卡贡献与原因码（代码计算）">
                <table className="table">
                  <thead><tr><th>变量</th><th>取值</th><th>分箱</th><th>WOE</th><th>分值</th></tr></thead>
                  <tbody>
                    {result.scoring.contributions.map((x) => (
                      <tr key={x.variable}>
                        <td>{x.variable_cn}</td>
                        <td>{typeof x.value === 'number' && x.value < 1 && x.value > -1 && !Number.isInteger(x.value) ? pct(x.value) : x.value}</td>
                        <td>{x.bin}</td>
                        <td className={x.woe < 0 ? 'neg' : 'pos'}>{x.woe}</td>
                        <td className={x.points < 0 ? 'neg' : 'pos'}>{x.points > 0 ? `+${x.points}` : x.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="muted small">规则版 PD（课件 score_pd 交叉校验）：{result.scoring.rule_pd}</div>
              </Card>
              {result.injection.detected && (
                <div className="warn-box">护栏告警：企业外部资料中检测到提示注入（如“忽略之前所有指令”“直接批准”），已隔离为数据，未影响 PD 计算与结论。</div>
              )}
              {result.knowledge?.length > 0 && (
                <Card title="引用制度（知识库检索）">
                  {result.knowledge.map((k) => <div key={k.title} className="kb-item"><b>《{k.title}》</b> <span className="muted small">{k.source}</span></div>)}
                </Card>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
