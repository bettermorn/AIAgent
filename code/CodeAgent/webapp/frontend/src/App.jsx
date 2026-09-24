import { useCallback, useEffect, useRef, useState } from 'react'

const STAGES = [
  { key: 'analyze', label: '分析', desc: '扫描代码库，理解上下文' },
  { key: 'plan', label: '规划', desc: 'DeepSeek 生成执行计划' },
  { key: 'dryrun', label: '试运行', desc: '在不改动文件的情况下验证计划' },
  { key: 'apply', label: '应用', desc: '将更改写入磁盘' },
  { key: 'verify', label: '验证', desc: '对修改后的文件做语法检查' },
]

function StageBar({ stages }) {
  return (
    <div className="stage-bar">
      {STAGES.map((s, i) => {
        const st = stages[s.key]
        return (
          <div key={s.key} className={`stage ${st || 'idle'}`}>
            <div className="stage-node">
              {st === 'done' ? '✓' : st === 'running' ? '⟳' : i + 1}
            </div>
            <div className="stage-meta">
              <div className="stage-label">{s.label}</div>
              <div className="stage-desc">{s.desc}</div>
            </div>
            {i < STAGES.length - 1 && <div className="stage-line" />}
          </div>
        )
      })}
    </div>
  )
}

function CodeBlock({ title, code, tone = 'plain' }) {
  if (!code) return null
  return (
    <div className={`code-block ${tone}`}>
      <div className="code-title">{title}</div>
      <pre>{code}</pre>
    </div>
  )
}

