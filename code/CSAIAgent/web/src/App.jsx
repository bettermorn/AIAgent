import React, { useEffect, useRef, useState } from 'react'
import { sendChat } from './api.js'
import MessageBubble from './components/MessageBubble.jsx'
import FeedbackForm from './components/FeedbackForm.jsx'
import ChatInput from './components/ChatInput.jsx'

const now = () =>
  new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })

const WELCOME = {
  id: 'welcome',
  role: 'assistant',
  text: '您好！我是 Helpdesk AI 智能客服 🤖 可以解答 FAQ、创建工单、处理投诉。请问有什么可以帮您？',
  time: now(),
}

function genId() {
  return Math.random().toString(36).slice(2, 10)
}

export default function App() {
  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(() => genId())
  const [userId, setUserId] = useState('u100')
  const [showFeedback, setShowFeedback] = useState(false)
  const listRef = useRef(null)

  // 新消息自动滚动到底部
  useEffect(() => {
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading, showFeedback])

  const push = (msg) => setMessages((prev) => [...prev, msg])

  const handleSend = async (overrideText) => {
    const text = (overrideText ?? input).trim()
    if (!text || loading) return
    setInput('')
    setShowFeedback(false)
    push({ id: genId(), role: 'user', text, time: now() })
    setLoading(true)
    try {
      const res = await sendChat({ session_id: sessionId, user_id: userId, query: text })
      push({
        id: genId(),
        role: 'assistant',
        text: res.answer ?? '（空回复）',
        intent: res.intent,
        ticketId: res.ticket_id,
        sources: res.meta?.sources || [],
        time: now(),
      })
      setShowFeedback(true)
    } catch (err) {
      push({
        id: genId(),
        role: 'assistant',
        text: `请求出错：${err.message}\n请确认后端服务已启动 (uvicorn app.main:app --port 8000)`,
        time: now(),
        error: true,
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-logo">🎧</div>
          <div>
            <div className="brand-name">Helpdesk AI</div>
            <div className="brand-sub">企业智能客服</div>
          </div>
        </div>

        <div className="field-group">
          <label className="field-label">会话 ID</label>
          <input className="field-input" value={sessionId} readOnly />
          <label className="field-label">用户 ID</label>
          <input
            className="field-input"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          />
        </div>

        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => {
            setMessages([WELCOME])
            setShowFeedback(false)
          }}
        >
          🗑 清空对话
        </button>

        <div className="sidebar-tip">
          支持意图：FAQ 问答 / 工单创建 / 投诉处理 / 多轮记忆
        </div>
      </aside>

      <main className="chat-main">
        <header className="chat-header">
          <span className="dot dot-green" />
          在线 · 会话 {sessionId}
        </header>

        <div className="msg-list" ref={listRef}>
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {loading && (
            <div className="msg-row msg-assistant">
              <div className="avatar">🤖</div>
              <div className="bubble bubble-typing">
                <span />
                <span />
                <span />
              </div>
            </div>
          )}
          {showFeedback && <FeedbackForm sessionId={sessionId} />}
        </div>

        <ChatInput
          value={input}
          onChange={setInput}
          onSend={() => handleSend()}
          onSuggest={(s) => handleSend(s)}
          disabled={loading}
        />
      </main>
    </div>
  )
}
