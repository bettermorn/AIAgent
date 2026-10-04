import { config } from '../config.js';
import { pool } from '../db.js';

// 互联网搜索服务：优先 SERPAPI，失败时回退到 BOCHA（博查）
export async function webSearch(query, { limit = 6, useCache = true } = {}) {
  if (useCache) {
    const cached = await pool.query('SELECT results FROM search_cache WHERE query = $1', [query]);
    if (cached.rows.length) return cached.rows[0].results;
  }

  let results = null;
  try {
    results = await searchSerpapi(query, limit);
  } catch (e) {
    console.warn('[search] SERPAPI 失败，回退到 BOCHA:', e.message);
  }
  if (!results) {
    try {
      results = await searchBocha(query, limit);
    } catch (e) {
      console.warn('[search] BOCHA 也失败:', e.message);
    }
  }

  if (!results) results = [];
  if (results.length && useCache) {
    await pool.query(
      'INSERT INTO search_cache (query, results) VALUES ($1, $2) ON CONFLICT (query) DO UPDATE SET results = $2',
      [query, JSON.stringify(results)]
    );
  }
  return results;
}

async function searchSerpapi(query, limit) {
  if (!config.search.serpapiKey) throw new Error('未配置 SERPAPI_API_KEY');
  const url = new URL('https://serpapi.com/search.json');
  url.searchParams.set('q', query);
  url.searchParams.set('hl', 'zh-cn');
  url.searchParams.set('num', String(limit));
  url.searchParams.set('api_key', config.search.serpapiKey);

  const res = await fetch(url);
  if (!res.ok) throw new Error(`SERPAPI HTTP ${res.status}`);
  const data = await res.json();
  return (data.organic_results || []).slice(0, limit).map((r) => ({
    title: r.title,
    snippet: r.snippet || '',
    url: r.link,
    source: 'SERPAPI',
  }));
}

async function searchBocha(query, limit) {
  if (!config.search.bochaApiKey) throw new Error('未配置 BOCHA_API_KEY');
  const res = await fetch('https://api.bochaai.com/v1/web-search', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${config.search.bochaApiKey}`,
    },
    body: JSON.stringify({ query, summary: true, count: limit }),
  });
  if (!res.ok) throw new Error(`BOCHA HTTP ${res.status}`);
  const data = await res.json();
  const pages = data?.data?.webPages?.value || [];
  return pages.slice(0, limit).map((r) => ({
    title: r.name,
    snippet: r.summary || r.snippet || '',
    url: r.url,
    source: 'BOCHA',
  }));
}
