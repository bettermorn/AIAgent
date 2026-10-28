import crypto from 'node:crypto';
import { fetchJson } from './http.js';

/**
 * B站 Web 接口 WBI 签名（2023 年后必须签名，否则返回 412）
 * 参考公开实现：获取 nav 接口中的 img_key / sub_key，按固定表重排生成 mixin_key。
 */
const MIXIN_KEY_ENC_TAB = [
  46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
  33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
  26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
  20, 34, 44, 52,
];

const UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36';

let cachedKey = null;
let cookieJar = '';
let cookieAt = 0;

/** B站接口需要 buvid3 等 Cookie，否则返回 412 */
export async function biliHeaders() {
  if (cookieJar && Date.now() - cookieAt < 30 * 60 * 1000) {
    return { 'User-Agent': UA, Cookie: cookieJar, Referer: 'https://www.bilibili.com/' };
  }
  try {
    const res = await fetch('https://www.bilibili.com/', {
      headers: { 'User-Agent': UA },
      signal: AbortSignal.timeout(15000),
    });
    const cookies = typeof res.headers.getSetCookie === 'function' ? res.headers.getSetCookie() : [];
    const jar = cookies.map((c) => c.split(';')[0]).join('; ');
    if (jar) {
      cookieJar = jar;
      cookieAt = Date.now();
    }
  } catch { /* 忽略，继续无 Cookie 请求 */ }
  return { 'User-Agent': UA, Cookie: cookieJar, Referer: 'https://www.bilibili.com/' };
}

async function getMixinKey() {
  if (cachedKey && Date.now() - cachedKey.at < 30 * 60 * 1000) return cachedKey.key;
  const data = await fetchJson('https://api.bilibili.com/x/web-interface/nav', {
    headers: await biliHeaders(),
  });
  const imgUrl = data?.data?.wbi_img?.img_url || '';
  const subUrl = data?.data?.wbi_img?.sub_url || '';
  const imgKey = imgUrl.split('/').pop().split('.')[0];
  const subKey = subUrl.split('/').pop().split('.')[0];
  if (!imgKey || !subKey) throw new Error('无法获取 B站 wbi key');
  const raw = imgKey + subKey;
  const key = MIXIN_KEY_ENC_TAB.map((i) => raw[i]).join('').slice(0, 32);
  cachedKey = { key, at: Date.now() };
  return key;
}

function md5(input) {
  return crypto.createHash('md5').update(input).digest('hex');
}

/** 为查询参数对象附加 wts / w_rid */
export async function signWbi(params) {
  const mixinKey = await getMixinKey();
  const withWts = { ...params, wts: Math.round(Date.now() / 1000) };
  const query = Object.keys(withWts)
    .sort()
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(withWts[k]).replace(/[!'()*]/g, ''))}`)
    .join('&');
  const w_rid = md5(query + mixinKey);
  return { ...withWts, w_rid };
}
