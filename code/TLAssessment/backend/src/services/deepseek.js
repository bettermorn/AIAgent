import { config } from '../config.js';

// DeepSeek Chat Completions 调用
export async function chat(messages, { temperature = 0.7, maxTokens = 4096, timeoutMs = 120000 } = {}) {
  if (!config.deepseekApiKey) throw new Error('未配置 DEEPSEEK_API_KEY');

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${config.deepseekBaseUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.deepseekApiKey}`
      },
      body: JSON.stringify({
        model: config.deepseekModel,
        messages,
        temperature,
        max_tokens: maxTokens,
        stream: false
      }),
      signal: controller.signal
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`DeepSeek API ${res.status}: ${text.slice(0, 500)}`);
    }
    const data = await res.json();
    const content = data?.choices?.[0]?.message?.content;
    if (!content) throw new Error('DeepSeek 返回内容为空');
    return content;
  } finally {
    clearTimeout(timer);
  }
}

// ---------- 评价结论 ----------
export async function generateConclusion(scoreSummary, scores) {
  const system = `你是一位资深的技术领导力评测与发展专家，熟悉团队管理、技术能力发展、商业影响力和专业贡献的评估框架（参考 ACM 对高级/杰出专业人员的要求）。
请根据评测数据，输出一份客观、专业、有洞察力的评价结论。要求：
1. 使用简体中文，使用 Markdown 格式（二级/三级标题、加粗、列表）。
2. 结构：## 总体评价（含总体等级判断）→ ## 分维度点评（对四个维度逐一分析优势与短板，引用具体得分和关键题目）→ ## 关键优势（提炼2-4项核心优势）→ ## 主要短板与风险（提炼2-4项，引用低于3分的题目）→ ## 认知差异观察（结合评价关系与开放题，指出值得注意的差异或盲区）。
3. 点评要具体、基于数据，避免空泛套话；对4分/5分的评价要提示"需以事实与案例支撑"。
4. 总长度控制在 800-1500 字。`;

  const user = `以下是技术领导力评测问卷的结果数据，请给出评价结论：\n\n${scoreSummary}`;

  return chat(
    [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ],
    { temperature: 0.5 }
  );
}

// ---------- 学习建议 ----------
export async function generateLearningAdvice({ scoreSummary, knowledgeContext, searchContext }) {
  const system = `你是一位技术领导力发展教练，请基于评测结果、知识库要点和网络搜索到的最新学习资源，为被评价人制定一份个性化、可落地的学习与发展建议。
要求：
1. 使用简体中文，Markdown 格式。
2. 结构：## 学习建议总览 → ## 分维度学习建议（每个维度给出：核心提升方向、学习要点、推荐书籍/课程/资源、具体实践行动，实践行动要具体到"做什么、怎么做"）→ ## 6-12个月发展路线图（分阶段：0-3个月/3-6个月/6-12个月，每阶段给出可检验的目标）→ ## 推荐学习资源清单（分书籍、课程、社区/专业组织三类，优先引用知识库与搜索结果中的真实资源，附链接）。
3. 建议要针对低分项，优先补短板、其次扬优势；参考知识库中的方法论（如三力合一、胶冻团队、ACM专业贡献路径、新技术学习五问等）。
4. 引用搜索结果中的资源时注明来源；如资源与提升方向无关则不要硬凑。
5. 总长度控制在 1200-2000 字。`;

  const user = `【评测结果数据】\n${scoreSummary}\n\n【技术领导力知识库要点（来自课程体系与参考文章）】\n${knowledgeContext}\n\n【网络搜索到的学习资源】\n${searchContext}\n\n请生成个性化学习建议。`;

  return chat(
    [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ],
    { temperature: 0.6, maxTokens: 6000 }
  );
}
