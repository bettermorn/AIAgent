// 调用后端 /api/chat，流式读取 SSE 返回
// 纯文本块        -> onDelta(delta)
// [TOOL] 块      -> onTool({ name, args })        （AI 决定调用工具）
// [TOOL_RESULT]  -> onToolResult({ name, result })(工具执行结果)
export async function streamChat(messages, { onDelta, onTool, onToolResult } = {}) {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, stream: true }),
  })

  if (!resp.ok) {
    let detail = `请求失败 (${resp.status})`
    try {
      const data = await resp.json()
      if (data.detail) detail = data.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const events = buffer.split('\n\n')
    buffer = events.pop() // 最后一段可能不完整，留到下一轮

    for (const evt of events) {
      const line = evt.trim()
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)

      if (payload === '[DONE]') return
      if (payload.startsWith('[ERROR]')) throw new Error(payload.slice(8))

      if (payload.startsWith('[TOOL] ')) {
        try {
          onTool?.(JSON.parse(payload.slice(7)))
        } catch {
          /* 忽略解析失败的工具事件 */
        }
        continue
      }

      if (payload.startsWith('[TOOL_RESULT] ')) {
        try {
          onToolResult?.(JSON.parse(payload.slice(13)))
        } catch {
          /* 忽略解析失败的工具结果事件 */
        }
        continue
      }

      onDelta?.(payload)
    }
  }
}
