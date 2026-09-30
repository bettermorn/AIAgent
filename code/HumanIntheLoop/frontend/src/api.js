// 与后端 REST API 通信的封装。
// 通过 package.json 中的 "proxy" 字段，开发环境自动转发到 localhost:3001。

const BASE = process.env.REACT_APP_API_BASE || '/api';

async function request(path, opts = {}) {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    let detail = text;
    try {
      detail = JSON.parse(text).error || text;
    } catch (_) {}
    throw new Error(`${resp.status} ${resp.statusText}: ${detail}`);
  }
  return resp.json();
}

export const api = {
  health: () => request('/health'),
  listThreads: () => request('/threads'),
  createThread: (title) =>
    request('/threads', { method: 'POST', body: { title } }),
  getThread: (id) => request(`/threads/${id}`),
  deleteThread: (id) => request(`/threads/${id}`, { method: 'DELETE' }),
  renameThread: (id, title) =>
    request(`/threads/${id}`, { method: 'PATCH', body: { title } }),
  invoke: (id, messages) =>
    request(`/threads/${id}/invoke`, { method: 'POST', body: { messages } }),
  approve: (id, note) =>
    request(`/threads/${id}/approve`, { method: 'POST', body: { note } }),
  continue: (id) => request(`/threads/${id}/continue`, { method: 'POST' }),
  reject: (id, reason) =>
    request(`/threads/${id}/reject`, { method: 'POST', body: { reason } }),
  modify: (id, modifications, note) =>
    request(`/threads/${id}/modify`, {
      method: 'POST',
      body: { modifications, note },
    }),
  replay: (id, checkpointId) =>
    request(`/threads/${id}/replay`, {
      method: 'POST',
      body: { checkpoint_id: checkpointId },
    }),
  listCheckpoints: (id) => request(`/threads/${id}/checkpoints`),
  getCheckpoint: (id) => request(`/checkpoints/${id}`),
};
