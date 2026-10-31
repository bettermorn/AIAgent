import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api, pct, fmtTime, AGENT_NAMES } from '../api.js';
import { Card, PageHeader, StatusTag, Timeline, ErrorBox, Empty } from '../components/ui.jsx';

export default function Audit() {
  const { runId } = useParams();
  const nav = useNavigate();
  const [runs, setRuns] = useState([]);
  const [agent, setAgent] = useState('');
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get(`/runs?limit=100${agent ? `&agent=${agent}` : ''}`).then(setRuns).catch((e) => setError(e.message));
  }, [agent]);

  useEffect(() => {
    if (!runId) { setDetail(null); return; }
    api.get(`/runs/${runId}`).then(setDetail).catch((e) => setError(e.message));
  }, [runId]);

  const run = detail?.run;
  return (
    <>
      <PageHeader title="审计留痕与回放" desc="每次运行的规划、工具调用、计算、模型输出、护栏判定、人工决定，均按序记录，可追溯、可复现">
        <select className="select" value={agent} onChange={(e) => setAgent(e.target.value)}>
          <option value="">全部智能体</option>
          {Object.entries(AGENT_NAMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </PageHeader>
      <ErrorBox error={error} />
      <div className="grid-review">
        <Card title={`运行记录（${runs.length}）`}>
          {runs.length ? runs.map((r) => (
            <div key={r.id} className={`alert-item ${r.id === runId ? 'selected' : ''}`} onClick={() => nav(`/audit/${r.id}`)}>
              <div className="ai-head"><StatusTag status={r.status} /><span className={`tag ${r.llm_mode === 'deepseek' ? 'blue' : 'gray'}`}>{r.llm_mode}</span><span className="muted small">{r.steps} 步</span></div>
              <div className="ai-title">{AGENT_NAMES[r.agent]} · {r.target}</div>
              <div className="muted small">{fmtTime(r.started_at)}{r.pd !== null ? ` · PD ${pct(r.pd)}` : ''}</div>
            </div>
          )) : <Empty />}
        </Card>
        <div className="col">
          {run ? (
            <>
              <Card title="运行概要">
                <div className="kv"><span>运行 ID</span><code>{run.id}</code></div>
                <div className="kv"><span>智能体</span>{AGENT_NAMES[run.agent]}</div>
                <div className="kv"><span>目标</span>{run.goal}</div>
                <div className="kv"><span>模型</span>{run.llm_model}（{run.llm_mode}）</div>
                <div className="kv"><span>状态</span><StatusTag status={run.status} />{run.error && <span className="neg"> {run.error}</span>}</div>
                <div className="kv"><span>耗时</span>{run.finished_at ? `${((new Date(run.finished_at) - new Date(run.started_at)) / 1000).toFixed(1)} 秒` : '-'}</div>
                {run.pd !== null && <div className="kv"><span>PD / 评分</span>{pct(run.pd)} / {run.score}（{run.risk_level}）</div>}
                {run.company_id && <div className="kv"><span>相关操作</span><Link to={`/due-diligence?company=${run.company_id}`}>重新尽调</Link></div>}
              </Card>
              <Card title={`执行轨迹（${detail.logs.length} 步）`}><Timeline steps={detail.logs} /></Card>
            </>
          ) : <Card><Empty text="选择左侧运行记录进行回放" /></Card>}
        </div>
      </div>
    </>
  );
}
