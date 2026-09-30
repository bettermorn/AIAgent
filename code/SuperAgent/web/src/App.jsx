import { useState, useEffect } from 'react'
import { checkHealth } from './api.js'
import ChatPanel from './ChatPanel.jsx'
import IngestPanel from './IngestPanel.jsx'
import ToolPanel from './ToolPanel.jsx'

const TABS = [
  { key: 'chat', label: '对话' },
  { key: 'ingest', label: '知识库' },
  { key: 'tool', label: '工具' },
]

export default function App() {
  const [tab, setTab] = useState('chat')
  const [health, setHealth] = useState(null)

  useEffect(() => {
    checkHealth()
      .then((h) => setHealth(h.ok === true))
      .catch(() => setHealth(false))
  }, [])

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="logo">S</span>
          <div>
            <h1>SuperAgent</h1>
            <p>多智能体编排 · LangGraph + DeepSeek</p>
          </div>
        </div>
        <span className={`status ${health ? 'up' : 'down'}`}>
          {health === null ? '检测中…' : health ? '后端在线' : '后端离线'}
        </span>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? 'active' : ''}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        {tab === 'chat' && <ChatPanel />}
        {tab === 'ingest' && <IngestPanel />}
        {tab === 'tool' && <ToolPanel />}
      </main>

      <footer className="footer">
        Planner → Researcher → Writer → Reflector · Powered by DeepSeek
      </footer>
    </div>
  )
}
