const API_BASE = '/api'

async function request(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, options)
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(text || `请求失败 (${resp.status})`)
  }
  return resp.json()
}

export async function checkHealth() {
  return request('/health')
}

export async function sendChat(message, user) {
  return request('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      user: {
        user_id: user.userId || 'u1',
        name: user.name || 'You',
        safety_tier: 'normal',
      },
    }),
  })
}

export async function ingestText(text, source) {
  const form = new URLSearchParams()
  form.append('text', text)
  form.append('source', source)
  return request('/ingest/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form.toString(),
  })
}

export async function execTool(expr) {
  const form = new URLSearchParams()
  form.append('expr', expr)
  return request('/tool/exec', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form.toString(),
  })
}
