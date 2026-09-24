import { useRef, useState } from 'react'
import { reviewFile, reviewText } from '../api.js'

const RISK_LABEL = { low: '低风险', medium: '中风险', high: '高风险' }
const ASSESS_LABEL = {
  有利: 'assess-good',
  中性: 'assess-neutral',
  不利: 'assess-bad',
  缺失: 'assess-missing',
}

export default function ContractPage() {
  const [mode, setMode] = useState('text')
  const [text, setText] = useState('')
  const [fileName, setFileName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef(null)

  const pickFile = (file) => {
    if (!file) return
    setFileName(file.name)
    setResult(null)
  }

  const submit = async (e) => {
    e?.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (mode === 'file') {
        const file = fileRef.current?.files?.[0]
        if (!file) throw new Error('请选择一个合同文件')
        setResult(await reviewFile(file))
      } else {
        if (!text.trim()) throw new Error('请粘贴合同文本')
        setResult(await reviewText(text))
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <section className="card">
        <h2>合同审查</h2>
        <p className="hint">上传合同文件（txt / md / pdf / docx）或直接粘贴文本，系统将提取关键条款并与基线条款（DPA）比较。</p>
        <div className="mode-switch">
          <button className={`chip ${mode === 'text' ? 'chip-on' : ''}`} onClick={() => setMode('text')}>
            粘贴文本
          </button>
          <button className={`chip ${mode === 'file' ? 'chip-on' : ''}`} onClick={() => setMode('file')}>
            上传文件
          </button>
        </div>
        <form onSubmit={submit}>
          {mode === 'text' ? (
            <textarea
              className="textarea"
              rows={8}
              placeholder="在此粘贴合同全文…"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          ) : (
            <div
              className={`dropzone ${dragOver ? 'dropzone-over' : ''}`}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault()
                setDragOver(false)
                if (e.dataTransfer.files?.[0]) {
                  const dt = new DataTransfer()
                  dt.items.add(e.dataTransfer.files[0])
                  if (fileRef.current) fileRef.current.files = dt.files
                  pickFile(e.dataTransfer.files[0])
                }
              }}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".txt,.md,.pdf,.doc,.docx"
                hidden
                onChange={(e) => pickFile(e.target.files?.[0])}
              />
              <p className="dropzone-icon">📄</p>
              {fileName ? (
                <p className="dropzone-name">{fileName}</p>
              ) : (
                <p>点击选择或拖拽合同文件到此处<br /><span className="hint">支持 .txt / .md / .pdf / .docx</span></p>
              )}
            </div>
          )}
          <button className="btn btn-primary" disabled={loading}>
            {loading ? '审查中…' : '开始审查'}
          </button>
        </form>
        {error && <div className="alert alert-error">{error}</div>}
      </section>

      {loading && <div className="card skeleton-card">DeepSeek 正在提取条款并进行比对分析，请稍候…</div>}

      {result && !loading && (
        <section className="card">
          <div className="result-header">
            <h2>审查结果</h2>
            <span className={`badge risk-${result.overall_risk}`}>
              {RISK_LABEL[result.overall_risk] || result.overall_risk}
            </span>
          </div>
          {result.summary && <p className="answer">{result.summary}</p>}
          <div className="clause-list">
            {result.clauses.map((c, i) => (
              <div className="clause-item" key={i}>
                <div className="clause-head">
                  <strong>{c.type}</strong>
                  <span className={`assess ${ASSESS_LABEL[c.assessment] || 'assess-neutral'}`}>
                    {c.assessment}
                  </span>
                </div>
                {c.excerpt && <p className="clause-excerpt">“{c.excerpt}”</p>}
                {c.issues?.length > 0 && (
                  <ul className="issue-list">
                    {c.issues.map((iss, j) => (
                      <li key={j}>{iss}</li>
                    ))}
                  </ul>
                )}
                {c.suggestions?.length > 0 && (
                  <ul className="suggest-list">
                    {c.suggestions.map((s, j) => (
                      <li key={j}>{s}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
