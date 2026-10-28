import { Router } from 'express';
import { config } from '../config.js';
import { getSettings, updateSettings } from '../db/settingsRepo.js';
import { listArticles, statsByChannel } from '../db/articlesRepo.js';
import { getLatestReport, getReport, listReports, listRuns } from '../db/reportsRepo.js';
import { runPipeline, isRunning, getRunHistory } from '../services/pipeline.js';
import { reloadScheduler, nextRunInfo } from '../services/scheduler.js';
import { hasLLM } from '../services/summarizer.js';
import { CHANNEL_LABELS } from '../services/searchProviders.js';
import { hasDeepSeekSearch, hasDeepSeekFetch } from '../services/deepseekTools.js';
import { todayStr } from '../services/http.js';
import { healthCheck } from '../db/pool.js';

export const apiRouter = Router();

const asyncHandler = (fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);

apiRouter.get('/health', asyncHandler(async (req, res) => {
  let db = false;
  try {
    db = await healthCheck();
  } catch { /* noop */ }
  res.json({
    ok: true,
    db,
    llm: hasLLM(),
    search: {
      serpapi: Boolean(config.search.serpapiKey),
      bocha: Boolean(config.search.bochaKey),
      deepseek: hasDeepSeekSearch(),
      deepseekMode: hasDeepSeekSearch() ? config.deepseek.search.mode : 'off',
      fetch: hasDeepSeekFetch(),
      mock: config.search.mock,
    },
    schedule: nextRunInfo(),
    time: new Date().toISOString(),
  });
}));

apiRouter.get('/channels', (req, res) => {
  res.json(Object.entries(CHANNEL_LABELS).map(([key, label]) => ({ key, label })));
});

/* ------------------------------- 配置 ------------------------------- */

apiRouter.get('/settings', asyncHandler(async (req, res) => {
  const settings = await getSettings();
  res.json({ settings, schedule: nextRunInfo() });
}));

apiRouter.put('/settings', asyncHandler(async (req, res) => {
  const body = req.body || {};
  const patch = {};
  if (Array.isArray(body.keywordsZh)) patch.keywordsZh = body.keywordsZh.map(String).filter(Boolean);
  if (Array.isArray(body.keywordsEn)) patch.keywordsEn = body.keywordsEn.map(String).filter(Boolean);
  if (Array.isArray(body.channels)) {
    patch.channels = body.channels.filter((c) => Object.keys(CHANNEL_LABELS).includes(c));
  }
  if (body.cron) patch.cron = String(body.cron);
  if (body.timezone) patch.timezone = String(body.timezone);
  if (body.windowDays !== undefined) patch.windowDays = Number(body.windowDays);
  if (body.perKeywordLimit !== undefined) patch.perKeywordLimit = Number(body.perKeywordLimit);

  const settings = await updateSettings(patch);
  await reloadScheduler();
  res.json({ settings, schedule: nextRunInfo() });
}));

/* ------------------------------- 文章 ------------------------------- */

apiRouter.get('/articles', asyncHandler(async (req, res) => {
  const { channel, keyword, q, days, onlySummarized, includeIrrelevant } = req.query;
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  const offset = Number(req.query.offset) || 0;
  const data = await listArticles({
    limit,
    offset,
    channel,
    keyword,
    q,
    days: days ? Number(days) : undefined,
    onlySummarized: onlySummarized === 'true',
    includeIrrelevant: includeIrrelevant === 'true',
  });
  res.json(data);
}));

apiRouter.get('/stats', asyncHandler(async (req, res) => {
  const days = Number(req.query.days) || 7;
  const byChannel = await statsByChannel(days);
  const total = byChannel.reduce((s, c) => s + Number(c.count), 0);
  res.json({ days, total, byChannel });
}));

/* ------------------------------- 日报 ------------------------------- */

apiRouter.get('/reports', asyncHandler(async (req, res) => {
  res.json({ items: await listReports(Number(req.query.limit) || 30) });
}));

apiRouter.get('/reports/latest', asyncHandler(async (req, res) => {
  const report = await getLatestReport();
  res.json({ report, today: todayStr() });
}));

apiRouter.get('/reports/:date', asyncHandler(async (req, res) => {
  const report = await getReport(req.params.date);
  if (!report) return res.status(404).json({ error: '未找到该日期的日报' });
  res.json({ report });
}));

/* ------------------------------- 采集任务 ------------------------------- */

apiRouter.get('/runs', asyncHandler(async (req, res) => {
  res.json({ items: await getRunHistory(Number(req.query.limit) || 20), running: isRunning() });
}));

apiRouter.post('/runs', asyncHandler(async (req, res) => {
  if (isRunning()) return res.status(409).json({ error: '已有采集任务正在运行' });
  const channels = Array.isArray(req.body?.channels) ? req.body.channels : undefined;
  // 立即返回，任务后台执行
  res.status(202).json({ accepted: true, running: true });
  runPipeline({ trigger: 'manual', channels }).catch((err) => {
    console.error('[api] 手动采集失败:', err.message);
  });
}));
