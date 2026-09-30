// 统一的 API 请求封装，开发模式下由 Vite 代理到 Flask 后端
async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `请求失败 (${res.status})`);
  }
  return data;
}

export const fetchConfig = () => request("/api/config");

export const runBacktest = (params) =>
  request("/api/backtest", {
    method: "POST",
    body: JSON.stringify(params),
  });

export const getDecision = (params) =>
  request("/api/decision", {
    method: "POST",
    body: JSON.stringify(params),
  });
