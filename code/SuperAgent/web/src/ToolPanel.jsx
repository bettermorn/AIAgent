import { useState } from 'react'
import { execTool } from './api.js'

export default function ToolPanel() {
  const [expr, setExpr] = useState('sin(pi/2)+sqrt(9)')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleRun = async (e) => {
    e.preventDefault()
    if (!expr.trim() || loading) return
    setLoading(true)
    try {
      const res = await execTool(expr)
      setResult({ ok: true, msg: `${res.expr} = ${res.value}` })
    } catch (err) {
      setResult({ ok: false, msg: `失败：${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel">
      <h2>工具 · 安全计算</h2>
      <p className="desc">仅允许 math.* 函数与常见运算（后端沙箱求值）。</p>
      <form onSubmit={handleRun}>
        <label>
          表达式
          <input value={expr} onChange={(e) => setExpr(e.target.value)} placeholder="sin(pi/2)+sqrt(9)" />
        </label>
        <button type="submit" disabled={loading || !expr.trim()}>
          {loading ? '计算中…' : '求值'}
        </button>
      </form>
      {result && (
        <div className={`notice ${result.ok ? 'ok' : 'err'}`}>{result.msg}</div>
      )}
    </section>
  )
}
