const BASE = import.meta.env.VITE_API_BASE || "/api";

export async function askQuestion({ question, user_id, patient }) {
  const res = await fetch(`${BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, user_id, patient }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`请求失败 (${res.status}) ${detail}`);
  }
  return res.json();
}

export async function checkHealth() {
  try {
    const res = await fetch(`${BASE}/healthz`);
    return res.ok;
  } catch {
    return false;
  }
}
