/**
 * 微信公众号文章检索（基于搜狗微信搜索）
 * 1) 搜索列表页解析标题 / 摘要 / 公众号名 / 发布时间
 * 2) 逐个解析跳转页中的真实 mp.weixin.qq.com 地址（失败时保留搜狗跳转链接）
 */

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36';
const SOGOU = 'https://weixin.sogou.com';

let cookieJar = '';
let cookieAt = 0;

async function ensureCookie(timeout = 15000) {
  if (cookieJar && Date.now() - cookieAt < 20 * 60 * 1000) return cookieJar;
  const res = await fetch(`${SOGOU}/`, { headers: { 'User-Agent': UA }, signal: AbortSignal.timeout(timeout) });
  const cookies = typeof res.headers.getSetCookie === 'function' ? res.headers.getSetCookie() : [];
  const jar = cookies.map((c) => c.split(';')[0]).join('; ');
  if (jar) {
    cookieJar = jar;
    cookieAt = Date.now();
  }
  return cookieJar;
}

const stripTags = (s) =>
  String(s || '')
    .replace(/<!--.*?-->/g, '')
    .replace(/<[^>]+>/g, '')
    .replace(/&ldquo;|&rdquo;/g, '"')
    .replace(/&amp;/g, '&')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .trim();

export async function searchWechat(keyword, { limit = 8, windowDays = 7, resolveLimit = 5 } = {}) {
  await ensureCookie();
  const url = `${SOGOU}/weixin?type=2&query=${encodeURIComponent(keyword)}&ie=utf8`;
  const res = await fetch(url, {
    headers: { 'User-Agent': UA, Cookie: cookieJar, Referer: `${SOGOU}/` },
    signal: AbortSignal.timeout(20000),
  });
  const html = await res.text();
  if (/请输入验证码|antispider|访问过于频繁/.test(html)) {
    throw new Error('搜狗触发反爬验证');
  }

  const blocks = html.match(/<li id="sogou_vr_11002601_box_\d+"[\s\S]*?<\/li>/g) || [];
  const items = [];
  for (const b of blocks.slice(0, limit)) {
    const title = stripTags((b.match(/id="sogou_vr_11002601_title_\d+"[^>]*>([\s\S]*?)<\/a>/) || [])[1]);
    const href = (b.match(/href="(\/link\?url=[^"]+)"/) || [])[1];
    if (!title || !href) continue;
    const summary = stripTags((b.match(/id="sogou_vr_11002601_summary_\d+"[^>]*>([\s\S]*?)<\/p>/) || [])[1]);
    const account =
      stripTags((b.match(/id="sogou_vr_11002601_account_\d+"[^>]*>([\s\S]*?)<\/a>/) || [])[1]) ||
      stripTags((b.match(/<span class="all-time-y2">([\s\S]*?)<\/span>/) || [])[1]);
    const ts = (b.match(/timeConvert\('(\d+)'\)/) || [])[1];
    const publishedAt = ts ? new Date(Number(ts) * 1000) : null;

    items.push({
      url: SOGOU + href.replace(/&amp;/g, '&'),
      title,
      snippet: summary,
      source: account ? `微信公众号 · ${account}` : '微信公众号',
      publishedAt,
      channel: 'wechat',
      language: 'zh',
      keyword,
    });
  }

  // 解析真实公众号链接（限量 + 随机延迟，避免触发反爬）
  for (const item of items.slice(0, resolveLimit)) {
    if (Date.now() < blockedUntil) break;
    try {
      const real = await resolveRealUrl(item.url);
      if (real) item.url = real;
      await new Promise((r) => setTimeout(r, 400 + Math.random() * 500));
    } catch { /* 保留搜狗跳转链接 */ }
  }

  const deadline = Date.now() - windowDays * 864e5;
  return items.filter((i) => !i.publishedAt || i.publishedAt.getTime() >= deadline);
}

let blockedUntil = 0;

async function resolveRealUrl(linkUrl) {
  await ensureCookie();
  const res = await fetch(linkUrl, {
    headers: { 'User-Agent': UA, Cookie: cookieJar, Referer: `${SOGOU}/weixin` },
    signal: AbortSignal.timeout(15000),
  });
  const html = await res.text();
  if (/verify\.css|请输入验证码|anti\.min\.css/.test(html)) {
    // 触发反爬：本轮停止解析，30 分钟后再试
    blockedUntil = Date.now() + 30 * 60 * 1000;
    return null;
  }
  const parts = [...html.matchAll(/url \+= '([^']*)'/g)].map((m) => m[1]);
  const joined = parts.join('');
  const match = joined.match(/https?:\/\/mp\.weixin\.qq\.com\/[\s\S]*?(?=['"]|$)/);
  const url = match ? match[0].replace(/['")\s;]+$/, '') : '';
  return /^https?:\/\/mp\.weixin\.qq\.com\//.test(url) ? url : null;
}
