import React from 'react'

const INTENT_LABELS = {
  FAQ: { text: '知识问答', cls: 'badge-faq' },
  TICKET: { text: '工单', cls: 'badge-ticket' },
  COMPLAINT: { text: '投诉处理', cls: 'badge-complaint' },
  CHITCHAT: { text: '闲聊', cls: 'badge-chitchat' },
}

/** 将回答文本中的 [1] / 【1】 渲染为高亮的引用角标，悬停显示来源文件名 */
function renderWithCitations(text, indexToSource) {
  const parts = String(text ?? '').split(/(\[\d+\]|【\d+】)/g)
  return parts.map((part, i) => {
    const m = part.match(/^[\[【](\d+)[\]】]$/)
    if (m) {
      const src = indexToSource?.[Number(m[1])]
      return (
        <sup key={i} className="cite-ref" title={src ? `来源：${src}` : ''}>
          [{m[1]}]
        </sup>
      )
    }
    return <React.Fragment key={i}>{part}</React.Fragment>
  })
}

/** 将扁平的来源列表按文件分组 */
function groupByFile(sources) {
  const files = []
  const byName = new Map()
  for (const s of sources) {
    const name = s.source || '未知来源'
    if (!byName.has(name)) {
      const file = { name, chunks: [] }
      byName.set(name, file)
      files.push(file)
    }
    byName.get(name).chunks.push(s)
  }
  return files
}

export default function MessageBubble({ message }) {
  const { role, text, intent, ticketId, time, error, sources } = message
  const intentInfo = INTENT_LABELS[intent]

  // 引用编号 -> 文件名 映射，用于角标悬停提示
  const indexToSource = {}
  if (Array.isArray(sources)) {
    for (const s of sources) {
      indexToSource[s.index] = s.source
    }
  }
  const groupedFiles = Array.isArray(sources) ? groupByFile(sources) : []

  return (
    <div className={`msg-row msg-${role}`}>
      <div className="avatar">{role === 'user' ? '🧑' : '🤖'}</div>
      <div className={`bubble ${error ? 'bubble-error' : ''}`}>
        {intentInfo && (
          <span className={`badge ${intentInfo.cls}`}>{intentInfo.text}</span>
        )}
        {ticketId && (
          <span className="ticket-chip" title="点击复制工单号">
            🎫 工单 {ticketId}
          </span>
        )}
        <div className="bubble-text">{renderWithCitations(text, indexToSource)}</div>
        {groupedFiles.length > 0 && (
          <div className="sources-list">
            <div className="sources-title">
              📎 来源文件（{groupedFiles.length} 个）
            </div>
            {groupedFiles.map((f) => (
              <div
                key={f.name}
                className="source-item"
                title={f.chunks[0]?.snippet || ''}
              >
                <span className="source-name">{f.name}</span>
                <span className="source-chunks">
                  引用 {f.chunks.map((c) => `[${c.index}]`).join(' ')}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="bubble-time">{time}</div>
      </div>
    </div>
  )
}
