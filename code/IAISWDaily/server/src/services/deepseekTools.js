import { config } from '../config.js';
import { sleep } from './http.js';

/**
 * DeepSeek Search / Fetch 工具封装
 * - Search: POST {baseUrl}/v1/tools/search   按 query 检索网页，返回结构化结果
 * - Fetch : POST {baseUrl}/v1/tools/fetch    抓取单个网页，返回 Markdown 正文
 *
 * 文档：https://api-docs.deepseek.com/zh-cn/guides/search/
 * 说明：两者均为只读接口；遇 408 / 429 / 5xx 可等待后重试，其它 4xx 不重试。
 */

const MAX_QUERY_CHARS = 128;
const MAX_URL_CHARS = 8192;
const MAX_CONTENT_CHARS = 6000;

const base = () => config.deepseek.baseUrl.replace(/\/$/, '');
const SEARCH_URL = () => `${base()}/v1/tools/search`;
const FETCH_URL = () => `${base()}/v1/tools/fetch`;

export const SEARCH_MODES = ['off', 'fallback', 'primary', 'supplement'];

export const hasDeepSeekSearch = () =>
  Boolean(config.deepseek.apiKey) &&
  config.deepseek.search.enabled &&
  config.deepseek.search.mode !== 'off';

export const hasDeepSeekFetch = () => Boolean(config.deepseek.apiKey) && config.deepseek.fetch.enabled;

/**
 * 带重试的 JSON POST；仅 408 / 429 / 5xx / 网络错误重试
 */
async function postJson(url, payload, { timeout, retries = 2 } = {}) {
  let lastErr;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${config.deepseek.apiKey}`,
        },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const text = await res.text().catch(() => '');
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch { /* 非 JSON 响应，按文本处理 */ }

      if (!res.ok) {
        const message = data?.error?.message || text.slice(0, 200) || res.statusText;
        const err = new Error(`DeepSeek ${res.status}: ${message}`);
        err.status = res.status;
        throw err;
      }
      return data || {};
    } catch (err) {
      lastErr = err;
      const status = err.status;
      const retryable =
        err.name === 'AbortError' ||
        err.name === 'TypeError' ||
        status === 408 ||
        status === 429 ||
        (typeof status === 'number' && status >= 500);
      if (attempt < retries && retryable) {
        await sleep(800 * (attempt + 1));
        continue;
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }
  throw lastErr;
}

/**
 * 网页搜索（DeepSeek 自研搜索引擎）
 * @param {object} params
 * @param {string} params.query       搜索词，1~128 Unicode 字符，支持 site: / lang: / after: 等语法
 * @param {number} [params.count]     返回条数 1~50，默认 10
 * @param {boolean} [params.needContent] 是否返回网页正文
 * @param {string} [params.oriQuestion]  触发搜索的原始问题，帮助理解意图
 * @param {string} [params.localization] 用于本地化结果的 IP
 * @returns {Promise<Array<object>>} results 数组
 */
export async function deepseekSearch({
  query,
  count = 10,
  needContent,
  oriQuestion,
  localization,
  timeout,
} = {}) {
  const q = String(query || '').trim();
  const len = [...q].length;
  if (!len) throw new Error('DeepSeek Search: query 不能为空');
  if (len > MAX_QUERY_CHARS) throw new Error(`DeepSeek Search: query 超过 ${MAX_QUERY_CHARS} 字符（当前 ${len}）`);

  const body = {
    query: q,
    count: Math.min(Math.max(Number(count) || 10, 1), 50),
  };
  if (needContent ?? config.deepseek.search.needContent) body.need_content = true;
  if (oriQuestion) {
    const oq = String(oriQuestion).trim();
    if (oq && [...oq].length <= MAX_QUERY_CHARS) body.ori_question = oq;
  }
  if (localization) body.localization = String(localization);

  const data = await postJson(SEARCH_URL(), body, {
    timeout: timeout ?? config.deepseek.search.timeout,
    retries: config.deepseek.search.retries,
  });
  return Array.isArray(data.results) ? data.results : [];
}

/**
 * 抓取单个网页，返回 Markdown 正文
 * @param {string} url 必须为含 host 的 http/https 地址，长度 <= 8192
 * @returns {Promise<{title: string, content: string}>}
 */
export async function deepseekFetchPage(url, { timeout } = {}) {
  const target = String(url || '').trim();
  if (!/^https?:\/\/[^/\s]+/i.test(target)) throw new Error(`DeepSeek Fetch: 非法 URL ${url}`);
  if (target.length > MAX_URL_CHARS) throw new Error(`DeepSeek Fetch: URL 超过 ${MAX_URL_CHARS} 字符`);

  const data = await postJson(FETCH_URL(), { url: target }, {
    timeout: timeout ?? config.deepseek.fetch.timeout,
    retries: config.deepseek.fetch.retries,
  });
  return { title: String(data.title || ''), content: String(data.content || '') };
}

/**
 * 用 Fetch 接口补充过短摘要条目的正文，提升后续总结质量（仅内存增强，不落库）
 * @param {Array<object>} articles 文章行，snippet 会被就地替换
 * @returns {Promise<number>} 成功补充的条数
 */
export async function enrichArticlesWithFetch(articles, { limit, minSnippet } = {}) {
  const maxItems = limit ?? config.deepseek.fetch.limit;
  const threshold = minSnippet ?? config.deepseek.fetch.minSnippet;
  if (!hasDeepSeekFetch() || !maxItems || !Array.isArray(articles) || !articles.length) return 0;

  const targets = articles
    .filter((a) => a?.url && /^https?:\/\//i.test(a.url))
    .filter((a) => String(a.snippet || '').length < threshold)
    .slice(0, maxItems);

  let enriched = 0;
  const queue = [...targets];
  const workerCount = Math.min(config.deepseek.fetch.concurrency, queue.length);
  const workers = Array.from({ length: workerCount }, async () => {
    while (queue.length) {
      const item = queue.shift();
      if (!item) return;
      try {
        const { content } = await deepseekFetchPage(item.url);
        if (content && content.length > String(item.snippet || '').length) {
          item.snippet = content.slice(0, MAX_CONTENT_CHARS);
          enriched += 1;
        }
      } catch (err) {
        console.warn(`[deepseek-fetch] 抓取失败 ${item.url}: ${err.message}`);
      }
    }
  });
  await Promise.all(workers);
  return enriched;
}
