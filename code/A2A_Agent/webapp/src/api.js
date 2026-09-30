// 与 FastAPI 网关通信的 API 封装
// 开发环境通过 Vite 代理访问 http://localhost:8080
const BASE = import.meta.env.VITE_API_BASE || ''

export async function fetchAgents() {
  const res = await fetch(`${BASE}/api/agents`)
  if (!res.ok) throw new Error(`获取 Agent 列表失败: ${res.status}`)
  return res.json()
}

export async function sendChat(agent, message) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent, message }),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}

export async function runPipeline(topic, count) {
  const res = await fetch(`${BASE}/api/pipeline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, count }),
  })
  if (!res.ok) throw new Error(`请求失败: ${res.status}`)
  return res.json()
}
