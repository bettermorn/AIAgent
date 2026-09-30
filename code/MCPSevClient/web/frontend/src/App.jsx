import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkBreaks from 'remark-breaks'
import { streamChat } from './api.js'

const SYSTEM_PROMPT = '你是 DeepSeek 智能助手，请用简体中文回答用户的问题，回答清晰、准确、有帮助。'

const WELCOME = {
  role: 'assistant',
  content: '你好！我是 **DeepSeek 智能助手** 🤖\n\n有什么可以帮你的吗？',
}

const SUGGESTIONS = [
  '请计算 (123 * 456 + 789) / 3 等于多少',
  '现在北京时间几点了？纽约时间呢？',
  '帮我生成一个 16 位的强密码',
  '今天北京天气怎么样？',
  '100 美元现在能换多少人民币？',
  '帮我搜索一下 MCP的概念',
  '帮我搜索一下 AI Agent 的最新进展',
]

function ThinkingIndicator() {
  return (
    <div className="msg-row msg-ai">
      <div className="avatar">🤖</div>
      <div className="bubble thinking-bubble">
        <span className="thinking-icon">💭</span>
        <span className="thinking-text">正在思考</span>
        <span className="thinking-dots">
          <span /><span /><span />
        </span>
      </div>
    </div>
  )
}

function ToolBubble({ msg }) {
  return (
    <div className="msg-row msg-ai">
      <div className="avatar">🤖</div>
      <div className="bubble tool-bubble">
        <div className="tool-title">🔧 AI 决定调用工具</div>
        <div className="tool-detail">
          <span className="tool-name">{msg.name}</span>
          <pre className="tool-args">{JSON.stringify(msg.args, null, 2)}</pre>
        </div>
        {msg.result !== undefined ? (
          <div className="tool-result">
            <span className="tool-result-label">执行结果</span>
            <pre className="tool-result-text">{msg.result}</pre>
          </div>
        ) : (
          <div className="tool-running">
            <span className="thinking-dots">
              <span /><span /><span />
            </span>
            <span>正在执行工具...</span>
          </div>
        )}
      </div>
    </div>
  )
}

