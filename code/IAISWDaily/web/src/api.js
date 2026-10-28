const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `请求失败 ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: () => request('/health'),
  channels: () => request('/channels'),
  settings: () => request('/settings'),
  saveSettings: (payload) => request('/settings', { method: 'PUT', body: JSON.stringify(payload) }),
  articles: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== '' && v !== null),
    ).toString();
    return request(`/articles?${qs}`);
  },
  stats: (days = 7) => request(`/stats?days=${days}`),
  latestReport: () => request('/reports/latest'),
  reports: (limit = 30) => request(`/reports?limit=${limit}`),
  report: (date) => request(`/reports/${date}`),
  runs: () => request('/runs'),
  runNow: (channels) => request('/runs', { method: 'POST', body: JSON.stringify({ channels }) }),
};
