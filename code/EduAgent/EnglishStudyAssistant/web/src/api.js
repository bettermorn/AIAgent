// 后端 API 封装（开发模式经 Vite 代理转发到 FastAPI）
const BASE = '/api'

async function handle(res) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `请求失败 (${res.status})`)
  }
  return res.json()
}

function post(path, body) {
  return fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(handle)
}

export const api = {
  login: (userId, name) => post('/session', { user_id: userId, name }),

  nextQuestion: (userId) =>
    fetch(`${BASE}/question/${encodeURIComponent(userId)}`).then(handle),

  answer: (userId, name, questionId, answer) =>
    post('/answer', { user_id: userId, name, question_id: questionId, answer }),

  report: (userId) =>
    fetch(`${BASE}/report/${encodeURIComponent(userId)}`).then(handle),

  advice: (userId) =>
    fetch(`${BASE}/advice/${encodeURIComponent(userId)}`).then(handle),

  chat: (userId, message) => post('/chat', { user_id: userId, message }),
}
