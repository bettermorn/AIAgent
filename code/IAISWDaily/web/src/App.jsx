import React, { useCallback, useEffect, useState } from 'react';
import { api } from './api.js';
import ReportPanel from './components/ReportPanel.jsx';
import ArticlesPanel from './components/ArticlesPanel.jsx';
import RunsPanel from './components/RunsPanel.jsx';
import SettingsPanel from './components/SettingsPanel.jsx';

const TABS = [
  { key: 'report', label: '每日日报' },
  { key: 'articles', label: '信息检索' },
  { key: 'runs', label: '采集记录' },
  { key: 'settings', label: '配置' },
];

export default function App() {
  const [tab, setTab] = useState('report');
  const [health, setHealth] = useState(null);
  const [channels, setChannels] = useState([]);
  const [running, setRunning] = useState(false);
  const [toast, setToast] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const notify = useCallback((message, type = 'info') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
    } catch (err) {
      setHealth({ ok: false, db: false, llm: false });
    }
  }, []);

  useEffect(() => {
    loadHealth();
    api.channels().then(setChannels).catch(() => setChannels([]));
  }, [loadHealth]);

  // 轮询运行状态
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(async () => {
      try {
        const data = await api.runs();
        if (!data.running) {
          setRunning(false);
          setRefreshKey((k) => k + 1);
          notify('采集完成，日报已更新', 'success');
        }
      } catch { /* noop */ }
    }, 4000);
    return () => clearInterval(timer);
  }, [running, notify]);

  const runNow = async () => {
    try {
      await api.runNow();
      setRunning(true);
      notify('采集任务已启动，正在检索与总结...', 'info');
    } catch (err) {
      notify(err.message, 'error');
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">II</div>
          <div>
            <h1>工业智能 · 工业软件 信息智能体</h1>
            <p className="sub">每日自动检索国际网站 / 微信公众号 / B站，并由 DeepSeek 生成中文日报</p>
          </div>
        </div>
        <div className="topbar-right">
          <StatusPill ok={health?.db} label="数据库" />
          <StatusPill ok={health?.llm} label="DeepSeek" />
          <StatusPill
            ok={
              health?.search?.serpapi ||
              health?.search?.bocha ||
              health?.search?.deepseek ||
              health?.search?.mock
            }
            label="搜索源"
          />
          <button className="primary" onClick={runNow} disabled={running}>
            {running ? <span className="spinner" /> : null}
            {running ? '采集中…' : '立即采集'}
          </button>
        </div>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? 'tab active' : 'tab'}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
        {health?.schedule?.cron && <span className="cron">定时：{health.schedule.cron}</span>}
      </nav>

      <main className="content">
        {tab === 'report' && <ReportPanel refreshKey={refreshKey} channels={channels} />}
        {tab === 'articles' && <ArticlesPanel refreshKey={refreshKey} channels={channels} />}
        {tab === 'runs' && <RunsPanel refreshKey={refreshKey} />}
        {tab === 'settings' && <SettingsPanel channels={channels} notify={notify} />}
      </main>

      {toast && <div className={`toast ${toast.type}`}>{toast.message}</div>}
    </div>
  );
}

function StatusPill({ ok, label }) {
  return (
    <span className={`pill ${ok ? 'ok' : 'bad'}`}>
      <i className="dot" />
      {label}
    </span>
  );
}
