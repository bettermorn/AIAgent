import { useState, useRef, useEffect } from 'react'

const NPC_THEMES = {
  '村长': { emoji: '🏛️', color: '#e6b980', tag: '村长' },
  '铁匠': { emoji: '⚔️', color: '#8fa8c8', tag: '铁匠' },
  '药师': { emoji: '🌿', color: '#8fc8a0', tag: '药师' },
  '系统': { emoji: '🎮', color: '#b8a8d8', tag: '系统' },
}

export default function App() {
  const [npcs, setNpcs] = useState([])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    fetch('/api/npcs')
      .then((r) => r.json())
      .then(setNpcs)
      .catch(() => {})
    setMessages([
      {
        role: 'npc',
        npc: '系统',
        text: '欢迎来到 NPC 村落！直接说话，系统会自动为你选择合适的 NPC 回答。所有 NPC 都能看到完整的对话历史。',
      },
    ])
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function send() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text }])
    setLoading(true)
    try {
      const chatHistory = messages
        .filter((m) => m.role !== 'npc' || m.npc !== '系统')
        .map((m) =>
          m.role === 'user'
            ? { role: 'user', content: m.text }
            : { role: 'assistant', npc: m.npc, content: m.text }
        )
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, chat_history: chatHistory }),
      })
      const data = await res.json()
      setMessages((m) => [
        ...m,
        { role: 'npc', npc: data.npc, npcEmoji: data.npc_emoji, text: data.reply },
      ])
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: 'npc', npc: '系统', text: '⚠️ 连接失败，请确认后端服务已启动（python server.py）' },
      ])
    } finally {
      setLoading(false)
    }
  }

  function onKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">
          <span className="logo-icon">🏰</span>
          <div>
            <h1>NPC 村落</h1>
            <p>LangGraph × DeepSeek</p>
          </div>
        </div>
        <div className="npc-list">
          {npcs.map((npc) => (
            <div className="npc-card" key={npc.name}>
              <span className="npc-emoji">{npc.emoji}</span>
              <div>
                <div className="npc-name">{npc.name}</div>
                <div className="npc-desc">{npc.desc}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="sidebar-tip">
          💡 智能路由：AI 会根据对话内容自动选择最合适的 NPC 回答
        </div>
      </aside>

      <main className="chat">
        <div className="chat-header">
          <span>💬 村落对话</span>
          <span className="status-dot" title="后端状态" />
        </div>
        <div className="chat-body">
          {messages.map((msg, i) => {
            if (msg.role === 'user') {
              return (
                <div className="msg-row user" key={i}>
                  <div className="bubble user-bubble">{msg.text}</div>
                  <div className="avatar user-avatar">🧑‍🎤</div>
                </div>
              )
            }
            const theme = NPC_THEMES[msg.npc] || NPC_THEMES['系统']
            return (
              <div className="msg-row npc" key={i}>
                <div className="avatar" style={{ background: theme.color }}>
                  {msg.npcEmoji || theme.emoji}
                </div>
                <div className="bubble npc-bubble">
                  <div className="npc-tag" style={{ color: theme.color }}>
                    {msg.npc}
                  </div>
                  <div className="msg-text">{msg.text}</div>
                </div>
              </div>
            )
          })}
          {loading && (
            <div className="msg-row npc">
              <div className="avatar thinking">💭</div>
              <div className="bubble npc-bubble typing">
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
        <div className="chat-input">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="说点什么吧，例如：我需要一把剑…"
            rows={1}
          />
          <button onClick={send} disabled={loading || !input.trim()}>
            {loading ? '思考中…' : '发送'}
          </button>
        </div>
      </main>
    </div>
  )
}
