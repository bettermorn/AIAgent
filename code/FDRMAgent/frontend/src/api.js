// 前端 API 客户端：REST + SSE（fetch 读取 text/event-stream）
const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `请求失败（${res.status}）`);
  return data;
}

export const api = {
  get: (p) => request(p),
  post: (p, body) => request(p, { method: 'POST', body }),
  patch: (p, body) => request(p, { method: 'PATCH', body }),
  del: (p) => request(p, { method: 'DELETE' }),
};

/** 调用智能体并实时接收事件；返回 AbortController 以便取消 */
export function streamAgent(path, body, onEvent) {
  const ctrl = new AbortController();
  (async () => {
    try {
      const res = await fetch(BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        onEvent({ type: 'error', error: data.error || `请求失败（${res.status}）` });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop();
        for (const part of parts) {
          const line = part.split('\n').find((l) => l.startsWith('data:'));
          if (!line) continue;
          try { onEvent(JSON.parse(line.slice(5).trim())); } catch { /* 忽略 */ }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') onEvent({ type: 'error', error: e.message });
    }
  })();
  return ctrl;
}

export const pct = (x, d = 2) => (x === null || x === undefined ? '-' : `${(x * 100).toFixed(d)}%`);
export const fmtTime = (t) => (t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '-');
export const AGENT_NAMES = { due_diligence: '授信尽调智能体', early_warning: '风险预警智能体', copilot: '风控助手' };
export const ACTOR_NAMES = {
  planner: '规划者', tool: '工具', calculator: '计算引擎', llm: '大模型', guardrail: '护栏', human: '人工', system: '系统',
};
