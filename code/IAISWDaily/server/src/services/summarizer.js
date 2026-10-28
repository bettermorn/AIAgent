import { config } from '../config.js';
import { CHANNEL_LABELS } from './searchProviders.js';

/**
 * DeepSeek 模型封装：用于搜索结果的总结、分类、评分与每日日报生成。
 * 未配置 API Key 时自动降级为规则式摘要，保证流程可跑通。
 */

const API_URL = `${config.deepseek.baseUrl.replace(/\/$/, '')}/chat/completions`;

export const hasLLM = () => Boolean(config.deepseek.apiKey);

async function chat(messages, { json = false, maxTokens = 2000 } = {}) {
  const body = {
    model: config.deepseek.model,
    messages,
    temperature: config.deepseek.temperature,
    max_tokens: maxTokens,
    stream: false,
  };
  if (json) body.response_format = { type: 'json_object' };

  const res = await fetch(API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${config.deepseek.apiKey}`,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120000),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`DeepSeek ${res.status}: ${text.slice(0, 300)}`);
  }
  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content || '';
  if (json) return parseJson(content);
  return content.trim();
}

function parseJson(text) {
  const cleaned = String(text)
    .replace(/^```json\s*/i, '')
    .replace(/^```\s*/i, '')
    .replace(/```\s*$/i, '')
    .trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    const start = cleaned.indexOf('{');
    const end = cleaned.lastIndexOf('}');
    if (start >= 0 && end > start) {
      try {
        return JSON.parse(cleaned.slice(start, end + 1));
      } catch { /* noop */ }
    }
    const arrStart = cleaned.indexOf('[');
    const arrEnd = cleaned.lastIndexOf(']');
    if (arrStart >= 0 && arrEnd > arrStart) {
      try {
        return JSON.parse(cleaned.slice(arrStart, arrEnd + 1));
      } catch { /* noop */ }
    }
    throw new Error('模型返回内容不是合法 JSON');
  }
}

const SYSTEM = `你是“工业智能与工业软件”领域的信息分析助手。
服务对象是中国工业软件 / 智能制造行业的产品与研究人员。
输出要求：中文、客观、精炼，不编造原文没有的事实；不确定的信息标注“待确认”。`;

function toPlain(a, idx) {
  return [
    `#${idx} id=${a.id}`,
    `渠道: ${CHANNEL_LABELS[a.channel] || a.channel}`,
    `标题: ${a.title}`,
    `来源: ${a.source || '未知'}`,
    `时间: ${a.publishedAt ? new Date(a.publishedAt).toISOString().slice(0, 10) : '未知'}`,
    `正文片段: ${(a.snippet || '').slice(0, 700)}`,
  ].join('\n');
}

/**
 * 批量总结：一次请求处理若干条，返回 id -> {summary, category, tags, score}
 */
export async function summarizeArticles(articles, { chunkSize = 6 } = {}) {
  const result = new Map();
  if (!articles.length) return result;
  if (!hasLLM()) {
    for (const a of articles) {
      result.set(a.id, {
        summary: (a.snippet || a.title).slice(0, 180) || '暂无摘要',
        category: guessCategory(a),
        tags: [a.channel],
        score: 5,
        relevant: looksRelevant(a),
      });
    }
    return result;
  }

  for (let i = 0; i < articles.length; i += chunkSize) {
    const chunk = articles.slice(i, i + chunkSize);
    const prompt = `请对下列工业智能 / 工业软件领域的搜索结果逐条处理。
对每条输出：
- relevant：是否与“工业智能 / 工业软件 / 智能制造 / 工业互联网 / 数字孪生 / 工业自动化 / 工业AI”主题相关；明显无关的垃圾结果（影视、娱乐、游戏、股票炒作、广告等）为 false
- summary：60-120 字中文要点摘要（说明“谁 / 做了什么 / 对工业软件或工业智能的意义”），无关条目可为空字符串
- category：从 [工业智能, 工业软件, 智能制造, 工业互联网, 数字孪生, 政策标准, 市场投融资, 学术研究, 其他] 中选一个
- tags：2-4 个中文标签
- score：0-10 的重要性评分（面向中国工业软件从业者的参考价值；无关条目为 0）

严格以如下 JSON 返回：{"items":[{"id":123,"relevant":true,"summary":"...","category":"...","tags":["..."],"score":7}]}

${chunk.map(toPlain).join('\n\n')}`;

    try {
      const data = await chat(
        [
          { role: 'system', content: SYSTEM },
          { role: 'user', content: prompt },
        ],
        { json: true, maxTokens: 2500 },
      );
      const items = Array.isArray(data) ? data : data.items || [];
      for (const it of items) {
        const id = Number(it.id);
        if (!Number.isFinite(id)) continue;
        result.set(id, {
          summary: String(it.summary || '').trim(),
          category: String(it.category || '其他').trim(),
          tags: Array.isArray(it.tags) ? it.tags.map(String).slice(0, 6) : [],
          score: clampScore(it.score),
          relevant: it.relevant !== false && it.relevant !== 'false',
        });
      }
    } catch (err) {
      console.warn(`[llm] 批量总结失败: ${err.message}`);
      for (const a of chunk) {
        result.set(a.id, {
          summary: (a.snippet || a.title).slice(0, 180) || '暂无摘要',
          category: guessCategory(a),
          tags: [a.channel],
          score: 5,
          relevant: looksRelevant(a),
        });
      }
    }
  }
  return result;
}

