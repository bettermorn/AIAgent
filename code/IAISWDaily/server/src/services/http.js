const DEFAULT_TIMEOUT = 20000;

/**
 * 带超时、重试的 JSON 请求
 */
export async function fetchJson(url, { method = 'GET', headers, body, timeout = DEFAULT_TIMEOUT, retries = 1 } = {}) {
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const res = await fetch(url, {
        method,
        headers: { 'User-Agent': 'IAISWDaily/1.0 (+research-agent)', ...headers },
        body,
        signal: controller.signal,
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} ${res.statusText} @ ${url}`);
      }
      return await res.json();
    } catch (err) {
      lastErr = err;
      if (attempt < retries) await sleep(500 * (attempt + 1));
    } finally {
      clearTimeout(timer);
    }
  }
  throw lastErr;
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * 解析各种格式的发布时间；无法解析返回 null
 */
export function parseDate(input) {
  if (!input) return null;
  if (input instanceof Date) return Number.isNaN(input.getTime()) ? null : input;
  if (typeof input === 'number') {
    const ms = input < 1e12 ? input * 1000 : input;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const s = String(input).trim();
  // "2026-10-20" / "2026/10/20" / "2026-10-20 10:00:00"
  const norm = s.replace(/\//g, '-');
  const d = new Date(norm);
  if (!Number.isNaN(d.getTime())) return d;
  // "3 hours ago" / "2天前"
  const relZh = s.match(/(\d+)\s*(分钟|小时|天|周|个月)前/);
  if (relZh) {
    const n = Number(relZh[1]);
    const unitMap = { 分钟: 6e4, 小时: 36e5, 天: 864e5, 周: 6048e5, 个月: 2592e6 };
    return new Date(Date.now() - n * (unitMap[relZh[2]] || 0));
  }
  const relEn = s.match(/(\d+)\s*(minute|hour|day|week|month)s?\s*ago/i);
  if (relEn) {
    const n = Number(relEn[1]);
    const unitMap = { minute: 6e4, hour: 36e5, day: 864e5, week: 6048e5, month: 2592e6 };
    return new Date(Date.now() - n * unitMap[relEn[2].toLowerCase()]);
  }
  return null;
}

export function withinDays(date, days) {
  if (!date) return true; // 无时间信息时保留，交由模型判断
  return Date.now() - date.getTime() <= days * 864e5;
}

export const todayStr = (tz = 'Asia/Shanghai') =>
  new Date().toLocaleDateString('en-CA', { timeZone: tz }); // YYYY-MM-DD
