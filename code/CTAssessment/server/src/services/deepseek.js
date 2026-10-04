import { config } from '../config.js';

// 调用 DeepSeek Chat API
export async function chat(messages, { temperature = 0.3, jsonMode = false, maxTokens = 4096 } = {}) {
  const body = {
    model: config.deepseek.model,
    messages,
    temperature,
    max_tokens: maxTokens,
  };
  if (jsonMode) body.response_format = { type: 'json_object' };

  const res = await fetch(`${config.deepseek.baseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${config.deepseek.apiKey}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`DeepSeek API 错误 (${res.status}): ${text.slice(0, 500)}`);
  }
  const data = await res.json();
  return data.choices?.[0]?.message?.content ?? '';
}

// 从模型输出中稳健地解析 JSON（兼容 ```json 包裹）
export function parseJsonOutput(text) {
  if (!text) throw new Error('模型返回为空');
  let t = text.trim();
  const fence = t.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) t = fence[1].trim();
  const start = t.indexOf('{');
  const end = t.lastIndexOf('}');
  if (start === -1 || end === -1) throw new Error('模型输出中未找到 JSON');
  return JSON.parse(t.slice(start, end + 1));
}