// 规范化 Markdown 文本，修正模型输出的常见格式问题：
// 1. 回车换行：\r\n -> \n（配合 remark-breaks，段落内单个回车正常换行）
// 2. 空格：连续空格转不间断空格（\u00A0）保留显示；正文行首缩进保留，
//    且避免 4 空格缩进被误判为代码块；列表/引用/表格行不受影响
// 3. 标题：行中标题符拆分到独立行；"##标题" 补空格；标题前补空行确保独立成段
// 4. 正文：非特殊行原样保留，不误改
// 5. 表格：表格行紧跟正文时补空行，使其被正确识别为表格
// 6. 分隔符：--- / *** / ___ / - - - 等独立分隔线，前后补空行，渲染为 <hr>
//    （并避免 "段落\n---" 被解析为 setext 二级标题）
// 代码块（``` 围栏内）内容完全不做改写。
function normalizeMarkdown(text) {
  const NBSP = '\u00A0'
  const isFence = (s) => /^\s*(```|~~~)/.test(s)
  const isTableLine = (s) => /^\s*\|/.test(s) // 以 | 开头的表格行
  const isListItem = (s) => /^\s*([-*+]|\d+[.)])\s+/.test(s) // 列表项
  const isQuote = (s) => /^\s*>/.test(s) // 引用
  const isDivider = (s) => {
    const t = s.trim()
    // 排除表格分隔行 |---|---|（以 | 开头）
    return !!t && !t.startsWith('|') && /^([-*_])(\s*\1){2,}$/.test(t)
  }
  const isHeading = (s) => /^#{1,6}(\s|$)/.test(s.trim())

  // 保留正文中的连续空格（Markdown 默认会折叠为一个）
  // 仅匹配"非行首"位置的 2+ 连续空格，行首缩进由 preserveIndent 单独处理
  const preserveSpaces = (s) =>
    s.replace(/(\S)( +)/g, (m, ch, sp) => ch + (sp.length >= 2 ? NBSP.repeat(sp.length) : sp))

  // 保留正文行首缩进（Markdown 默认丢弃行首空格；4+ 空格还会变成代码块）
  const preserveIndent = (s) => {
    const m = s.match(/^( +)(\S.*)$/)
    if (!m) return s
    return NBSP.repeat(m[1].length) + m[2]
  }

  const lines = text.replace(/\r\n/g, '\n').split('\n')
  let inCode = false
  const out = []

  const prevLine = () => (out.length ? out[out.length - 1] : '')
  const pushBlankIfBusy = () => {
    if (prevLine().trim() !== '') out.push('')
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // 代码块围栏：原样保留，仅切换状态
    if (isFence(line)) {
      inCode = !inCode
      out.push(line)
      continue
    }
    if (inCode) {
      out.push(line)
      continue
    }

    // 行中间的标题符提升到新行：如 "结论如下 ## 总结" -> 两行
    // 行首标题符后补空格："##标题" -> "## 标题"
    const parts = line
      .replace(/([^\n])\s+(#{1,6})(?=\s*\S)/g, '$1\n$2')
      .split('\n')
      .map((p) => p.replace(/^(#{1,6})(?=[^\s#])/, '$1 '))

    for (const p of parts) {
      if (isHeading(p)) {
        // 标题前补空行，确保标题独立成段
        pushBlankIfBusy()
        out.push(p)
      } else if (isDivider(p)) {
        // 分隔线前后补空行，渲染为水平线 <hr>
        pushBlankIfBusy()
        out.push(p)
        const nxt = lines[i + 1]
        if (nxt !== undefined && nxt.trim() !== '') out.push('')
      } else if (isTableLine(p)) {
        // 表格首行紧跟正文时补空行，使其被识别为表格（表格行不做空格转换）
        if (prevLine().trim() !== '' && !isTableLine(prevLine())) out.push('')
        out.push(p)
      } else if (isListItem(p) || isQuote(p) || isTableLine(prevLine())) {
        // 列表 / 引用 / 表格后行：保持 Markdown 原生语义，不转换空格
        out.push(p)
      } else {
        // 普通正文：上一行是列表项时不处理行首缩进（保护列表续行/嵌套），
        // 否则先保留行首缩进，再保留行内连续空格
        let body = p
        if (!isListItem(prevLine())) body = preserveIndent(body)
        body = preserveSpaces(body)
        out.push(body)
      }
    }
  }

  return out.join('\n')
}

function MessageBubble({ msg }) {
  if (msg.role === 'tool') return <ToolBubble msg={msg} />
  const isUser = msg.role === 'user'
  return (
    <div className={`msg-row ${isUser ? 'msg-user' : 'msg-ai'}`}>
      <div className="avatar">{isUser ? '🧑' : '🤖'}</div>
      <div className="bubble">
        {isUser ? (
          <pre className="bubble-text">{msg.content}</pre>
        ) : (
          <div className="bubble-text md">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
              {normalizeMarkdown(msg.content)}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const [messages, setMessages] = useState([WELCOME])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [thinking, setThinking] = useState(false) // 等待首个字符到达
  const [status, setStatus] = useState('') // 顶部状态栏: 模型名 / 错误
  const [model, setModel] = useState('')
  const bottomRef = useRef(null)

  // 页面加载时检查后端配置状态
  useEffect(() => {
    fetch('/api/health')
      .then((r) => r.json())
      .then((d) => {
        setModel(d.model || 'deepseek-chat')
        setStatus(
          d.api_key_configured
            ? ''
            : '⚠️ 后端未配置 DEEPSEEK_API_KEY，请在项目根目录 config.env 中填写后重启服务',
        )
      })
      .catch(() => setStatus('⚠️ 无法连接后端服务，请确认后端已启动'))
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, thinking])

  async function send(text) {
    const content = (text ?? input).trim()
    if (!content || loading) return

    const userMsg = { role: 'user', content }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setLoading(true)
    setThinking(true) // 显示"正在思考"等待画面，直到首个字符到达
    setStatus('')

    let started = false

    try {
      await streamChat(
        // 只回传 user/assistant 消息（工具消息由后端在本次请求内闭环处理）
        [
          { role: 'system', content: SYSTEM_PROMPT },
          ...newMessages.filter((m) => m !== WELCOME && (m.role === 'user' || m.role === 'assistant')),
        ],
        {
          onDelta: (delta) => {
            if (!started) {
              // 首个字符到达：关闭等待画面，创建回答气泡
              started = true
              setThinking(false)
              setMessages((prev) => [...prev, { role: 'assistant', content: delta }])
            } else {
              setMessages((prev) => {
                const copy = [...prev]
                const last = copy[copy.length - 1]
                copy[copy.length - 1] = { ...last, content: last.content + delta }
                return copy
              })
            }
          },
          onTool: (tool) => {
            // AI 决定调用工具：结束当前回答气泡，插入工具调用消息
            // 执行状态由工具气泡内的"正在执行工具"指示器展示
            started = false
            setThinking(false)
            setMessages((prev) => [...prev, { role: 'tool', name: tool.name, args: tool.args }])
          },
          onToolResult: (res) => {
            // 工具执行完成：为对应的工具气泡填入执行结果
            setMessages((prev) => {
              const copy = [...prev]
              // 从后往前找同名的、还没有结果的工具消息
              for (let i = copy.length - 1; i >= 0; i--) {
                if (copy[i].role === 'tool' && copy[i].name === res.name && copy[i].result === undefined) {
                  copy[i] = { ...copy[i], result: res.result }
                  break
                }
              }
              return copy
            })
          },
        },
      )
    } catch (e) {
      setThinking(false)
      setMessages((prev) => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (!started) {
          copy.push({ role: 'assistant', content: `❌ ${e.message}` })
        } else if (!last.content) {
          copy[copy.length - 1] = { ...last, content: `❌ ${e.message}` }
        }
        return copy
      })
    } finally {
      setLoading(false)
      setThinking(false)
    }
  }

  function clearChat() {
    setMessages([WELCOME])
    setStatus('')
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <span className="logo">🤖</span>
          <div>
            <h1>DeepSeek 智能助手</h1>
            <p className="subtitle">{model ? `模型: ${model}` : 'React + FastAPI'}</p>
          </div>
        </div>
        <button className="btn-clear" onClick={clearChat} title="清空对话">
          🗑️ 清空对话
        </button>
      </header>

      {status && <div className="status-bar">{status}</div>}

      <main className="chat">
        {messages.map((m, i) => (
          <MessageBubble key={i} msg={m} />
        ))}
        {thinking && <ThinkingIndicator />}
        <div ref={bottomRef} />
      </main>

      {/* 建议问题：始终保留显示，对话中不隐藏（生成中禁用点击） */}
      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="chip" onClick={() => send(s)} disabled={loading}>
            {s}
          </button>
        ))}
      </div>

      <footer className="composer">
        <textarea
          value={input}
          placeholder="输入你的问题，点击“发送”按钮发送..."
          onChange={(e) => setInput(e.target.value)}
          rows={1}
        />
        <button className="btn-send" onClick={() => send()} disabled={loading || !input.trim()}>
          {loading ? '生成中...' : '发送 ➤'}
        </button>
      </footer>
    </div>
  )
}
