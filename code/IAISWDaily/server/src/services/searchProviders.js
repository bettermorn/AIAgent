import { config } from '../config.js';
import { fetchJson, parseDate, withinDays } from './http.js';
import { signWbi, biliHeaders } from './bilibiliWbi.js';
import { searchWechat } from './wechatProvider.js';
import { deepseekSearch, hasDeepSeekSearch } from './deepseekTools.js';

/**
 * 渠道说明
 * - international: 国际/国外网站（Google，SerpAPI；DeepSeek Search 兜底/并行）
 * - wechat       : 微信公众号文章（搜狗微信 → 博查 site:mp.weixin.qq.com；DeepSeek Search）
 * - bilibili     : B站视频（B站搜索 API → 博查 site:bilibili.com；DeepSeek Search）
 * - news         : 中文资讯站点（博查全网搜索；DeepSeek Search）
 */

const normalize = (item) => {
  const publishedAt = parseDate(item.publishedAt || item.date || item.pubdate);
  return {
    url: item.url,
    title: (item.title || '').trim(),
    source: item.source || null,
    snippet: (item.snippet || '').trim().slice(0, 1200),
    publishedAt,
    channel: item.channel,
    language: item.language || 'zh',
    keyword: item.keyword || null,
  };
};

/* ------------------------------ SerpAPI：国际站点 ------------------------------ */

async function searchSerpApi(keyword, { limit, windowDays }) {
  if (!config.search.serpapiKey) throw new Error('缺少 SERPAPI_API_KEY');
  const url = new URL('https://serpapi.com/search.json');
  url.searchParams.set('engine', 'google');
  url.searchParams.set('q', keyword);
  url.searchParams.set('num', String(limit));
  url.searchParams.set('hl', 'en');
  url.searchParams.set('gl', 'us');
  url.searchParams.set('tbs', windowDays <= 1 ? 'qdr:d' : windowDays <= 7 ? 'qdr:w' : 'qdr:m');
  url.searchParams.set('api_key', config.search.serpapiKey);

  const data = await fetchJson(url.toString(), { timeout: 25000 });
  if (data.error) throw new Error(data.error);
  const rows = [
    ...(data.organic_results || []).map((r) => ({
      url: r.link,
      title: r.title,
      snippet: r.snippet,
      source: r.source,
      date: r.date,
    })),
    ...(data.news_results || []).map((r) => ({
      url: r.link,
      title: r.title,
      snippet: r.snippet,
      source: r.source?.name || r.source,
      date: r.date,
    })),
  ];
  return rows
    .filter((r) => r.url && r.title)
    .map((r) => normalize({ ...r, channel: 'international', language: 'en', keyword }))
    .filter((r) => withinDays(r.publishedAt, windowDays));
}

/* -------------------------------- 博查：中文全网 -------------------------------- */

async function searchBocha(query, { limit = 10, windowDays = 3, channel = 'news', language = 'zh', keyword }) {
  if (!config.search.bochaKey) throw new Error('缺少 BOCHA_API_KEY');
  const freshness = windowDays <= 1 ? 'oneDay' : windowDays <= 7 ? 'oneWeek' : 'oneMonth';
  const data = await fetchJson('https://api.bochaai.com/v1/web-search', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${config.search.bochaKey}`,
    },
    body: JSON.stringify({ query, count: limit, freshness, summary: true }),
    timeout: 25000,
  });
  const pages = data?.data?.webPages?.value || [];
  return pages
    .filter((p) => p.url && p.name)
    .map((p) =>
      normalize({
        url: p.url,
        title: p.name,
        snippet: p.summary || p.snippet,
        source: p.siteName,
        date: p.dateLastCrawled || p.datePublished,
        channel,
        language,
        keyword,
      }),
    )
    .filter((r) => withinDays(r.publishedAt, windowDays));
}

/* ----------------------------------- B站视频 ----------------------------------- */

async function searchBilibili(keyword, { limit = 8, windowDays = 7 }) {
  const signed = await signWbi({
    search_type: 'video',
    keyword,
    order: 'pubdate',
    page: 1,
  });
  const url = new URL('https://api.bilibili.com/x/web-interface/search/type');
  for (const [k, v] of Object.entries(signed)) url.searchParams.set(k, String(v));

  const data = await fetchJson(url.toString(), {
    headers: await biliHeaders(),
    timeout: 20000,
  });
  if (data.code !== 0) throw new Error(`B站接口返回 code=${data.code} ${data.message || ''}`);
  const list = data?.data?.result || [];
  const strip = (s) => String(s || '').replace(/<[^>]+>/g, '');
  return list
    .slice(0, limit)
    .map((v) =>
      normalize({
        url: `https://www.bilibili.com/video/${v.bvid}`,
        title: strip(v.title),
        snippet: strip(v.description),
        source: `B站 · ${v.author}`,
        date: v.pubdate ? new Date(v.pubdate * 1000) : null,
        channel: 'bilibili',
        language: 'zh',
        keyword,
      }),
    )
    .filter((r) => withinDays(r.publishedAt, windowDays));
}

/* --------------------------- DeepSeek Search（/v1/tools/search） --------------------------- */

