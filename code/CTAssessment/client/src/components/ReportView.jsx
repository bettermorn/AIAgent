import React, { useEffect, useState } from 'react';
import { api } from '../api.js';

const DIM_INFO = {
  decomposition: { name: '分解问题', max: 20 },
  pattern: { name: '模式识别', max: 13 },
  abstraction: { name: '抽象', max: 16 },
  algorithm: { name: '算法设计', max: 16 },
  comprehensive: { name: '综合开放题', max: 12 },
  ai: { name: '人工智能问题', max: 8 },
};

const SELF_MAX = 25;

function LevelTag({ level }) {
  const cls = { '较强': 'tag-strong', '良好': 'tag-good', '中等': 'tag-mid', '需要加强': 'tag-weak' }[level] || 'tag-mid';
  return <span className={`level-tag ${cls}`}>{level}</span>;
}

function ScoreBar({ label, score, max, suffix }) {
  const pct = Math.min(100, Math.round((score / max) * 100));
  const color = pct >= 70 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
  return (
    <div className="score-row">
      <div className="score-label">{label}</div>
      <div className="score-track">
        <div className="score-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="score-value">{score}<span className="score-max">/{max}{suffix}</span></div>
    </div>
  );
}

export default function ReportView({ result, onRestart }) {
  // 统一数据结构：新提交结果 或 历史记录
  const data = result.id && result.taskResult ? {
    id: result.id,
    student: '',
    self: result.selfResult,
    task: result.taskResult,
    conclusion: result.conclusion,
    advice: null,
  } : {
    id: result.id,
    student: `${result.student_name}（${result.grade}）`,
    self: { scores: result.self_scores, levels: result.self_levels },
    task: {
      detail: result.task_detail,
      dimensionScores: result.dimension_scores,
      percentage: Number(result.percentage),
      level: { level: result.level },
      dimensionComments: result.test_scores?.dimensionComments || {},
      strengths: result.test_scores?.strengths || [],
      weaknesses: result.test_scores?.weaknesses || [],
      total: Number(result.total_score),
    },
    conclusion: result.conclusion,
    advice: result.advice,
  };

  const [advice, setAdvice] = useState(data.advice);
  const [adviceLoading, setAdviceLoading] = useState(false);
  const [adviceError, setAdviceError] = useState('');
  const [showDetail, setShowDetail] = useState(false);

  useEffect(() => { window.scrollTo(0, 0); }, [result.id]);

  async function fetchAdvice() {
    setAdviceLoading(true);
    setAdviceError('');
    try {
      const a = await api.getAdvice(data.id);
      setAdvice(a);
    } catch (e) {
      setAdviceError(e.message);
    } finally {
      setAdviceLoading(false);
    }
  }

  const taskDetail = data.task.detail || {};

  return (
    <div className="report">
      {/* 总览 */}
      <div className="panel report-hero">
        <div className="report-hero-main">
          <h2>测评报告{data.student && <span className="report-student"> · {data.student}</span>}</h2>
          <LevelTag level={data.task.level.level} />
          <div className="total-score">
            <span className="total-num">{data.task.percentage}</span>
            <span className="total-unit">分（百分制）</span>
          </div>
          <p className="total-desc">
            情境测试原始分 {data.task.total ?? '--'}/85 · {data.task.level.level}
            {data.task.level.desc ? ` —— ${data.task.level.desc}` : ''}
          </p>
        </div>
      </div>

      {/* 维度得分 */}
      <div className="panel">
        <h3 className="section-title">维度得分</h3>
        <div className="dim-grid">
          {Object.entries(DIM_INFO).map(([key, info]) => (
            <div className="dim-card" key={key}>
              <div className="dim-card-head">
                <strong>{info.name}</strong>
                <span>{data.task.dimensionScores?.[key] ?? 0}/{info.max}</span>
              </div>
              <div className="dim-bar">
                <div
                  className="dim-fill"
                  style={{
                    width: `${Math.min(100, ((data.task.dimensionScores?.[key] ?? 0) / info.max) * 100)}%`,
                    background: (data.task.dimensionScores?.[key] ?? 0) / info.max >= 0.7 ? '#10b981' : (data.task.dimensionScores?.[key] ?? 0) / info.max >= 0.5 ? '#f59e0b' : '#ef4444',
                  }}
                />
              </div>
              {data.task.dimensionComments?.[key] && (
                <p className="dim-comment">{data.task.dimensionComments[key]}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 自评 vs 实测 */}
      <div className="panel">
        <h3 className="section-title">自评量表结果（各维度满分 25）</h3>
        {Object.entries(DIM_INFO).slice(0, 4).map(([key, info]) => (
          <ScoreBar key={key} label={info.name} score={data.self.scores?.[key] ?? 0} max={SELF_MAX} />
        ))}
        <p className="hint">
          自评反映主观感受，实际任务得分更能反映计算思维水平。对比两者：自评明显偏高说明可能高估自己，明显偏低说明可能缺乏自信。
        </p>
      </div>

      {/* 评价结论 */}
      <div className="panel">
        <h3 className="section-title">📝 评价结论</h3>
        <div className="conclusion-text">{data.conclusion}</div>
        {(data.task.strengths?.length > 0 || data.task.weaknesses?.length > 0) && (
          <div className="sw-grid">
            {data.task.strengths?.length > 0 && (
              <div className="sw-box strengths">
                <h4>✅ 优势</h4>
                <ul>{data.task.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>
            )}
            {data.task.weaknesses?.length > 0 && (
              <div className="sw-box weaknesses">
                <h4>🎯 待提升</h4>
                <ul>{data.task.weaknesses.map((s, i) => <li key={i}>{s}</li>)}</ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 逐题明细 */}
      <div className="panel">
        <button className="collapsible" onClick={() => setShowDetail(!showDetail)}>
          {showDetail ? '▼ 收起逐题评分明细' : '▶ 展开逐题评分明细'}
        </button>
        {showDetail && (
          <div className="task-detail-list">
            {Object.values(taskDetail).sort((a, b) => a.no - b.no).map((d) => (
              <div className="task-detail-item" key={d.no}>
                <div className="task-detail-head">
                  <span>第 {d.no} 题 · {d.title}</span>
                  <span className="task-detail-score">{d.score}/{d.maxScore} 分</span>
                </div>
                {d.comment && <p className="task-detail-comment">{d.comment}</p>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 学习建议 */}
      <div className="panel advice-panel">
        <h3 className="section-title">📚 个性化学习建议</h3>
        {!advice && !adviceLoading && (
          <div className="advice-empty">
            <p>AI 智能体将结合《用不同语言训练计算思维》《日常任务练习计算思维》知识库，并搜索互联网学习资源，为你的薄弱维度生成学习建议。</p>
            <button className="btn-primary btn-lg" onClick={fetchAdvice}>生成学习建议 →</button>
          </div>
        )}
        {adviceLoading && (
          <div className="loading-box inline">
            <div className="spinner" />
            <p>正在检索学习资源并生成建议…（约 1—2 分钟）</p>
          </div>
        )}
        {adviceError && <div className="error-text">生成失败：{adviceError} <button className="btn-link" onClick={fetchAdvice}>重试</button></div>}

        {advice && !adviceLoading && (
          <div className="advice-content">
            {advice.overall && (
              <div className="advice-block">
                <h4>总体建议</h4>
                <p>{advice.overall}</p>
              </div>
            )}
            {advice.dimensionAdvice?.map((d, i) => (
              <div className="advice-block dim-advice" key={i}>
                <h4>
                  {d.dimensionName}
                  <span className={`priority-tag p-${d.priority === '高' ? 'high' : d.priority === '中' ? 'mid' : 'low'}`}>{d.priority}优先</span>
                </h4>
                {d.currentIssue && <p className="advice-issue">当前问题：{d.currentIssue}</p>}
                {d.actions?.length > 0 && (
                  <ol className="advice-actions">{d.actions.map((a, j) => <li key={j}>{a}</li>)}</ol>
                )}
                {d.dailyPractice && <p className="advice-practice"><b>日常练习：</b>{d.dailyPractice}</p>}
                {d.programmingPractice && <p className="advice-practice"><b>编程练习：</b>{d.programmingPractice}</p>}
              </div>
            ))}
            {advice.weeklyPlan?.length > 0 && (
              <div className="advice-block">
                <h4>📅 四周训练计划</h4>
                <ol className="advice-actions">{advice.weeklyPlan.map((w, i) => <li key={i}>{w}</li>)}</ol>
              </div>
            )}
            {advice.resources?.length > 0 && (
              <div className="advice-block">
                <h4>🔗 推荐资源（来自互联网搜索）</h4>
                <div className="resource-list">
                  {advice.resources.map((r, i) => (
                    <div className="resource-item" key={i}>
                      <div className="resource-head">
                        <span className="resource-type">{r.type}</span>
                        <strong>{r.name}</strong>
                      </div>
                      <p>{r.description}</p>
                      {r.url && r.url !== '—' && (
                        <a href={r.url} target="_blank" rel="noreferrer">{r.url}</a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {advice.checkMethod && (
              <div className="advice-block">
                <h4>✅ 效果检验方法</h4>
                <p>{advice.checkMethod}</p>
              </div>
            )}
            <div className="advice-actions-bar">
              <button className="btn-ghost" onClick={fetchAdvice}>🔄 重新生成建议</button>
              <button className="btn-primary" onClick={onRestart}>完成，返回首页</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
