import { useEffect, useState } from 'react'
import QAPage from './pages/QAPage.jsx'
import GapPage from './pages/GapPage.jsx'
import ContractPage from './pages/ContractPage.jsx'
import { fetchHealth, fetchMeta } from './api.js'

const TABS = [
  { key: 'qa', label: '法规问答' },
  { key: 'gap', label: '合规差距分析' },
  { key: 'contract', label: '合同审查' },
]

export default function App() {
  const [tab, setTab] = useState('qa')
  const [health, setHealth] = useState(null)
  const [meta, setMeta] = useState(null)
  const [healthError, setHealthError] = useState('')

  useEffect(() => {
    fetchHealth().then(setHealth).catch((e) => setHealthError(e.message))
    fetchMeta().then(setMeta).catch(() => {})
  }, [])

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-mark">⚖</span>
            <div>
              <h1>法律合规助手</h1>
              <p className="subtitle">RAG 法规问答 · 差距分析 · 合同审查</p>
            </div>
          </div>
          <div className="status">
            {healthError ? (
              <span className="badge badge-bad">后端未连接</span>
            ) : health ? (
              <>
                <span className={`badge ${health.api_key_configured ? 'badge-ok' : 'badge-bad'}`}>
                  {health.api_key_configured ? `DeepSeek · ${health.model}` : '缺少 DEEPSEEK_API_KEY'}
                </span>
                <span className="badge badge-muted">语料块 {health.corpus_chunks}</span>
              </>
            ) : (
              <span className="badge badge-muted">连接中…</span>
            )}
          </div>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab ${tab === t.key ? 'tab-active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="main">
        {tab === 'qa' && <QAPage meta={meta} />}
        {tab === 'gap' && <GapPage meta={meta} />}
        {tab === 'contract' && <ContractPage />}
      </main>

      <footer className="footer">
        本工具不提供法律建议，输出结果仅供参考，必须由合格的法律顾问审查。
      </footer>
    </div>
  )
}
