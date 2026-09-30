import { useEffect, useRef, useState } from 'react'

const SCORE_LABELS = {
  total: '总分',
  relevance: '相关性',
  completeness: '完整性',
  length_fit: '长度匹配',
  structure: '结构',
  redundancy: '冗余度',
}

const EXAMPLES = [
  '分析特斯拉2026年的发展战略和市场表现',
  '分析中国2026年的生物医药产业发展情况',
  '研究DeepSeek最新模型及其对行业的影响',
  '分析中国2026年的芯片人才市场情况',
  '分析中国2026年的AI发展情况', 
  '分析中国2026年的芯片产业发展情况',
]

async function fetchHealth() {
  try {
    const res = await fetch('/api/health')
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

// 读取 SSE 流（fetch + ReadableStream 手动解析）
async function streamGenerate(body, { onLog, onResult, onError }) {
  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    onError(`请求失败（HTTP ${res.status}）`)
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let currentEvent = 'message'

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() ?? ''

    for (const chunk of chunks) {
      let data = ''
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event:')) currentEvent = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      let payload
      try {
        payload = JSON.parse(data)
      } catch {
        continue
      }
      if (currentEvent === 'log') onLog(payload)
      else if (currentEvent === 'result') onResult(payload)
      else if (currentEvent === 'error') onError(payload)
    }
  }
}

function ScoreBar({ label, value }) {
  const pct = Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100)
  return (
    <div className="score-row">
      <span className="score-label">{label}</span>
      <div className="score-track">
        <div className="score-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className="score-value">{pct}%</span>
    </div>
  )
}

export default function App() {
  const [prompt, setPrompt] = useState('')
  const [steps, setSteps] = useState(5)
  const [targetWords, setTargetWords] = useState(800)
  const [targetScore, setTargetScore] = useState(0.86)
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [health, setHealth] = useState(null)
  const logEndRef = useRef(null)

  useEffect(() => {
    fetchHealth().then(setHealth)
  }, [])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const run = async () => {
    if (!prompt.trim() || running) return
    setRunning(true)
    setLogs([])
    setResult(null)
    setError('')
    await streamGenerate(
      {
        prompt: prompt.trim(),
        steps: Number(steps),
        target_words: Number(targetWords),
        target_score: Number(targetScore),
      },
      {
        onLog: (msg) => setLogs((prev) => [...prev, msg]),
        onResult: (data) => setResult(data),
        onError: (msg) => setError(String(msg)),
      },
    )
    setRunning(false)
  }

  return (
    <div className="page">
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-mark">SE</span>
            <div>
              <h1>自进化商业报告生成代理</h1>
              <p className="subtitle">DeepSeek · 互联网搜索 · 迭代自进化</p>
            </div>
          </div>
          {health && (
            <div className="health">
              <span className={`dot ${health.deepseek_configured ? 'ok' : 'bad'}`} />
              {health.model}
              {health.search_configured
                ? ` · 搜索已启用（${health.search_provider === 'google' ? 'Google' : '免费搜索'}）`
                : ' · 搜索未配置'}
            </div>
          )}
        </div>
      </header>

      <main className="main">
        <section className="card control-card">
          <h2>生成配置</h2>
          <label className="field">
            <span>报告主题 / 需求</span>
            <textarea
              rows={3}
              value={prompt}
              placeholder="例如：分析特斯拉2025年的发展战略和市场表现"
              onChange={(e) => setPrompt(e.target.value)}
            />
          </label>
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" className="chip" onClick={() => setPrompt(ex)}>
                {ex}
              </button>
            ))}
          </div>
          <div className="field-row">
            <label className="field">
              <span>迭代步数：{steps}</span>
              <input type="range" min="1" max="10" value={steps} onChange={(e) => setSteps(e.target.value)} />
            </label>
            <label className="field">
              <span>目标字数：{targetWords}</span>
              <input type="range" min="200" max="3000" step="100" value={targetWords} onChange={(e) => setTargetWords(e.target.value)} />
            </label>
          </div>
          <label className="field">
            <span>目标分数：{targetScore.toFixed(2)}</span>
            <input type="range" min="0.5" max="1" step="0.01" value={targetScore} onChange={(e) => setTargetScore(parseFloat(e.target.value))} />
          </label>
          <button className="run-btn" onClick={run} disabled={running || !prompt.trim()}>
            {running ? '生成中…' : '🚀 开始生成报告'}
          </button>
          {error && <div className="error">{error}</div>}
        </section>

        <section className="card log-card">
          <h2>实时过程</h2>
          <div className="log">
            {logs.length === 0 && !running && <p className="placeholder">开始后此处将显示代理的每一步反思、搜索与评分过程</p>}
            {logs.map((line, i) => (
              <div key={i} className={`log-line ${line.includes('得分') || line.includes('🎉') ? 'highlight' : ''}`}>
                {line}
              </div>
            ))}
            {running && <div className="log-line typing">●●● 代理思考中…</div>}
            <div ref={logEndRef} />
          </div>
        </section>

        {result && (
          <section className="card result-card">
            <h2>最终报告</h2>
            {result.best_score && (
              <div className="scores">
                <div className="total-score">
                  <span className="total-num">{(result.best_score.total ?? 0).toFixed(3)}</span>
                  <span className="total-cap">最佳得分</span>
                </div>
                <div className="score-bars">
                  {Object.entries(SCORE_LABELS)
                    .filter(([k]) => k !== 'total' && result.best_score?.[k] !== undefined)
                    .map(([k, label]) => (
                      <ScoreBar key={k} label={label} value={result.best_score[k]} />
                    ))}
                </div>
              </div>
            )}
            <article className="report">{result.summary || '（无内容）'}</article>
            {result.search_summary?.length > 0 && (
              <details className="search-details">
                <summary>搜索记录（{result.search_summary.length} 次）</summary>
                {result.search_summary.map((s, i) => (
                  <div key={i} className="search-item">
                    <strong>步骤 {s.step}：</strong>{s.query}
                    <ul>
                      {s.results?.map((r, j) => (
                        <li key={j}>
                          <a href={r.link} target="_blank" rel="noreferrer">{r.title}</a>
                          <p>{r.snippet}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </details>
            )}
          </section>
        )}
      </main>

      <footer className="footer">StrategyEvolution · DeepSeek 驱动的自进化商业报告生成代理</footer>
    </div>
  )
}
