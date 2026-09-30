import React, { useEffect, useState } from 'react';
import './App.css';
import EssayForm from './components/EssayForm';
import StatusBar from './components/StatusBar';
import PlanDisplay from './components/PlanDisplay';
import CritiqueDisplay from './components/CritiqueDisplay';
import EssayDisplay from './components/EssayDisplay';

const API_BASE =
  process.env.REACT_APP_API_BASE ||
  `${window.location.protocol}//${window.location.hostname}:8000`;

function App() {
  const [task, setTask] = useState('');
  const [maxRevisions, setMaxRevisions] = useState(2);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [currentNode, setCurrentNode] = useState('');
  const [plan, setPlan] = useState('');
  const [draft, setDraft] = useState('');
  const [critique, setCritique] = useState('');
  const [revisionNumber, setRevisionNumber] = useState(1);

  const [health, setHealth] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth({ status: 'down' }));
  }, []);

  const reset = () => {
    setError('');
    setDone(false);
    setCurrentNode('');
    setPlan('');
    setDraft('');
    setCritique('');
    setRevisionNumber(1);
  };

  const handleSubmit = () => {
    reset();
    setLoading(true);

    const url = `${API_BASE}/api/essay/generate`;
    // 使用 fetch + ReadableStream 解析 SSE，便于自定义错误处理
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task: task.trim(), max_revisions: maxRevisions }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `HTTP ${response.status}`);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        const pump = () =>
          reader.read().then(({ value, done: rDone }) => {
            if (rDone) {
              setLoading(false);
              return;
            }
            buffer += decoder.decode(value, { stream: true });
            const events = buffer.split('\n\n');
            buffer = events.pop() || '';

            for (const evt of events) {
              const line = evt.split('\n').find((l) => l.startsWith('data:'));
              if (!line) continue;
              const dataStr = line.slice(5).trim();
              if (!dataStr) continue;
              try {
                const payload = JSON.parse(dataStr);
                handleEvent(payload);
              } catch (e) {
                console.warn('解析 SSE 失败', e, dataStr);
              }
            }
            pump();
          });
        pump();
      })
      .catch((err) => {
        setError(err.message || String(err));
        setLoading(false);
      });
  };

  const handleEvent = (payload) => {
    if (payload.type === 'error') {
      setError(payload.message || '未知错误');
      setLoading(false);
      return;
    }
    if (payload.type === 'done') {
      setDone(true);
      setCurrentNode('');
      setLoading(false);
      // 最终内容再合并一次
      mergeData(payload.data || {});
      return;
    }
    if (payload.type === 'node') {
      setCurrentNode(payload.node);
      mergeData(payload.data || {});
    }
  };

  const mergeData = (data) => {
    if (typeof data.plan === 'string') setPlan(data.plan);
    if (typeof data.draft === 'string') setDraft(data.draft);
    if (typeof data.critique === 'string') setCritique(data.critique);
    if (typeof data.revision_number === 'number') setRevisionNumber(data.revision_number);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          <span className="logo">✍️</span> Essay Writer
        </h1>
        <p className="subtitle">
          基于 DeepSeek 的多 Agent 写作助手 · 规划 · 检索 · 撰写 · 批改 · 修订
        </p>
        <div className="health">
          {health &&
            (health.status === 'ok' ? (
              health.deepseek_configured === 'yes' ? (
                <span className="ok">● 已连接后端 · DeepSeek 已配置 · 模型：{health.model}</span>
              ) : (
                <span className="warn">
                  ● 已连接后端，但未配置 DEEPSEEK_API_KEY（请检查 config.env）
                </span>
              )
            ) : (
              <span className="warn">● 后端不可达（{API_BASE}）</span>
            ))}
        </div>
      </header>

      <main className="app-main">
        <section className="left-panel">
          <EssayForm
            task={task}
            setTask={setTask}
            maxRevisions={maxRevisions}
            setMaxRevisions={setMaxRevisions}
            onSubmit={handleSubmit}
            loading={loading}
          />
        </section>

        <section className="right-panel">
          <StatusBar
            currentNode={currentNode}
            revisionNumber={revisionNumber}
            maxRevisions={maxRevisions}
            error={error}
            done={done}
          />
          <div className="cards-grid">
            <PlanDisplay plan={plan} />
            <CritiqueDisplay critique={critique} />
            <EssayDisplay draft={draft} />
          </div>
        </section>
      </main>

      <footer className="app-footer">
        Powered by DeepSeek · LangGraph · FastAPI · React
      </footer>
    </div>
  );
}

export default App;