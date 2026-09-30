'use strict';

const axios = require('axios');
const { config } = require('./config');

/**
 * DeepSeek API 客户端（OpenAI 兼容协议）。
 * 文档参考: https://api-docs.deepseek.com/
 */
const client = axios.create({
  baseURL: config.deepseekBaseUrl,
  timeout: 60000,
  // 优先使用环境变量里的代理：HTTPS_PROXY / HTTP_PROXY / https_proxy / http_proxy
  proxy: buildProxyConfig(),
  headers: {
    'Content-Type': 'application/json',
    Authorization: config.deepseekApiKey
      ? `Bearer ${config.deepseekApiKey}`
      : '',
  },
});

function buildProxyConfig() {
  // 任意一个被设置的代理环境变量都生效
  const envProxy =
    process.env.HTTPS_PROXY ||
    process.env.HTTP_PROXY ||
    process.env.https_proxy ||
    process.env.http_proxy ||
    process.env.ALL_PROXY ||
    process.env.all_proxy;
  if (!envProxy) return false;

  // 1) 先尝试 URL 形式：http://[user:pass@]host:port
  if (/^https?:\/\//i.test(envProxy)) {
    try {
      const u = new URL(envProxy);
      return {
        protocol: u.protocol.replace(':', ''),
        host: u.hostname,
        port: Number(u.port) || (u.protocol === 'https:' ? 443 : 80),
        auth: u.username
          ? {
              username: decodeURIComponent(u.username),
              password: decodeURIComponent(u.password),
            }
          : undefined,
      };
    } catch (_) {
      /* fallthrough */
    }
  }

  // 2) 兜底：host:port 简写
  const m = envProxy.match(/^([^:]+):(\d+)$/);
  if (m) return { protocol: 'http', host: m[1], port: Number(m[2]) };

  return false;
}

/**
 * 将 LangChain 风格的消息转换为 OpenAI 风格消息。
 */
function convertMessages(messages) {
  const out = [];
  for (const m of messages) {
    const role = m.role || (m.type === 'human' ? 'user' : m.type === 'ai' ? 'assistant' : 'user');
    if (role === 'system') {
      out.push({ role: 'system', content: m.content || '' });
    } else if (role === 'user' || role === 'human') {
      out.push({ role: 'user', content: m.content || '' });
    } else if (role === 'assistant' || role === 'ai') {
      const msg = { role: 'assistant', content: m.content || '' };
      // DeepSeek 思考模式要求：带 tool_calls 的 assistant 消息必须
      // 把当初返回的 reasoning_content 原样传回，否则 400
      if (m.reasoning_content) {
        msg.reasoning_content = m.reasoning_content;
      }
      if (m.tool_calls && m.tool_calls.length) {
        msg.tool_calls = m.tool_calls.map((tc) => ({
          id: tc.id,
          type: 'function',
          function: {
            name: tc.name,
            arguments:
              typeof tc.args === 'string' ? tc.args : JSON.stringify(tc.args || {}),
          },
        }));
      }
      out.push(msg);
    } else if (role === 'tool') {
      out.push({
        role: 'tool',
        content: m.content || '',
        tool_call_id: m.tool_call_id,
      });
    }
  }
  return out;
}

/**
 * 调用 DeepSeek 模型，支持 tool_calls。
 * 返回: { content, tool_calls, raw }
 */
async function chat({ messages, tools, toolChoice, temperature = 0.2 }) {
  if (!config.deepseekApiKey || config.deepseekApiKey === 'your-deepseek-api-key-here') {
    throw new Error('DEEPSEEK_API_KEY 未配置，请编辑 config.env 后重启服务。');
  }

  const body = {
    model: config.deepseekModel,
    messages: convertMessages(messages),
    temperature,
    stream: false,
  };

  if (tools && tools.length) {
    body.tools = tools;
    if (toolChoice) body.tool_choice = toolChoice;
  }

  let resp;
  try {
    resp = await client.post('/chat/completions', body);
  } catch (err) {
    // 1) 网络/底层错误（DNS、连接被拒、超时等）— 没有 e.response
    if (!err.response) {
      const code = err.code || err.errno || '';
      const sys = err.syscall || '';
      const reason = explainNetworkError(code, err.message);
      throw new Error(
        `DeepSeek 网络错误 (${code || 'UNKNOWN'}${sys ? ' / ' + sys : ''}): ` +
        `无法连接 ${config.deepseekBaseUrl}\n` +
        `  ↳ 原因：${reason}\n` +
        `  ↳ 排查：\n` +
        `     1) 终端执行   curl -v ${config.deepseekBaseUrl}/models \\\n` +
        `           -H "Authorization: Bearer ${config.deepseekApiKey?.slice(0, 8)}..."\n` +
        `     2) 若需要代理，编辑 config.env 设置   HTTPS_PROXY=http://127.0.0.1:7890\n` +
        `     3) 检查防火墙 / VPN 是否拦截了 api.deepseek.com`
      );
    }
    // 2) HTTP 4xx/5xx — 提取真正错误体
    const status = err.response.status;
    const data = err.response.data;
    const upstreamMsg =
      data?.error?.message || data?.message || data?.error || err.message;
    const detail =
      typeof data === 'string' ? data : JSON.stringify(data || {}).slice(0, 500);
    throw new Error(
      `DeepSeek ${status}: ${upstreamMsg} | ${detail}`
    );
  }

  const choice = resp.data?.choices?.[0];
  if (!choice) {
    throw new Error('DeepSeek 返回数据为空: ' + JSON.stringify(resp.data));
  }
  const message = choice.message || {};

  const toolCalls = (message.tool_calls || []).map((tc) => ({
    id: tc.id,
    name: tc.function?.name,
    args: safeParseArgs(tc.function?.arguments),
  }));

  return {
    content: message.content || '',
    // 思考模式的推理内容：必须随消息持久化，重放时传回 API
    reasoning_content: message.reasoning_content || '',
    tool_calls: toolCalls,
    raw: resp.data,
  };
}

function safeParseArgs(str) {
  if (!str) return {};
  try {
    return JSON.parse(str);
  } catch (_) {
    return { _raw: str };
  }
}

/**
 * 把 Node.js DNS/网络错误码翻译成中文说明，便于用户排查。
 */
function explainNetworkError(code, rawMsg) {
  switch (code) {
    case 'ENOTFOUND':
      return 'DNS 解析失败（域名不存在或本机 DNS 配置错误）';
    case 'ECONNREFUSED':
      return '远端端口拒绝连接（可能被防火墙拦截或服务宕机）';
    case 'ETIMEDOUT':
      return '连接超时（网络不通）';
    case 'ECONNRESET':
      return '连接被远端重置';
    case 'EAI_AGAIN':
      return 'DNS 临时解析失败（重试可解）';
    case 'ENETUNREACH':
      return '本机网络不可达（无网或路由缺失）';
    case 'EHOSTUNREACH':
      return '目标主机不可达';
    case 'CERT_HAS_EXPIRED':
    case 'UNABLE_TO_VERIFY_LEAF_SIGNATURE':
    case 'SELF_SIGNED_CERT_IN_CHAIN':
      return 'HTTPS 证书校验失败（可能是公司代理/防火墙 TLS 拦截）';
    default:
      return rawMsg || '未知网络错误';
  }
}

module.exports = { chat };
