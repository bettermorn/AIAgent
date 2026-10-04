import { config } from '../config.js';

// 统一的搜索结果结构
function normalize(item, source) {
  return {
    title: (item.title || '').slice(0, 200),
    url: item.url || item.link || '',
    snippet: (item.snippet || item.content || item.summary || item.description || '').slice(0, 500),
    source
  };
}

// Bocha AI 网络搜索（中文效果好，优先使用）
async function bochaSearch(query, count = 5) {
  if (!config.bochaApiKey) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch('https://api.bochaai.com/v1/web-search', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.bochaApiKey}`
      },
      body: JSON.stringify({ query, count, summary: true }),
      signal: controller.signal
    });
    if (!res.ok) throw new Error(`Bocha ${res.status}`);
    const data = await res.json();
    const pages = data?.data?.webPages?.value || [];
    return pages.map((p) => normalize({ title: p.name, url: p.url, snippet: p.snippet || p.summary }, 'Bocha'));
  } catch (err) {
    console.warn(`[search] Bocha 搜索失败: ${err.message}`);
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// SerpAPI Google 搜索
async function serpSearch(query, count = 5) {
  if (!config.serpapiKey) return null;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const url = new URL('https://serpapi.com/search.json');
    url.searchParams.set('q', query);
    url.searchParams.set('api_key', config.serpapiKey);
    url.searchParams.set('num', count);
    url.searchParams.set('hl', 'zh-cn');
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`SerpAPI ${res.status}`);
    const data = await res.json();
    const results = data.organic_results || [];
    return results.map((r) => normalize({ title: r.title, url: r.link, snippet: r.snippet }, 'SerpAPI'));
  } catch (err) {
    console.warn(`[search] SerpAPI 搜索失败: ${err.message}`);
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// 单条查询：Bocha 优先，失败/无Key时使用 SerpAPI
export async function searchWeb(query, count = 5) {
  const bocha = await bochaSearch(query, count);
  if (bocha && bocha.length > 0) return bocha;
  const serp = await serpSearch(query, count);
  return serp || [];
}

// 按维度生成学习资源搜索查询
export function buildSearchQueries(dimensions, weakPoints) {
  const queries = [
    '技术领导力 提升 书籍 推荐 2025',
    '技术管理者 团队管理 学习路线'
  ];
  const weakDims = dimensions.filter((d) => d.score !== null && d.score < 3.8);
  const dimQueryMap = {
    teamwork: '技术团队管理 授权激励 人员培养 最佳实践 方法论',
    sustainability: '技术人 持续学习 新技术 学习方法 知识分享',
    business: '技术 商业思维 业务理解 技术人转型 书籍',
    contribution: '技术贡献 开源 专业协会 专利 标准制定 如何参与'
  };
  for (const d of weakDims) {
    if (dimQueryMap[d.key]) queries.push(dimQueryMap[d.key]);
  }
  // 去重，最多5条查询
  return [...new Set(queries)].slice(0, 5);
}

// 批量搜索学习资源并整合为上下文
export async function searchLearningResources(dimensions) {
  const queries = buildSearchQueries(dimensions);
  const allResults = [];
  const searchTasks = queries.map(async (q) => {
    const results = await searchWeb(q, 4);
    return results.map((r) => ({ ...r, query: q }));
  });
  const settled = await Promise.allSettled(searchTasks);
  for (const s of settled) {
    if (s.status === 'fulfilled') allResults.push(...s.value);
  }
  return allResults;
}

export function formatSearchContext(results) {
  if (!results || results.length === 0) {
    return '（本次未获取到网络搜索结果，请主要依据知识库要点给出建议。）';
  }
  // 去重（按URL）
  const seen = new Set();
  const unique = results.filter((r) => {
    if (!r.url || seen.has(r.url)) return false;
    seen.add(r.url);
    return true;
  }).slice(0, 20);
  return unique
    .map((r, i) => `${i + 1}. 《${r.title}》\n   链接：${r.url}\n   摘要：${r.snippet}\n   来源：${r.source}｜搜索词：${r.query}`)
    .join('\n');
}
