import React, { useEffect, useState, useCallback, useRef } from 'react';
import { fetchQuestionnaire, fetchAssessmentList, fetchAssessment, submitAssessment } from './api.js';
import QuestionnaireForm from './components/QuestionnaireForm.jsx';
import ReportView from './components/ReportView.jsx';

const POLL_INTERVAL = 4000;

export default function App() {
  const [view, setView] = useState('form'); // form | submitting | report | history
  const [questionnaire, setQuestionnaire] = useState(null);
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState('');
  const pollRef = useRef(null);

  useEffect(() => {
    fetchQuestionnaire()
      .then(setQuestionnaire)
      .catch((e) => setError(`加载问卷失败：${e.message}`));
  }, []);

  const loadHistory = useCallback(() => {
    fetchAssessmentList()
      .then(setHistory)
      .catch((e) => setError(`加载历史记录失败：${e.message}`));
  }, []);

  useEffect(() => {
    if (view === 'history') loadHistory();
  }, [view, loadHistory]);

  // 提交后轮询报告状态
  const startPolling = useCallback((id) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const rec = await fetchAssessment(id);
        if (rec.status === 'completed' || rec.status === 'failed') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setReport(rec);
          setView(rec.status === 'completed' ? 'report' : 'form');
          if (rec.status === 'failed') setError(`报告生成失败：${rec.error || '未知错误'}`);
        }
      } catch (e) {
        clearInterval(pollRef.current);
        pollRef.current = null;
        setError(`查询报告失败：${e.message}`);
        setView('form');
      }
    }, POLL_INTERVAL);
  }, []);

  useEffect(() => () => pollRef.current && clearInterval(pollRef.current), []);

  const handleSubmit = async (payload) => {
    setError('');
    setView('submitting');
    try {
      const { id } = await submitAssessment(payload);
      startPolling(id);
    } catch (e) {
      setError(`提交失败：${e.message}`);
      setView('form');
    }
  };

  const openReport = async (id) => {
    try {
      const rec = await fetchAssessment(id);
      setReport(rec);
      setView('report');
      window.scrollTo(0, 0);
    } catch (e) {
      setError(`查看失败：${e.message}`);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-icon">⚡</span>
            <div>
              <h1>技术领导力评测智能体</h1>
              <p className="subtitle">Technical Leadership Assessment Agent · Powered by DeepSeek</p>
            </div>
          </div>
          <nav className="nav">
            <button className={view === 'form' || view === 'submitting' ? 'nav-btn active' : 'nav-btn'} onClick={() => { setView('form'); }}>
              开始评测
            </button>
            <button className={view === 'history' ? 'nav-btn active' : 'nav-btn'} onClick={() => setView('history')}>
              历史报告
            </button>
          </nav>
        </div>
      </header>

      <main className="main">
        {error && (
          <div className="alert error" onClick={() => setError('')}>
            {error} <span className="alert-close">✕</span>
          </div>
        )}

        {!questionnaire && !error && <div className="loading">正在加载问卷…</div>}

        {questionnaire && view === 'form' && (
          <QuestionnaireForm questionnaire={questionnaire} onSubmit={handleSubmit} />
        )}

        {view === 'submitting' && (
          <div className="submitting card">
            <div className="spinner" />
            <h2>评测报告生成中</h2>
            <p>智能体正在执行以下步骤，通常需要 1-2 分钟：</p>
            <ol className="steps-list">
              <li>计算各维度得分与加权总分</li>
              <li>调用 DeepSeek 生成评价结论</li>
              <li>通过 Bocha / SerpAPI 搜索最新学习资源</li>
              <li>结合课程知识库生成个性化学习建议</li>
            </ol>
            <p className="muted">页面会自动跳转，请勿关闭…</p>
          </div>
        )}

        {view === 'report' && report && (
          <ReportView report={report} onBack={() => setView('history')} />
        )}

        {view === 'history' && (
          <section className="card">
            <h2>历史评测报告</h2>
            {history.length === 0 ? (
              <p className="muted">暂无记录，先完成一次评测吧。</p>
            ) : (
              <table className="history-table">
                <thead>
                  <tr>
                    <th>被评价人</th>
                    <th>部门/职位</th>
                    <th>评价关系</th>
                    <th>总分</th>
                    <th>状态</th>
                    <th>时间</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id}>
                      <td>{h.evaluatee_name || '-'}</td>
                      <td>{[h.department, h.position].filter(Boolean).join(' / ') || '-'}</td>
                      <td>{h.relationship || '-'}</td>
                      <td><strong>{h.total_score ?? '-'}</strong></td>
                      <td>
                        <span className={`badge ${h.status}`}>{statusLabel(h.status)}</span>
                      </td>
                      <td className="muted">{new Date(h.created_at).toLocaleString('zh-CN')}</td>
                      <td>
                        <button className="btn small" onClick={() => openReport(h.id)}>查看</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}
      </main>

      <footer className="footer">
        依据《技术领导力评测问卷》构建 · 参考：技术领导力课程（0-4 系列）与 CSDN【专业发展】技术领导力
      </footer>
    </div>
  );
}

function statusLabel(s) {
  return { processing: '生成中', completed: '已完成', failed: '失败' }[s] || s;
}
