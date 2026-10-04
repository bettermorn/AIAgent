const BASE = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      msg = data.error || msg;
    } catch { /* ignore */ }
    throw new Error(msg);
  }
  return res.json();
}

export const fetchQuestionnaire = () => request('/questionnaire');

export const submitAssessment = (payload) =>
  request('/assessments', { method: 'POST', body: JSON.stringify(payload) });

export const fetchAssessment = (id) => request(`/assessments/${id}`);

export const fetchAssessmentList = () => request('/assessments');

export const fetchHealth = () => request('/health');
