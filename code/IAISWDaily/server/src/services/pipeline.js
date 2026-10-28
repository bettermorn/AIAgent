import { randomUUID } from 'node:crypto';
import { searchChannel, CHANNEL_LABELS } from './searchProviders.js';
import { summarizeArticles, buildDailyReport, hasLLM } from './summarizer.js';
import { enrichArticlesWithFetch, hasDeepSeekFetch } from './deepseekTools.js';
import { todayStr } from './http.js';
import {
  upsertArticles,
  updateArticleAnalysis,
  getArticlesByIds,
  getArticlesCollectedToday,
  statsByChannel,
} from '../db/articlesRepo.js';
import { createRun, finishRun, listRuns, upsertReport } from '../db/reportsRepo.js';
import { getSettings } from '../db/settingsRepo.js';

let running = false;

export const isRunning = () => running;

/**
 * 执行一次完整的“搜索 -> 入库 -> DeepSeek 总结 -> 生成日报”
 */
export async function runPipeline({ trigger = 'schedule', channels } = {}) {
  if (running) {
    return { skipped: true, reason: '已有采集任务正在运行' };
  }
  running = true;
  const runId = randomUUID();
  const started = Date.now();

  try {
    const settings = await getSettings();
    const windowDays = Number(settings.windowDays) || 3;
    const limit = Number(settings.perKeywordLimit) || 8;
    const activeChannels = (channels?.length ? channels : settings.channels || []).filter((c) =>
      Object.keys(CHANNEL_LABELS).includes(c),
    );

    const plan = [];
    for (const channel of activeChannels) {
      const keywords = channel === 'international' ? settings.keywordsEn : settings.keywordsZh;
      for (const kw of keywords || []) plan.push({ channel, keyword: kw });
    }
    const allKeywords = [...new Set(plan.map((p) => p.keyword))];

    await createRun({ id: runId, channels: activeChannels, keywords: allKeywords });
    console.log(`[run ${runId.slice(0, 8)}] 开始采集：${plan.length} 个检索任务，窗口 ${windowDays} 天`);

    // 1) 并发搜索（控制并发，避免触发限流）
    const results = [];
    const queue = [...plan];
    const workers = Array.from({ length: 4 }, async () => {
      while (queue.length) {
        const task = queue.shift();
        if (!task) return;
        const items = await searchChannel(task.channel, task.keyword, { limit, windowDays });
        results.push(...items);
        await new Promise((r) => setTimeout(r, 300));
      }
    });
    await Promise.all(workers);

    // 2) 去重入库（URL 相同 或 标题归一化后相同 视为重复）
    const seenUrl = new Set();
    const seenTitle = new Set();
    const unique = [];
    for (const item of results) {
      if (!item.url || !item.title) continue;
      const titleKey = item.title.replace(/[\s\p{P}]/gu, '').toLowerCase().slice(0, 60);
      if (seenUrl.has(item.url) || seenTitle.has(titleKey)) continue;
      seenUrl.add(item.url);
      seenTitle.add(titleKey);
      unique.push(item);
    }
    const { inserted, newIds } = await upsertArticles(unique.map((a) => ({ ...a, runId })));
    console.log(`[run ${runId.slice(0, 8)}] 检索 ${results.length} 条，去重 ${unique.length} 条，新增 ${inserted} 条`);

    // 3) DeepSeek Fetch 补充正文（摘要过短时）+ 总结
    let summarized = 0;
    if (newIds.length) {
      const rows = await getArticlesByIds(newIds);
      if (hasDeepSeekFetch()) {
        try {
          const enriched = await enrichArticlesWithFetch(rows);
          if (enriched) console.log(`[run ${runId.slice(0, 8)}] Fetch 补充正文 ${enriched} 条`);
        } catch (err) {
          console.warn(`[run ${runId.slice(0, 8)}] Fetch 补充正文失败: ${err.message}`);
        }
      }
      const analysis = await summarizeArticles(rows);
      for (const row of rows) {
        const a = analysis.get(Number(row.id));
        if (!a) continue;
        await updateArticleAnalysis(row.id, a);
        summarized += 1;
      }
    }
    console.log(`[run ${runId.slice(0, 8)}] 完成总结 ${summarized} 条（LLM ${hasLLM() ? '已启用' : '未配置，使用规则摘要'}）`);

    // 4) 生成日报（覆盖当天全部相关条目，便于一天内多次运行时补充更新）
    const newOnes = await getArticlesByIds(newIds);
    const dropped = newOnes.filter((a) => a.relevant === false).length;
    if (dropped > 0) console.log(`[run ${runId.slice(0, 8)}] 过滤无关条目 ${dropped} 条`);

    const date = todayStr(settings.timezone || 'Asia/Shanghai');
    const fresh = await getArticlesCollectedToday(settings.timezone || 'Asia/Shanghai');
    const report = await buildDailyReport(fresh, { date });
    const saved = await upsertReport({
      reportDate: date,
      title: report.title,
      overview: report.overview,
      highlights: report.highlights,
      trends: report.trends,
      byChannel: report.byChannel,
      articleCount: fresh.length,
      runId,
    });

    const byChannel = await statsByChannel(windowDays);
    await finishRun(runId, {
      status: 'success',
      collectedCount: results.length,
      insertedCount: inserted,
    });

    console.log(`[run ${runId.slice(0, 8)}] 完成，用时 ${((Date.now() - started) / 1000).toFixed(1)}s`);
    return {
      runId,
      collected: results.length,
      inserted,
      summarized,
      report: saved,
      byChannel,
      trigger,
    };
  } catch (err) {
    console.error(`[run ${runId.slice(0, 8)}] 失败:`, err);
    await finishRun(runId, { status: 'failed', error: err.message }).catch(() => {});
    throw err;
  } finally {
    running = false;
  }
}

export async function getRunHistory(limit = 20) {
  return listRuns(limit);
}
