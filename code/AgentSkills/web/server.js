import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 从 config.env 加载配置
dotenv.config({ path: path.join(__dirname, 'config.env') });

const DEEPSEEK_API_KEY = process.env.DEEPSEEK_API_KEY;
const DEEPSEEK_BASE_URL = (process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com').replace(/\/+$/, '');
const DEEPSEEK_MODEL = process.env.DEEPSEEK_MODEL || 'deepseek-chat';
const PORT = process.env.PORT || 3001;

const app = express();
app.use(cors());
app.use(express.json());

// 健康检查：提示 Key 是否已配置（不泄露内容）
app.get('/api/health', (_req, res) => {
  res.json({
    ok: true,
    model: DEEPSEEK_MODEL,
    apiKeyConfigured: Boolean(DEEPSEEK_API_KEY && DEEPSEEK_API_KEY !== 'your_deepseek_api_key_here'),
  });
});

function buildPrompt(topic) {
  return `你是一个 PPT 结构生成器。
请根据用户输入生成 JSON，不要输出任何解释说明。

JSON 格式必须严格如下：
{
  "title": "...",
  "slides": [
    {
      "title": "...",
      "content": ["...", "..."]
    }
  ]
}

用户主题：${topic}`;
}

// 从模型输出中稳健地提取 JSON（兼容 ```json 代码块包裹）
function extractJson(text) {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const raw = fenced ? fenced[1] : text;
  return JSON.parse(raw.trim());
}

// 调用 DeepSeek，将主题转为结构化 PPT IR
app.post('/api/generate', async (req, res) => {
  const topic = (req.body?.topic || '').trim();
  if (!topic) {
    return res.status(400).json({ error: '请输入主题' });
  }
  if (!DEEPSEEK_API_KEY || DEEPSEEK_API_KEY === 'your_deepseek_api_key_here') {
    return res.status(500).json({ error: '未配置 DEEPSEEK_API_KEY，请在 web/config.env 中填写你的 Key' });
  }

  try {
    const resp = await fetch(`${DEEPSEEK_BASE_URL}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${DEEPSEEK_API_KEY}`,
      },
      body: JSON.stringify({
        model: DEEPSEEK_MODEL,
        messages: [
          { role: 'system', content: '你是一个结构化输出助手' },
          { role: 'user', content: buildPrompt(topic) },
        ],
        response_format: { type: 'json_object' },
        temperature: 0.3,
        max_tokens: 4096,
      }),
    });

    if (!resp.ok) {
      const errText = await resp.text();
      return res.status(resp.status).json({ error: `DeepSeek API 调用失败: ${errText.slice(0, 500)}` });
    }

    const data = await resp.json();
    const text = data.choices?.[0]?.message?.content?.trim();
    if (!text) {
      return res.status(502).json({ error: 'DeepSeek 返回内容为空' });
    }

    let ir;
    try {
      ir = extractJson(text);
    } catch {
      return res.status(502).json({ error: `模型输出无法解析为 JSON: ${text.slice(0, 300)}` });
    }

    if (!ir.title || !Array.isArray(ir.slides) || ir.slides.length === 0) {
      return res.status(502).json({ error: '生成的结构缺少 title 或 slides 字段' });
    }

    res.json({
      title: ir.title,
      slides: ir.slides.map((s) => ({
        title: s.title || '',
        content: Array.isArray(s.content) ? s.content : [String(s.content ?? '')],
      })),
      model: DEEPSEEK_MODEL,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: `服务异常: ${err.message}` });
  }
});

app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT} (model: ${DEEPSEEK_MODEL})`);
});
