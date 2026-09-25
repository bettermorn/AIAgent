import { useEffect, useRef, useState } from 'react'
import { api } from './api'

const LEVEL_COLORS = {
  A1: '#22c55e',
  A2: '#84cc16',
  B1: '#eab308',
  B2: '#f97316',
  C1: '#ef4444',
}

function MasteryBar({ value }) {
  const color =
    value >= 0.8 ? '#22c55e' : value >= 0.5 ? '#84cc16' : value >= 0.3 ? '#eab308' : '#ef4444'
  return (
    <div className="mastery-bar">
      <div className="mastery-fill" style={{ width: `${Math.round(value * 100)}%`, background: color }} />
    </div>
  )
}

function LoginView({ onLogin }) {
  const [userId, setUserId] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    if (!userId.trim()) return setError('请输入用户 ID')
    setLoading(true)
    setError('')
    try {
      const { profile } = await api.login(userId.trim(), name.trim())
      onLogin(profile)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-card">
      <div className="login-icon">🎓</div>
      <h1>英语学习智能助手</h1>
      <p className="login-sub">自适应出题 · 学习记忆 · DeepSeek AI 答疑</p>
      <form onSubmit={submit}>
        <input
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          placeholder="用户 ID（如 xiaoming）"
          autoFocus
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="学生姓名（可选）"
        />
        {error && <div className="error-text">{error}</div>}
        <button type="submit" disabled={loading}>
          {loading ? '进入中…' : '开始学习'}
        </button>
      </form>
    </div>
  )
}

function QuestionCard({ question, selected, onSelect, textAnswer, setTextAnswer, onSubmit, loading }) {
  if (!question) return null
  const letters = ['A', 'B', 'C', 'D', 'E', 'F']
  return (
    <div className="card question-card">
      <div className="question-meta">
        <span className="badge cefr">{question.cefr}</span>
        {question.tags.map((t) => (
          <span key={t} className="badge tag">{t}</span>
        ))}
        <span className="difficulty">难度 {question.difficulty.toFixed(2)}</span>
      </div>
      <h2 className="stem">{question.stem}</h2>

      {question.is_choice ? (
        <div className="options">
          {question.options.map((opt, i) => (
            <button
              key={i}
              className={`option ${selected === i ? 'selected' : ''}`}
              onClick={() => onSelect(i)}
              disabled={loading}
            >
              <span className="option-letter">{letters[i]}</span>
              <span>{opt}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="free-answer">
          <input
            value={textAnswer}
            onChange={(e) => setTextAnswer(e.target.value)}
            placeholder="在此输入你的答案…"
            disabled={loading}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && textAnswer.trim()) onSubmit()
            }}
          />
        </div>
      )}

      <button
        className="primary-btn"
        disabled={loading || (question.is_choice ? selected === null : !textAnswer.trim())}
        onClick={onSubmit}
      >
        {loading ? 'AI 判分中…' : '提交答案'}
      </button>
    </div>
  )
}

function FeedbackPanel({ feedback, onNext }) {
  if (!feedback) return null
  return (
    <div className={`card feedback ${feedback.is_correct ? 'correct' : 'wrong'}`}>
      <div className="feedback-head">
        <span className="feedback-icon">{feedback.is_correct ? '✅' : '❌'}</span>
        <span className="feedback-title">
          {feedback.is_correct ? '回答正确！' : '回答错误'}
        </span>
      </div>
      {!feedback.is_correct && (
        <div className="correct-answer">正确答案：{String(feedback.correct_answer)}</div>
      )}
      <div className="feedback-explain">{feedback.explanation}</div>
      <button className="primary-btn" onClick={onNext}>下一题 →</button>
    </div>
  )
}