const DEEPSEEK_SITE_FILTER = {
  wechat: 'site:mp.weixin.qq.com',
  bilibili: 'site:bilibili.com',
};

/** 按渠道拼装搜索词：站点限定 / 语言限定 / 时间下限（query 上限 128 字符） */
function buildDeepSeekQuery(keyword, { channel, language, windowDays }) {
  const parts = [String(keyword || '').trim()].filter(Boolean);
  if (DEEPSEEK_SITE_FILTER[channel]) parts.push(DEEPSEEK_SITE_FILTER[channel]);
  else parts.push(language === 'en' ? 'lang:en' : 'lang:zh');

  const fits = (arr) => [...arr.join(' ')].length <= 128;
  if (config.deepseek.search.useAfter && windowDays > 0) {
    const after = new Date(Date.now() - windowDays * 864e5).toISOString().slice(0, 10);
    const withAfter = [...parts, `after:${after}`];
    if (fits(withAfter)) return withAfter.join(' ');
  }
  return fits(parts) ? parts.join(' ') : parts[0];
}

async function searchDeepSeek(keyword, { limit = 10, windowDays = 3, channel = 'news', language = 'zh' }) {
  const query = buildDeepSeekQuery(keyword, { channel, language, windowDays });
  const results = await deepseekSearch({
    query,
    count: limit,
    oriQuestion: keyword,
  });
  return results
    .filter((r) => r.url && r.title)
    .map((r) =>
      normalize({
        url: r.url,
        title: r.title,
        snippet: r.summary || r.snippet || r.content,
        source: r.site_name || null,
        date: r.date,
        channel,
        language,
        keyword,
      }),
    )
    .filter((r) => withinDays(r.publishedAt, windowDays));
}

/* ------------------------------- 演示数据（无 Key 时） ------------------------------- */

function mockResults(keyword, channel) {
  const now = Date.now();
  return [1, 2].map((i) =>
    normalize({
      url: `https://example.com/${channel}/${encodeURIComponent(keyword)}/${i}`,
      title: `[演示] ${keyword} 相关动态 ${i}（${channel}）`,
      snippet: `这是搜索渠道 ${channel} 针对关键词「${keyword}」的演示数据。请在 config.env 中配置对应搜索服务 API Key 后获取真实结果。`,
      source: 'demo',
      date: new Date(now - i * 3600e3),
      channel,
      language: channel === 'international' ? 'en' : 'zh',
      keyword,
    }),
  );
}

/* ---------------------------------- 渠道分发 ---------------------------------- */

export const CHANNEL_LABELS = {
  international: '国际/国外网站',
  wechat: '微信公众号',
  bilibili: 'B站',
  news: '中文资讯',
};

/**
 * @param {string} channel 渠道
 * @param {string} keyword 关键词
 */
export async function searchChannel(channel, keyword, { limit, windowDays }) {
  if (config.search.mock) return mockResults(keyword, channel);

  const language = channel === 'international' ? 'en' : 'zh';

  // 原有渠道实现（内部已含博查回退）
  const builtin = async () => {
    if (channel === 'international') {
      return searchSerpApi(keyword, { limit, windowDays });
    }
    if (channel === 'wechat') {
      try {
        return await searchWechat(keyword, { limit, windowDays });
      } catch (err) {
        console.warn(`[search] 搜狗微信不可用(${err.message})，回退博查检索`);
        return searchBocha(`${keyword} 微信公众号`, { limit, windowDays, channel, keyword });
      }
    }
    if (channel === 'bilibili') {
      try {
        return await searchBilibili(keyword, { limit, windowDays });
      } catch (err) {
        console.warn(`[search] B站接口不可用(${err.message})，回退博查检索`);
        return searchBocha(`${keyword} site:bilibili.com/video`, {
          limit,
          windowDays,
          channel: 'bilibili',
          keyword,
        });
      }
    }
    return searchBocha(keyword, { limit, windowDays, channel, keyword });
  };

  // DeepSeek Search（/v1/tools/search）
  const viaDeepSeek = async () => {
    if (!hasDeepSeekSearch()) return [];
    return searchDeepSeek(keyword, { limit, windowDays, channel, language });
  };

  const safe = async (fn, tag) => {
    try {
      return await fn();
    } catch (err) {
      console.warn(`[search] 渠道 ${channel} 关键词「${keyword}」${tag}失败: ${err.message}`);
      return [];
    }
  };

  const mode = config.deepseek.search.mode;
  try {
    if (mode === 'supplement' && hasDeepSeekSearch()) {
      const [own, ds] = await Promise.all([
        safe(builtin, '内置源'),
        safe(viaDeepSeek, 'DeepSeek'),
      ]);
      return [...own, ...ds];
    }
    if (mode === 'primary' && hasDeepSeekSearch()) {
      const ds = await safe(viaDeepSeek, 'DeepSeek');
      if (ds.length) return ds;
      return safe(builtin, '内置源');
    }
    // fallback（默认）：内置源无结果时由 DeepSeek 兜底
    const own = await safe(builtin, '内置源');
    if (own.length) return own;
    return safe(viaDeepSeek, 'DeepSeek');
  } catch (err) {
    console.warn(`[search] 渠道 ${channel} 关键词「${keyword}」失败: ${err.message}`);
    return [];
  }
}