/**
 * 生成每日日报
 */
export async function buildDailyReport(articles, { date }) {
  const byChannel = articles.reduce((acc, a) => {
    acc[a.channel] = (acc[a.channel] || 0) + 1;
    return acc;
  }, {});

  if (!articles.length) {
    return {
      title: `${date} 工业智能与工业软件信息日报`,
      overview: '今日未采集到符合条件的新增信息。',
      highlights: [],
      trends: [],
      byChannel,
    };
  }

  if (!hasLLM()) {
    return {
      title: `${date} 工业智能与工业软件信息日报`,
      overview: `今日共采集 ${articles.length} 条信息，覆盖 ${Object.keys(byChannel).length} 个渠道。未配置 DEEPSEEK_API_KEY，以下为按来源汇总的条目清单。`,
      highlights: articles.slice(0, 8).map((a) => ({
        title: a.title,
        why: (a.snippet || '').slice(0, 120),
        url: a.url,
        source: a.source,
      })),
      trends: ['配置 DEEPSEEK_API_KEY 后可自动生成趋势洞察'],
      byChannel,
    };
  }

  const brief = articles
    .slice(0, 40)
    .map((a, i) =>
      [
        `#${i + 1} id=${a.id}`,
        `渠道: ${CHANNEL_LABELS[a.channel] || a.channel}`,
        `标题: ${a.title}`,
        `来源: ${a.source || '未知'}`,
        `分类: ${a.category || '未分类'}`,
        `要点: ${(a.summary || a.snippet || '').slice(0, 220)}`,
      ].join('\n'),
    )
    .join('\n\n');

  const prompt = `下面是 ${date} 采集到的工业智能 / 工业软件领域信息（共 ${articles.length} 条，节选 ${Math.min(articles.length, 40)} 条）。

请生成一份日报，面向中国工业软件与智能制造从业者，严格返回 JSON：
{
  "title": "日报标题（含日期）",
  "overview": "300-500 字总体综述：今天这个领域发生了什么，最值得关注的是什么",
  "highlights": [
    {"id": 123, "title": "原标题或精炼标题", "why": "为什么值得关注（50-80字）", "url": "原文链接", "source": "来源"}
  ],
  "trends": ["趋势洞察1", "趋势洞察2", "趋势洞察3"]
}
要求：highlights 取最重要的 5-8 条，按重要性排序；trends 为 3-5 条可执行的洞察。

${brief}`;

  try {
    const data = await chat(
      [
        { role: 'system', content: SYSTEM },
        { role: 'user', content: prompt },
      ],
      { json: true, maxTokens: 3000 },
    );
    const highlights = (data.highlights || []).map((h) => ({
      id: Number(h.id) || null,
      title: String(h.title || '').trim(),
      why: String(h.why || '').trim(),
      url: String(h.url || '').trim(),
      source: String(h.source || '').trim(),
    }));
    return {
      title: String(data.title || `${date} 工业智能与工业软件信息日报`).trim(),
      overview: String(data.overview || '').trim(),
      highlights,
      trends: Array.isArray(data.trends) ? data.trends.map(String) : [],
      byChannel,
    };
  } catch (err) {
    console.warn(`[llm] 日报生成失败: ${err.message}`);
    return {
      title: `${date} 工业智能与工业软件信息日报`,
      overview: `今日共采集 ${articles.length} 条信息（日报自动生成失败：${err.message}）。`,
      highlights: articles.slice(0, 8).map((a) => ({
        id: a.id,
        title: a.title,
        why: (a.summary || a.snippet || '').slice(0, 120),
        url: a.url,
        source: a.source,
      })),
      trends: [],
      byChannel,
    };
  }
}

function clampScore(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 5;
  return Math.max(0, Math.min(10, Math.round(n * 10) / 10));
}

/** 规则式相关性判断（未配置 LLM 时的兜底） */
export function looksRelevant(a) {
  const text = `${a.title} ${a.snippet || ''}`;
  return RELEVANT_RE.test(text);
}

const RELEVANT_RE =
  /工业|制造|工厂|车间|数字孪生|数字化|智能装备|机器人|自动化|CAD|CAE|CAM|PLM|MES|ERP|SCADA|EDA|工业软件|工业互联网|IIoT|industrial|manufacturing|factory|digital twin|smart factory|Industry 4|PLM|CAD\/CAE/i;

function guessCategory(a) {
  const text = `${a.title} ${a.snippet || ''}`;
  if (/工业软件|CAD|CAE|PLM|MES|EDA|SCADA/i.test(text)) return '工业软件';
  if (/工业智能|人工智能|大模型|AI/i.test(text)) return '工业智能';
  if (/数字孪生|digital twin/i.test(text)) return '数字孪生';
  if (/工业互联网|工业物联网|IIoT/i.test(text)) return '工业互联网';
  if (/智能制造|智能工厂/i.test(text)) return '智能制造';
  if (/标准|政策|规划|工信部/i.test(text)) return '政策标准';
  return '其他';
}
