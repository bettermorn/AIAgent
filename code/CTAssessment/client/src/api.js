const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `请求失败 (${res.status})`);
  return data;
}

export const api = {
  getQuestionnaire: () => request('/assessments/questionnaire'),
  submit: (payload) => request('/assessments/submit', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  getAssessment: (id) => request(`/assessments/${id}`),
  getAdvice: (id) => request(`/assessments/${id}/advice`, { method: 'POST' }),
  listHistory: () => request('/assessments'),
};
