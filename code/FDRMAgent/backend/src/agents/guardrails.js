// 护栏（Guardrails）：提示注入检测、外部文本隔离、输出数字核验、权限校验
import { TOOLS } from '../tools/registry.js';

const INJECTION_PATTERNS = [
  /忽略(之前|以上|前面|所有).{0,6}(指令|规则|提示)/,
  /ignore (all |the )?(previous|above|prior) (instructions|rules)/i,
  /(系统提示|system prompt)\s*[:：]/i,
  /直接(批准|通过|放款)/,
  /无需(人工)?复核/,
  /(将|把)\s*PD\s*(设为|改为)/i,
  /你现在是/,
];

export function detectInjection(text) {
  const hits = INJECTION_PATTERNS.filter((p) => p.test(String(text || ''))).map((p) => p.source);
  return { detected: hits.length > 0, patterns: hits };
}

/** 把外部文本包装为“数据”，并剔除疑似指令片段，避免被当作指令执行 */
export function quarantine(text) {
  const raw = String(text || '');
  const cleaned = raw
    .replace(/【[^】]*(指令|系统提示|批准|复核)[^】]*】/g, '［已屏蔽疑似注入内容］')
    .replace(/忽略(之前|以上|前面|所有)[^。]*。?/g, '［已屏蔽疑似注入内容］');
  return `<external_data>\n${cleaned}\n</external_data>`;
}

/** 规划结果校验：只允许白名单内的只读工具，强制补齐必需工具 */
export function validatePlan(plan) {
  const allowed = Object.keys(TOOLS);
  const steps = (Array.isArray(plan) ? plan : []).filter((s) => typeof s === 'string');
  const rejected = steps.filter((s) => !allowed.includes(s));
  const accepted = [...new Set(steps.filter((s) => allowed.includes(s) && TOOLS[s].permission === 'read'))];
  const added = allowed.filter((k) => TOOLS[k].required && !accepted.includes(k));
  return { steps: [...added, ...accepted].sort((a, b) => allowed.indexOf(a) - allowed.indexOf(b)), rejected, added };
}

function collectNumbers(obj, out = new Set()) {
  if (obj === null || obj === undefined) return out;
  if (typeof obj === 'number') {
    out.add(obj);
    out.add(Math.abs(obj));
    out.add(Number((obj * 100).toFixed(2)));
    out.add(Number((Math.abs(obj) * 100).toFixed(2)));
    return out;
  }
  if (typeof obj === 'string') {
    for (const m of obj.matchAll(/-?\d+(?:\.\d+)?/g)) out.add(Number(m[0]));
    return out;
  }
  if (Array.isArray(obj)) obj.forEach((v) => collectNumbers(v, out));
  else if (typeof obj === 'object') Object.values(obj).forEach((v) => collectNumbers(v, out));
  return out;
}

/**
 * 输出核验：报告中出现的关键数字必须能在证据中找到（允许四舍五入误差）。
 * 忽略年份、序号、阈值常量等小整数。
 */
export function verifyNumbers(text, evidence, extraAllowed = []) {
  const allowed = [...collectNumbers(evidence), ...extraAllowed];
  const found = [...String(text || '').matchAll(/-?\d+(?:\.\d+)?/g)].map((m) => Number(m[0]));
  const suspicious = [];
  for (const n of found) {
    if (Number.isInteger(n) && Math.abs(n) <= 12) continue;
    if (n >= 1990 && n <= 2100 && Number.isInteger(n)) continue;
    const ok = allowed.some((a) => {
      if (a === n) return true;
      const tol = Math.max(Math.abs(a) * 0.01, 0.051);
      return Math.abs(a - n) <= tol;
    });
    if (!ok) suspicious.push(n);
  }
  const uniq = [...new Set(suspicious)];
  return { passed: uniq.length === 0, checked: found.length, unverified: uniq };
}
