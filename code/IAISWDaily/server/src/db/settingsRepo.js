import { query } from './pool.js';
import { config, defaultKeywords } from '../config.js';

const DEFAULTS = {
  keywordsZh: defaultKeywords.zh,
  keywordsEn: defaultKeywords.en,
  channels: ['international', 'wechat', 'bilibili', 'news'],
  cron: config.schedule.cron,
  timezone: config.schedule.timezone,
  windowDays: config.collect.windowDays,
  perKeywordLimit: config.collect.perKeywordLimit,
};

export async function seedDefaultSettings() {
  for (const [key, value] of Object.entries(DEFAULTS)) {
    await query(
      `INSERT INTO settings (key, value) VALUES ($1, $2)
       ON CONFLICT (key) DO NOTHING`,
      [key, JSON.stringify(value)],
    );
  }
}

export async function getSettings() {
  const { rows } = await query('SELECT key, value FROM settings');
  const out = {};
  for (const row of rows) out[row.key] = row.value;
  // 兜底：缺失项使用默认值
  for (const [key, value] of Object.entries(DEFAULTS)) {
    if (out[key] === undefined) out[key] = value;
  }
  return out;
}

export async function getSetting(key) {
  const { rows } = await query('SELECT value FROM settings WHERE key = $1', [key]);
  return rows[0]?.value;
}

export async function updateSettings(patch) {
  const allowed = Object.keys(DEFAULTS);
  for (const [key, value] of Object.entries(patch)) {
    if (!allowed.includes(key)) continue;
    await query(
      `INSERT INTO settings (key, value, updated_at) VALUES ($1, $2, now())
       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()`,
      [key, JSON.stringify(value)],
    );
  }
  return getSettings();
}
