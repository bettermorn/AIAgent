import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchAgents, sendChat, runPipeline } from './api.js'

const AGENT_META = {
  collector: { icon: '📥', label: '信息收集', desc: '按主题与数量收集信息' },
  summarizer: { icon: '📝', label: '摘要生成', desc: '对长文本生成结构化摘要' },
  translator: { icon: '🌐', label: '文本翻译', desc: '中英文智能互译' },
  classifier: { icon: '🏷️', label: '内容分类', desc: '识别文本所属类别' },
}

const TOPICS = ['集成电路', '工业软件', '生物医药']

/* ---------- 子组件：Agent 状态卡片 ---------- */
function AgentCard({ agent, active, onClick }) {
  const meta = AGENT_META[agent.name] || { icon: '🤖', label: agent.name, desc: '' }
  const card = agent.card || {}
  return (
    <button
      className={`agent-card ${active ? 'active' : ''} ${agent.online ? '' : 'offline'}`}
      onClick={onClick}
    >
      <div className="agent-card-header">
        <span className="agent-icon">{meta.icon}</span>
        <div className="agent-card-title">
          <strong>{meta.label}</strong>
          <span className="agent-url">{agent.url}</span>
        </div>
        <span className={`status-dot ${agent.online ? 'on' : 'off'}`} title={agent.online ? '在线' : '离线'} />
      </div>
      <p className="agent-desc">{card.description || meta.desc}</p>
      {card.skills?.length > 0 && (
        <div className="agent-skills">
          {card.skills.map((s) => (
            <span key={s.id} className="skill-tag">{s.name}</span>
          ))}
        </div>
      )}
    </button>
  )
}

/* ---------- 子组件：聊天气泡 ---------- */
function Bubble({ role, text, elapsed, onTranslate, translating }) {
  const isTranslation = text?.startsWith('# Translation Result')
  return (
    <div className={`bubble ${role}`}>
      <div className="bubble-role">
        {role === 'user' ? '🧑 你' : '🤖 Agent'}
        {elapsed != null && <span className="bubble-elapsed">{elapsed}s</span>}
        {role === 'user' && onTranslate && !translating && (
          <button className="translate-btn" onClick={onTranslate} title="翻译此消息">
            🌐 翻译
          </button>
        )}
        {translating && <span className="bubble-elapsed">翻译中...</span>}
      </div>
      {isTranslation && <div className="translation-badge">🌐 翻译结果</div>}
      <pre className="bubble-text">{text}</pre>
    </div>
  )
}

