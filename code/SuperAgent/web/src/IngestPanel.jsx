import { useState } from 'react'
import { ingestText } from './api.js'

export default function IngestPanel() {
  const [text, setText] = useState('')
  const [source, setSource] = useState('user_note.txt')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!text.trim() || loading) return
    setLoading(true)
    try {
      const res = await ingestText(text, source || 'user_note.txt')
      setResult({ ok: true, msg: `已索引 ${res.indexed}（${res.len} 字符）` })
      setText('')
    } catch (err) {
      setResult({ ok: false, msg: `失败：${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel">
      <h2>知识库索引</h2>
      <p className="desc">将文本写入 RAG 向量库，对话时可作为检索证据被引用。</p>
      <form onSubmit={handleSubmit}>
        <label>
          来源名称
          <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="user_note.txt" />
        </label>
        <label>
          文本内容
          <textarea rows={6} value={text} onChange={(e) => setText(e.target.value)} placeholder="粘贴需要索引的文本…" />
        </label>
        <button type="submit" disabled={loading || !text.trim()}>
          {loading ? '索引中…' : '写入索引'}
        </button>
      </form>
      {result && (
        <div className={`notice ${result.ok ? 'ok' : 'err'}`}>{result.msg}</div>
      )}
    </section>
  )
}
