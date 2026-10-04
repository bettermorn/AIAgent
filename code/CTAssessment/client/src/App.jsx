import React, { useEffect, useState } from 'react';
import { api } from './api.js';
import BasicInfoStep from './components/BasicInfoStep.jsx';
import SelfRatingStep from './components/SelfRatingStep.jsx';
import TasksStep from './components/TasksStep.jsx';
import ReportView from './components/ReportView.jsx';
import HistoryView from './components/HistoryView.jsx';

const STEPS = [
  { key: 'basic', title: '基本信息', desc: '了解你的学习和编程背景' },
  { key: 'self', title: '自评量表', desc: '20 道题，按真实情况作答' },
  { key: 'tasks', title: '情境测试', desc: '14 道情境题，展现真实能力' },
];

export default function App() {
  const [view, setView] = useState('home'); // home | wizard | report | history
  const [step, setStep] = useState(0);
  const [studentName, setStudentName] = useState('');
  const [basicInfo, setBasicInfo] = useState({ grade: '', programmingExp: '', languages: [], chartsUsage: '' });
  const [selfRating, setSelfRating] = useState({});
  const [tasks, setTasks] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (error) {
      const t = setTimeout(() => setError(''), 6000);
      return () => clearTimeout(t);
    }
  }, [error]);

  async function handleSubmit() {
    setSubmitting(true);
    setError('');
    try {
      const data = await api.submit({ studentName, basicInfo, selfRating, tasks });
      setResult(data);
      setView('report');
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  function restart() {
    setView('home');
    setStep(0);
    setStudentName('');
    setBasicInfo({ grade: '', programmingExp: '', languages: [], chartsUsage: '' });
    setSelfRating({});
    setTasks({});
    setResult(null);
  }

  async function openHistory(id) {
    try {
      const record = await api.getAssessment(id);
      setResult(record);
      setView('report');
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo" onClick={restart}>
            <span className="logo-icon">🧠</span>
            <div>
              <h1>计算思维测试智能体</h1>
              <p>高中生计算思维能力评测 · 评价与学习建议</p>
            </div>
          </div>
          <nav className="nav">
            <button className={view === 'home' || view === 'wizard' ? 'active' : ''} onClick={() => (view === 'wizard' ? setView('home') : restart())}>开始测评</button>
            <button className={view === 'history' ? 'active' : ''} onClick={() => setView('history')}>历史记录</button>
          </nav>
        </div>
      </header>

      {error && <div className="error-bar">⚠️ {error}</div>}

      <main className="main">
        {view === 'home' && (
          <div className="home">
            <div className="hero">
              <h2>你了解自己的计算思维吗？</h2>
              <p>
                本测评基于《高中生计算思维能力评测问卷》，从<b>分解问题、模式识别、抽象、算法设计</b>
                四个维度，结合自评量表与情境任务，由 AI 智能体为你给出评价结论和个性化学习建议。
              </p>
              <div className="feature-cards">
                <div className="card">
                  <span className="card-icon">📋</span>
                  <h3>四维测评</h3>
                  <p>20 道自评题 + 14 道情境任务，全面覆盖计算思维核心能力</p>
                </div>
                <div className="card">
                  <span className="card-icon">🤖</span>
                  <h3>AI 智能评价</h3>
                  <p>DeepSeek 大模型按评分标准逐题判分，生成分维度评价结论</p>
                </div>
                <div className="card">
                  <span className="card-icon">📚</span>
                  <h3>个性化学习建议</h3>
                  <p>结合语言训练与日常任务知识库，并搜索互联网推荐学习资源</p>
                </div>
              </div>
              <button className="btn-primary btn-lg" onClick={() => { setView('wizard'); setStep(0); }}>
                开始测评 →
              </button>
              <p className="tip">建议用时 30—40 分钟 · 除特别说明外不建议使用网络搜索</p>
            </div>
          </div>
        )}

        {view === 'wizard' && (
          <div className="wizard">
            <div className="stepper">
              {STEPS.map((s, i) => (
                <div key={s.key} className={`step ${i === step ? 'current' : ''} ${i < step ? 'done' : ''}`}>
                  <div className="step-num">{i < step ? '✓' : i + 1}</div>
                  <div className="step-text">
                    <strong>{s.title}</strong>
                    <span>{s.desc}</span>
                  </div>
                </div>
              ))}
            </div>

            {step === 0 && (
              <BasicInfoStep
                studentName={studentName}
                setStudentName={setStudentName}
                basicInfo={basicInfo}
                setBasicInfo={setBasicInfo}
                onNext={() => setStep(1)}
              />
            )}
            {step === 1 && (
              <SelfRatingStep
                selfRating={selfRating}
                setSelfRating={setSelfRating}
                onPrev={() => setStep(0)}
                onNext={() => setStep(2)}
              />
            )}
            {step === 2 && (
              <TasksStep
                tasks={tasks}
                setTasks={setTasks}
                onPrev={() => setStep(1)}
                onSubmit={handleSubmit}
                submitting={submitting}
              />
            )}
            {submitting && (
              <div className="overlay">
                <div className="loading-box">
                  <div className="spinner" />
                  <p>AI 智能体正在批改你的答卷…</p>
                  <small>评分与结论生成约需 1—2 分钟，请耐心等待</small>
                </div>
              </div>
            )}
          </div>
        )}

        {view === 'report' && result && (
          <ReportView result={result} onRestart={restart} />
        )}

        {view === 'history' && (
          <HistoryView onOpen={openHistory} onError={setError} />
        )}
      </main>

      <footer className="footer">
        计算思维测试智能体 · React + Node.js + DeepSeek + PostgreSQL · 仅用于学习和教学诊断，不作为能力或成绩的唯一评价依据
      </footer>
    </div>
  );
}
