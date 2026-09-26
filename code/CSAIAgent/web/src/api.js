const API_BASE = import.meta.env.VITE_API_BASE || '/api'

async function request(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`请求失败 (${res.status}) ${detail}`)
  }
  return res.json()
}

/** 调用 /chat 接口，返回 { intent, answer, ticket_id, meta } */
export function sendChat({ session_id, user_id, query }) {
  return request('/chat', { session_id, user_id, query })
}

/** 调用 /feedback 接口，返回 { ok: true } */
export function sendFeedback({ session_id, score, comment }) {
  return request('/feedback', { session_id, score, comment })
}