/* ---------- 主应用 ---------- */
export default function App() {
  const [tab, setTab] = useState('chat') // chat | pipeline
  const [agents, setAgents] = useState([])
  const [activeAgent, setActiveAgent] = useState('collector')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [topic, setTopic] = useState('AI')
  const [count, setCount] = useState(3)
  const [pipelineRunning, setPipelineRunning] = useState(false)
  const [pipelineResult, setPipelineResult] = useState(null)
  const [translatingIdx, setTranslatingIdx] = useState(null)
  const chatEndRef = useRef(null)

  const refreshAgents = useCallback(async () => {
    try {
      const data = await fetchAgents()
      setAgents(data.agents || [])
    } catch {
      setAgents(Object.keys(AGENT_META).map((name) => ({
        name,
        url: `http://localhost:800${{ collector: 1, summarizer: 2, translator: 3, classifier: 4 }[name]}`,
        online: false,
        card: null,
      })))
    }
  }, [])

  useEffect(() => {
    refreshAgents()
    const t = setInterval(refreshAgents, 15000)
    return () => clearInterval(t)
  }, [refreshAgents])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || sending) return
    setMessages((m) => [...m, { role: 'user', text }])
    setInput('')
    setSending(true)
    try {
      const res = await sendChat(activeAgent, text)
      setMessages((m) => [
        ...m,
        { role: 'agent', text: res.reply, elapsed: res.elapsed },
      ])
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'agent', text: `❌ 请求失败：${e.message}\n请确认网关 (8080) 与 Agent 服务已启动。` },
      ])
    } finally {
      setSending(false)
    }
  }

  // 对任意一条消息调用 Translator Agent 进行翻译，结果追加到对话中
  const handleTranslate = async (idx) => {
    const text = messages[idx]?.text
    if (!text || translatingIdx != null) return
    setTranslatingIdx(idx)
    setSending(true)
    try {
      const res = await sendChat('translator', `将以下内容翻译成英文：\n\n${text}`)
      setMessages((m) => [
        ...m,
        { role: 'agent', text: res.reply, elapsed: res.elapsed },
      ])
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'agent', text: `❌ 翻译失败：${e.message}\n请确认 Translator Agent (8003) 已启动。` },
      ])
    } finally {
      setSending(false)
      setTranslatingIdx(null)
    }
  }

  const handlePipeline = async () => {
    if (pipelineRunning) return
    setPipelineRunning(true)
    setPipelineResult(null)
    try {
      const res = await runPipeline(topic, count)
      setPipelineResult(res)
    } catch (e) {
      setPipelineResult({ ok: false, error: e.message, stages: [] })
    } finally {
      setPipelineRunning(false)
    }
  }

  return (
    <div className="app">
      {/* 顶栏 */}
      <header className="header">
        <div className="brand">
          <span className="logo">⚡</span>
          <div>
            <h1>A2A Agent 协作平台</h1>
            <p>Google A2A SDK · DeepSeek 模型驱动</p>
          </div>
        </div>
        <nav className="tabs">
          <button className={tab === 'chat' ? 'tab active' : 'tab'} onClick={() => setTab('chat')}>
            💬 Agent 对话
          </button>
          <button className={tab === 'pipeline' ? 'tab active' : 'tab'} onClick={() => setTab('pipeline')}>
            🔗 协作管道
          </button>
          <button className="tab refresh" onClick={refreshAgents} title="刷新 Agent 状态">
            ↻
          </button>
        </nav>
      </header>

      <main className="layout">
        {/* 左侧：Agent 列表 */}
        <aside className="sidebar">
          <h2 className="sidebar-title">Agent 服务 ({agents.filter((a) => a.online).length}/{agents.length} 在线)</h2>
          <div className="agent-list">
            {agents.map((a) => (
              <AgentCard
                key={a.name}
                agent={a}
                active={tab === 'chat' && activeAgent === a.name}
                onClick={() => setActiveAgent(a.name)}
              />
            ))}
          </div>
          <div className="sidebar-tip">
            <p>💡 Agent 离线时请先启动对应服务：</p>
            <code>python agents/xxx_agent.py</code>
          </div>
        </aside>

        {/* 右侧：主内容区 */}
        <section className="content">
          {tab === 'chat' && (
            <div className="chat-panel">
              <div className="chat-messages">
                {messages.length === 0 && (
                  <div className="empty">
                    <p>🎯 已连接 <strong>{AGENT_META[activeAgent]?.label || activeAgent}</strong> Agent</p>
                    <p>试试输入：「收集关于集成电路的信息，限制 3 条」</p>
                  </div>
                )}
                {messages.map((m, i) => (
                  <Bubble
                    key={i}
                    role={m.role}
                    text={m.text}
                    elapsed={m.elapsed}
                    translating={translatingIdx === i}
                    onTranslate={() => handleTranslate(i)}
                  />
                ))}
                {sending && <div className="typing">Agent 思考中<span className="dots">...</span></div>}
                <div ref={chatEndRef} />
              </div>
              <div className="chat-input">
                <textarea
                  value={input}
                  placeholder={`向 ${AGENT_META[activeAgent]?.label || activeAgent} Agent 发送消息... (点击「发送」按钮提交)`}
                  onChange={(e) => setInput(e.target.value)}
                />
                <button onClick={handleSend} disabled={sending || !input.trim()}>
                  发送
                </button>
              </div>
            </div>
          )}

          {tab === 'pipeline' && (
            <div className="pipeline-panel">
              <div className="pipeline-controls card">
                <h3>🚀 多 Agent 协作管道</h3>
                <p className="pipeline-flow">收集信息 → 内容分类 → 生成摘要 → 翻译英文</p>
                <div className="controls-row">
                  <label>
                    主题
                    <select value={topic} onChange={(e) => setTopic(e.target.value)}>
                      {TOPICS.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    数量
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={count}
                      onChange={(e) => setCount(Math.min(10, Math.max(1, Number(e.target.value) || 1)))}
                    />
                  </label>
                  <button className="run-btn" onClick={handlePipeline} disabled={pipelineRunning}>
                    {pipelineRunning ? '⏳ 执行中...' : '▶ 运行管道'}
                  </button>
                </div>
              </div>

              {pipelineRunning && (
                <div className="pipeline-stages">
                  {['collector', 'classifier', 'summarizer', 'translator'].map((name) => (
                    <div key={name} className="stage running">
                      <span>{AGENT_META[name].icon}</span> {AGENT_META[name].label} 执行中...
                    </div>
                  ))}
                </div>
              )}

              {pipelineResult && !pipelineResult.ok && (
                <div className="card error-card">❌ 管道执行失败：{pipelineResult.error}</div>
              )}

              {pipelineResult?.ok && (
                <>
                  <div className="pipeline-stages">
                    {pipelineResult.stages.map((s, i) => (
                      <div key={i} className="stage done">
                        <span>{AGENT_META[s.agent]?.icon}</span>
                        <strong>{s.description}</strong>
                        <em>{s.elapsed}s</em>
                      </div>
                    ))}
                  </div>
                  <div className="pipeline-results">
                    <details open className="card">
                      <summary>📥 收集的信息</summary>
                      <pre>{pipelineResult.result.news}</pre>
                    </details>
                    <details className="card">
                      <summary>🏷️ 分类结果</summary>
                      <pre>{pipelineResult.result.classification}</pre>
                    </details>
                    <details open className="card">
                      <summary>📝 中文摘要</summary>
                      <pre>{pipelineResult.result.summary}</pre>
                    </details>
                    <details open className="card translation-card">
                      <summary>🌐 英文翻译（含中文摘要对照）</summary>
                      <div className="translation-view">
                        <div className="translation-col">
                          <div className="translation-lang">🇨🇳 中文摘要</div>
                          <pre>{pipelineResult.result.summary}</pre>
                        </div>
                        <div className="translation-col">
                          <div className="translation-lang">🇬🇧 English Translation</div>
                          <pre>{pipelineResult.result.translation}</pre>
                        </div>
                      </div>
                    </details>
                  </div>
                </>
              )}
            </div>
          )}
        </section>
      </main>

      <footer className="footer">
        A2A Agent 协作平台 · React + FastAPI + Google A2A SDK + DeepSeek
      </footer>
    </div>
  )
}