export default function App() {
  const [config, setConfig] = useState(null)
  const [path, setPath] = useState('')
  const [instruction, setInstruction] = useState('')
  const [apply, setApply] = useState(false)
  const [running, setRunning] = useState(false)
  const [stages, setStages] = useState({})
  const [logs, setLogs] = useState([])
  const [analysis, setAnalysis] = useState(null)
  const [plan, setPlan] = useState([])
  const [output, setOutput] = useState('')
  const [error, setError] = useState('')
  const [finished, setFinished] = useState(null)
  const logRef = useRef(null)

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => setConfig({ has_api_key: false, model: 'unavailable' }))
  }, [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  const handleRun = useCallback(async () => {
    if (!path.trim() || !instruction.trim() || running) return
    setRunning(true)
    setStages({})
    setLogs([])
    setAnalysis(null)
    setPlan([])
    setOutput('')
    setError('')
    setFinished(null)

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: path.trim(), instruction: instruction.trim(), apply }),
      })
      if (!res.ok || !res.body) throw new Error(`请求失败 (HTTP ${res.status})`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      // 解析 SSE 流
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop()
        for (const chunk of chunks) {
          const line = chunk.trim()
          if (!line.startsWith('data:')) continue
          let ev
          try {
            ev = JSON.parse(line.slice(5))
          } catch {
            continue
          }
          switch (ev.type) {
            case 'stage':
              setStages((s) => ({ ...s, [ev.stage]: ev.status }))
              break
            case 'log':
              setLogs((l) => [...l, ev.text])
              break
            case 'analyze':
              setAnalysis(ev.data)
              break
            case 'plan':
              setPlan(ev.steps || [])
              break
            case 'dryrun':
            case 'apply':
              setOutput(ev.text || '')
              break
            case 'verify':
              setOutput((prev) => prev + '\n\n## 验证结果\n' + (ev.data?.files || [])
                .map((f) => `[${f.status === 'passed' ? '通过' : '失败'}] ${f.file}` + (f.message ? `\n${f.message}` : ''))
                .join('\n'))
              break
            case 'error':
              setError(ev.message)
              setRunning(false)
              return
            case 'done':
              setFinished(ev.applied ? 'applied' : 'dryrun')
              setRunning(false)
              return
          }
        }
      }
      setRunning(false)
    } catch (e) {
      setError(String(e.message || e))
      setRunning(false)
    }
  }, [path, instruction, apply, running])

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="logo">{'</>'}</span>
          <div>
            <h1>智能编程助手</h1>
            <p>DeepSeek 驱动的自主代码智能体</p>
          </div>
        </div>
        {config && (
          <div className={`model-badge ${config.has_api_key ? '' : 'warn'}`}>
            <span className="dot" />
            {config.has_api_key
              ? `模型: ${config.model}`
              : '未检测到 DEEPSEEK_API_KEY'}
          </div>
        )}
      </header>

      <section className="card form-card">
        <div className="field">
          <label>项目路径</label>
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="/path/to/your/project"
            spellCheck={false}
          />
        </div>
        <div className="field">
          <label>指令</label>
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder='例如：将函数 "greeting" 重命名为 "say_hello"'
            rows={3}
          />
        </div>
        <div className="form-actions">
          <label className="checkbox">
            <input type="checkbox" checked={apply} onChange={(e) => setApply(e.target.checked)} />
            <span>应用更改（写入磁盘，否则仅试运行）</span>
          </label>
          <button
            className="btn-primary"
            onClick={handleRun}
            disabled={running || !path.trim() || !instruction.trim()}
          >
            {running ? '执行中…' : apply ? '执行并应用' : '开始执行'}
          </button>
        </div>
      </section>

      {(Object.keys(stages).length > 0 || running) && (
        <section className="card">
          <h2>执行进度</h2>
          <StageBar stages={stages} />
        </section>
      )}

      {error && (
        <section className="card error-card">
          <h2>出错了</h2>
          <p className="error-text">{error}</p>
        </section>
      )}

      {finished && (
        <section className={`card result-banner ${finished}`}>
          {finished === 'applied'
            ? '✓ 更改已成功应用并通过验证。完整日志已保存在项目 .smartcoder/logs 目录。'
            : '✓ 试运行完成，未修改任何文件。勾选「应用更改」后重新执行即可写入磁盘。'}
        </section>
      )}

      {analysis && (
        <section className="card">
          <h2>代码库分析</h2>
          <div className="summary-chips">
            <span className="chip">Python: {analysis.summary?.python ?? 0}</span>
            <span className="chip">JS/TS: {analysis.summary?.js_ts ?? 0}</span>
            <span className="chip">潜在问题: {analysis.summary?.issues ?? 0}</span>
          </div>
          <div className="file-list">
            {(analysis.files || []).map((f) => (
              <div key={f.path} className="file-item">
                <code>{f.path}</code>
                <div className="file-symbols">
                  {(f.classes || []).map((c) => (
                    <span key={c} className="symbol class">class {c}</span>
                  ))}
                  {(f.functions || []).map((fn) => (
                    <span key={fn} className="symbol fn">def {fn}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {plan.length > 0 && (
        <section className="card">
          <h2>DeepSeek 执行计划</h2>
          {plan.map((step, i) => (
            <div key={i} className="plan-step">
              <div className="plan-head">
                <span className="step-no">{i + 1}</span>
                <span className="step-action">{step.action}</span>
              </div>
              <p className="step-explain">{step.explain}</p>
              {step.args?.file && <div className="step-file">文件: <code>{step.args.file}</code></div>}
              <CodeBlock title="替换前" code={step.args?.old} tone="old" />
              <CodeBlock title="替换后" code={step.args?.new} tone="new" />
            </div>
          ))}
        </section>
      )}

      {output && (
        <section className="card">
          <h2>执行结果</h2>
          <pre className="output">{output}</pre>
        </section>
      )}

      {logs.length > 0 && (
        <section className="card">
          <h2>运行日志</h2>
          <div className="terminal" ref={logRef}>
            {logs.map((l, i) => (
              <div key={i} className="terminal-line">{l}</div>
            ))}
          </div>
        </section>
      )}

      <footer className="footer">
        工作流：分析 → 规划（DeepSeek）→ 试运行 → 应用 → 验证 · 失败自动重新规划（最多 3 次）
      </footer>
    </div>
  )
}
