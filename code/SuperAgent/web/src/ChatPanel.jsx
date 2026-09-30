import { useState } from 'react'
import { sendChat } from './api.js'

export default function ChatPanel() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSend = async (e) => {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: text }])
    setLoading(true)
    try {
      const res = await sendChat(text, { userId: 'u1', name: 'You' })
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: res.reply, citations: res.citations },
      ])
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: `调用失败：${err.message}`, error: true },
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel">
      <h2>智能对话</h2>
      <div className="chat-box">
        {messages.length === 0 && (
          <div className="empty-hint">
            向超级智能体提问，例如：请介绍一下这个超级智能体的能力，并给出实现建议
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="bubble">
              {m.content}
              {m.citations?.length > 0 && (
                <div className="citations">
                  <strong>参考依据：</strong>
                  {m.citations.map((c, j) => (
                    <span className="chip" key={j}>{c}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="msg assistant"><div className="bubble typing">思考中…</div></div>}
      </div>
      <form className="chat-input" onSubmit={handleSend}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入消息，回车发送"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>发送</button>
      </form>
    </section>
  )
}
