import { useState } from 'react'
import { askQuestion } from '../api.js'

export default function QAPage({ meta }) {
  const [question, setQuestion] = useState('')
  const [jurisdictions, setJurisdictions] = useState(['EU'])
  const [asOf, setAsOf] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState([])

  const options =
    meta?.jurisdictions?.map((j) => ({ value: j.code, label: j.name })) || [
      { value: 'EU', label: '欧盟' },
      { value: 'US-CA', label: '美国加利福尼亚州' },
    ]

  const toggle = (code) => {
    setJurisdictions((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code],
    )
  }

  const submit = async (e) => {
    e?.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setError('')
    try {
      const res = await askQuestion({
        question,
        jurisdictions,
        as_of: asOf || null,
      })
      setResult(res)
      setHistory((h) => [{ q: question, answer: res.answer }, ...h].slice(0, 5))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <section className="card">
        <h2>提出您的法规问题</h2>
        <p className="hint">系统将基于 GDPR / CCPA 演示语料进行检索增强问答（RAG），由 DeepSeek 生成带引用的回答。</p>
        <form onSubmit={submit}>
          <textarea
            className="textarea"
            rows={3}
            placeholder="例如：GDPR 对处理记录有什么规定？"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <div className="form-row">
            <div className="field">
              <label>司法辖区</label>
              <div className="chips">
                {options.map((o) => (
                  <button
                    type="button"
                    key={o.value}
                    className={`chip ${jurisdictions.includes(o.value) ? 'chip-on' : ''}`}
                    onClick={() => toggle(o.value)}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="field field-narrow">
              <label>时间点（可选）</label>
              <input
                type="date"
                className="input"
                value={asOf}
                onChange={(e) => setAsOf(e.target.value)}
              />
            </div>
          </div>
          <button className="btn btn-primary" disabled={loading || !question.trim()}>
            {loading ? '思考中…' : '提交问题'}
          </button>
        </form>
        {error && <div className="alert alert-error">{error}</div>}
      </section>

      {loading && <div className="card skeleton-card">正在检索语料并调用 DeepSeek 生成回答，请稍候…</div>}

      {result && !loading && (
        <section className="card result-card">
          <div className="result-header">
            <h2>回答</h2>
            <span className="badge badge-muted">置信度 {Math.round(result.confidence * 100)}%</span>
          </div>
          <div className="answer">{result.answer || '（未找到足够相关的语料，无法生成回答）'}</div>
          {result.citations?.length > 0 && (
            <>
              <h3>引用来源</h3>
              <div className="citations">
                {result.citations.map((c) => (
                  <div className="citation" key={c.chunk_id}>
                    <div className="citation-head">
                      <span className="citation-index">[{c.index}]</span>
                      <strong>{c.title}</strong>
                      {c.date && <span className="citation-date">{c.date}</span>}
                      <span className="citation-score">相关度 {c.score}</span>
                    </div>
                    <p className="citation-excerpt">{c.excerpt}…</p>
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      )}

      {history.length > 0 && (
        <section className="card">
          <h3>最近提问</h3>
          <ul className="history">
            {history.map((h, i) => (
              <li key={i}>
                <button className="history-item" onClick={() => setQuestion(h.q)}>
                  {h.q}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
