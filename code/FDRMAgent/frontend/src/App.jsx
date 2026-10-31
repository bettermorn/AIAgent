import { useEffect, useState } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';
import { api } from './api.js';
import Dashboard from './pages/Dashboard.jsx';
import DueDiligence from './pages/DueDiligence.jsx';
import EarlyWarning from './pages/EarlyWarning.jsx';
import GraphPage from './pages/GraphPage.jsx';
import AnomalyPage from './pages/AnomalyPage.jsx';
import ModelsPage from './pages/ModelsPage.jsx';
import Reviews from './pages/Reviews.jsx';
import Audit from './pages/Audit.jsx';
import Copilot from './pages/Copilot.jsx';

const NAV = [
  { group: '总览', items: [['/', '风险驾驶舱', '◎']] },
  { group: '智能体', items: [['/due-diligence', '授信尽调', '◆'], ['/early-warning', '风险预警', '▲'], ['/copilot', '风控助手', '✦']] },
  { group: '模型与数据', items: [['/graph', '关联图谱', '⬡'], ['/anomaly', '异常检测', '≋'], ['/models', '评分卡与模型', '▤']] },
  { group: '治理', items: [['/reviews', '人工复核', '✓'], ['/audit', '审计留痕', '☰']] },
];

export default function App() {
  const [health, setHealth] = useState(null);
  useEffect(() => {
    api.get('/health').then(setHealth).catch(() => setHealth({ status: 'down' }));
  }, []);

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">FR</div>
          <div>
            <div className="brand-title">智能风控智能体</div>
            <div className="brand-sub">Financial Risk Agent</div>
          </div>
        </div>
        {NAV.map((g) => (
          <div key={g.group} className="nav-group">
            <div className="nav-group-title">{g.group}</div>
            {g.items.map(([to, label, icon]) => (
              <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <span className="nav-icon">{icon}</span>{label}
              </NavLink>
            ))}
          </div>
        ))}
        <div className="sidebar-foot">
          <div className="status-row">
            <span className={`dot ${health?.db === 'ok' ? 'ok' : 'bad'}`} />PostgreSQL {health?.db === 'ok' ? '已连接' : '未连接'}
          </div>
          <div className="status-row">
            <span className={`dot ${health?.llm?.mode === 'deepseek' ? 'ok' : 'warn'}`} />
            {health?.llm?.mode === 'deepseek' ? `DeepSeek · ${health.llm.model}` : 'MockLLM（未配置 Key）'}
          </div>
          <div className="foot-note">示例数据为教学虚构，结论仅供参考，最终决定由人工作出。</div>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/due-diligence" element={<DueDiligence />} />
          <Route path="/early-warning" element={<EarlyWarning />} />
          <Route path="/copilot" element={<Copilot />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/anomaly" element={<AnomalyPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/reviews" element={<Reviews />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="/audit/:runId" element={<Audit />} />
        </Routes>
      </main>
    </div>
  );
}
