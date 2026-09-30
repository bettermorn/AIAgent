'use strict';

const axios = require('axios');
const { config } = require('./config');

/**
 * 工具定义（OpenAI function calling 格式）。
 */
const TOOL_DEFINITIONS = [
  {
    type: 'function',
    function: {
      name: 'web_search',
      description:
        '使用搜索引擎查询最新信息，例如天气、新闻、股价等。返回 JSON 字符串形式的搜索结果。',
      parameters: {
        type: 'object',
        properties: {
          query: {
            type: 'string',
            description: '搜索关键词，例如 "San Francisco weather today"',
          },
        },
        required: ['query'],
      },
    },
  },
];

async function web_search({ query }) {
  if (config.tavilyApiKey) {
    try {
      const resp = await axios.post(
        'https://api.tavily.com/search',
        {
          api_key: config.tavilyApiKey,
          query,
          max_results: 3,
          search_depth: 'basic',
          include_answer: true,
        },
        { timeout: 30000 }
      );
      const results = resp.data?.results || [];
      const answer = resp.data?.answer || '';
      const formatted = results
        .map(
          (r, i) =>
            `${i + 1}. ${r.title}\n   ${r.url}\n   ${r.content || ''}`
        )
        .join('\n\n');
      return JSON.stringify({
        source: 'tavily',
        answer,
        results: formatted || '（无搜索结果）',
      });
    } catch (e) {
      // 提取 axios 4xx/5xx 的真实响应体，便于排查 Tavily 的具体拒绝原因
      const status = e.response?.status;
      const detail =
        e.response?.data?.detail ||
        e.response?.data?.error ||
        (e.response && JSON.stringify(e.response.data).slice(0, 300)) ||
        e.message;
      return JSON.stringify({
        source: 'tavily',
        error: `Tavily 调用失败${status ? ' (HTTP ' + status + ')' : ''}: ${detail}`,
        results: '',
      });
    }
  }

  // 降级方案：直接返回提示，让模型基于自身知识回答
  return JSON.stringify({
    source: 'fallback',
    note:
      '当前未配置 TAVILY_API_KEY，已跳过联网检索。请基于模型已有知识作答，并在回答中说明这是基于训练数据的回答。',
    query,
  });
}

const TOOL_HANDLERS = {
  web_search,
};

async function callTool(name, args) {
  const fn = TOOL_HANDLERS[name];
  if (!fn) {
    return JSON.stringify({ error: `未知工具: ${name}` });
  }
  try {
    const result = await fn(args || {});
    return typeof result === 'string' ? result : JSON.stringify(result);
  } catch (e) {
    return JSON.stringify({ error: e.message || String(e) });
  }
}

module.exports = {
  TOOL_DEFINITIONS,
  TOOL_HANDLERS,
  callTool,
};
