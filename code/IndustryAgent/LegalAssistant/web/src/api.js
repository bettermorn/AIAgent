const BASE = ''

async function request(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, options)
  if (!resp.ok) {
    let detail = `请求失败 (${resp.status})`
    try {
      const data = await resp.json()
      if (data.detail) detail = data.detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return resp.json()
}

export function fetchHealth() {
  return request('/api/healthz')
}

export function fetchMeta() {
  return request('/api/meta')
}

export function askQuestion(payload) {
  return request('/api/qa', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function analyzeGap(payload) {
  return request('/api/compliance/gap', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function reviewFile(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/api/contracts/review', { method: 'POST', body: form })
}

export function reviewText(text) {
  const form = new FormData()
  form.append('text', text)
  return request('/api/contracts/review', { method: 'POST', body: form })
}