function ReportPanel({ profile }) {
  if (!profile) return null
  return (
    <div className="card report-card">
      <div className="report-stats">
        <div className="stat">
          <div className="stat-num">{profile.total}</div>
          <div className="stat-label">累计答题</div>
        </div>
        <div className="stat">
          <div className="stat-num">{profile.correct}</div>
          <div className="stat-label">答对次数</div>
        </div>
        <div className="stat">
          <div className="stat-num" style={{ color: LEVEL_COLORS[profile.level] }}>
            {profile.level}
          </div>
          <div className="stat-label">当前水平</div>
        </div>
      </div>

      {profile.skills.length > 0 ? (
        <table className="skill-table">
          <thead>
            <tr>
              <th>技能标签</th>
              <th>掌握度</th>
              <th>正/误</th>
              <th>下次复习</th>
            </tr>
          </thead>
          <tbody>
            {profile.skills.map((s) => (
              <tr key={s.tag}>
                <td className="tag-cell">{s.tag}</td>
                <td className="mastery-cell">
                  <MasteryBar value={s.mastery} />
                  <span>{s.mastery.toFixed(2)}</span>
                </td>
                <td className="mono">{s.correct}/{s.wrong}</td>
                <td className="mono dim">{s.next_review ? s.next_review.replace('T', ' ') : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="dim empty-tip">暂无技能数据，答题后自动生成学习报告。</p>
      )}
    </div>
  )
}

function ChatPanel({ userId }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const listRef = useRef(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const text = input.trim()
    if (!text || sending) return
    setMessages((m) => [...m, { role: 'user', text }])
    setInput('')
    setSending(true)
    try {
      const { reply } = await api.chat(userId, text)
      setMessages((m) => [...m, { role: 'ai', text: reply }])
    } catch (err) {
      setMessages((m) => [...m, { role: 'ai', text: `出错了：${err.message}` }])
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="card chat-card">
      <h3>💬 DeepSeek AI 答疑</h3>
      <div className="chat-list" ref={listRef}>
        {messages.length === 0 && (
          <div className="chat-empty dim">有问题可以问我，例如：“present perfect 和 past simple 有什么区别？”</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.text}
          </div>
        ))}
        {sending && <div className="bubble ai typing">AI 思考中…</div>}
      </div>
      <div className="chat-input">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder="输入问题…"
          disabled={sending}
        />
        <button onClick={send} disabled={sending || !input.trim()}>发送</button>
      </div>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(null) // profile 对象
  const [question, setQuestion] = useState(null)
  const [selected, setSelected] = useState(null)
  const [textAnswer, setTextAnswer] = useState('')
  const [feedback, setFeedback] = useState(null)
  const [advice, setAdvice] = useState(null)
  const [loadingQ, setLoadingQ] = useState(false)
  const [loadingA, setLoadingA] = useState(false)
  const [loadingAdvice, setLoadingAdvice] = useState(false)
  const [error, setError] = useState('')

  // 记录当前登录用户ID，用于丢弃切换用户后返回的过期异步响应
  const userIdRef = useRef(null)
  useEffect(() => {
    userIdRef.current = user?.user_id ?? null
  }, [user?.user_id])

  const loadQuestion = async () => {
    if (!user) return
    const uid = user.user_id
    setLoadingQ(true)
    setError('')
    setFeedback(null)
    setSelected(null)
    setTextAnswer('')
    try {
      const { question: q } = await api.nextQuestion(uid)
      if (userIdRef.current !== uid) return // 用户已切换，丢弃过期响应
      setQuestion(q)
    } catch (err) {
      if (userIdRef.current !== uid) return
      setError(err.message)
    } finally {
      if (userIdRef.current === uid) setLoadingQ(false)
    }
  }

  useEffect(() => {
    if (user) loadQuestion()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id])

  const submitAnswer = async () => {
    const ans = question.is_choice ? selected : textAnswer.trim()
    const uid = user.user_id
    setLoadingA(true)
    setError('')
    try {
      const res = await api.answer(uid, user.name, question.id, ans)
      if (userIdRef.current !== uid) return // 用户已切换，丢弃过期响应
      setFeedback(res)
      setUser(res.profile)
      setAdvice(null) // 档案已更新，清空旧建议
    } catch (err) {
      if (userIdRef.current !== uid) return
      // 题目过期/不存在（如服务重启后缓存丢失），自动获取新题目
      if (err.message.includes('请刷新')) {
        await loadQuestion()
        setError('题目已过期，已自动为你获取新题目')
      } else {
        setError(err.message)
      }
    } finally {
      if (userIdRef.current === uid) setLoadingA(false)
    }
  }

  const fetchAdvice = async () => {
    const uid = user.user_id
    setLoadingAdvice(true)
    try {
      const { advice: text } = await api.advice(uid)
      if (userIdRef.current !== uid) return
      setAdvice(text)
    } catch (err) {
      if (userIdRef.current !== uid) return
      setAdvice(`生成失败：${err.message}`)
    } finally {
      if (userIdRef.current === uid) setLoadingAdvice(false)
    }
  }

  const logout = () => {
    // 完整重置所有会话状态，确保切换用户后无残留
    setUser(null)
    setQuestion(null)
    setFeedback(null)
    setAdvice(null)
    setSelected(null)
    setTextAnswer('')
    setError('')
    setLoadingQ(false)
    setLoadingA(false)
    setLoadingAdvice(false)
  }

  if (!user) return <div className="app-bg"><LoginView onLogin={setUser} /></div>

  return (
    <div className="app-bg">
      <header className="topbar">
        <div className="topbar-title">🎓 英语学习智能助手</div>
        <div className="topbar-user">
          <span className="level-chip" style={{ background: LEVEL_COLORS[user.level] }}>
            {user.name} · {user.level}
          </span>
          <button className="ghost-btn" onClick={logout}>切换用户</button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <main className="layout">
        <section className="main-col">
          {!feedback && (
            loadingQ ? (
              <div className="card loading-card">正在为你选择合适的题目…</div>
            ) : (
              <QuestionCard
                question={question}
                selected={selected}
                onSelect={setSelected}
                textAnswer={textAnswer}
                setTextAnswer={setTextAnswer}
                onSubmit={submitAnswer}
                loading={loadingA}
              />
            )
          )}
          <FeedbackPanel feedback={feedback} onNext={loadQuestion} />

          <div className="advice-section">
            <button className="ghost-btn advice-btn" onClick={fetchAdvice} disabled={loadingAdvice}>
              {loadingAdvice ? 'AI 生成中…' : '🤖 获取 AI 学习建议'}
            </button>
            {advice && <div className="card advice-card">{advice}</div>}
          </div>
        </section>

        <aside className="side-col">
          <ReportPanel profile={user} />
          <ChatPanel key={user.user_id} userId={user.user_id} />
        </aside>
      </main>
    </div>
  )
}
