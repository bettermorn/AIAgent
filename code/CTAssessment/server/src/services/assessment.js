import { chat, parseJsonOutput } from './deepseek.js';
import {
  SELF_RATING_ITEMS, TASK_QUESTIONS, SECTION_SCORES, TOTAL_SCORE,
  abilityLevel, selfLevel, DIMENSIONS,
} from '../data/questionnaire.js';

// ---------- 自评量表计分（含反向题转换）----------
export function computeSelfScores(selfAnswers) {
  const dims = { decomposition: 0, pattern: 0, abstraction: 0, algorithm: 0 };
  const levels = {};
  for (const item of SELF_RATING_ITEMS) {
    let v = Number(selfAnswers[item.id]);
    if (!v || v < 1 || v > 5) continue;
    if (item.reverse) v = 6 - v;
    dims[item.dimension] += v;
  }
  for (const d of DIMENSIONS) {
    levels[d.key] = selfLevel(dims[d.key]);
  }
  return { scores: dims, levels };
}

// ---------- 情境任务评分：DeepSeek 按评分标准逐题打分 ----------
export async function gradeTasks(taskAnswers, studentInfo, selfScores) {
  const questionBlocks = TASK_QUESTIONS.map((q) => {
    const ans = (taskAnswers[q.id] || '').trim() || '（未作答）';
    return `【第${q.no}题 ${q.title}】（满分${q.maxScore}分，维度：${q.section}）
题目：${q.prompt}
评分标准：${q.rubric}
参考答案：${q.reference}
学生答案：${ans}`;
  }).join('\n\n');

  const systemPrompt = `你是一位专业的高中信息技术教师和计算思维测评专家。你需要根据评分标准，对学生的计算思维情境测试答案逐题评分并给出评价。

评分原则：
1. 严格按照每题的评分标准给分，不得超出满分。
2. 重视过程而不只看最终答案，答案表述清晰、逻辑合理即可部分给分。
3. 允许多种合理答案，尤其是开放题，关注是否分解合理、有逻辑关系、可执行、考虑反馈改进。
4. 未作答记0分。
5. 每题给出简短的扣分/得分理由。

请严格输出如下 JSON（不要输出任何其他内容）：
{
  "scores": {
    "t1": {"score": 0-8的整数, "comment": "简短点评"},
    "t2": {"score": ...}, ... 直到 "t14"
  },
  "dimensionComments": {
    "decomposition": "分解问题维度整体评价（2-3句）",
    "pattern": "模式识别维度整体评价（2-3句）",
    "abstraction": "抽象维度整体评价（2-3句）",
    "algorithm": "算法设计维度整体评价（2-3句）",
    "comprehensive": "综合运用能力评价（2-3句）",
    "ai": "人工智能理解评价（2-3句）"
  },
  "strengths": ["优势1", "优势2", ...],
  "weaknesses": ["不足1", "不足2", ...]
}`;

  const userPrompt = `学生信息：${studentInfo.grade}，编程经历：${studentInfo.programmingExp}，接触语言：${studentInfo.languagesText}，使用图表整理问题的频率：${studentInfo.chartsUsage}。
该生自评量表得分（各维度满分25）：分解问题${selfScores.decomposition}分、模式识别${selfScores.pattern}分、抽象${selfScores.abstraction}分、算法设计${selfScores.algorithm}分。

以下是学生的情境测试答案，请逐题评分：

${questionBlocks}`;

  const raw = await chat(
    [{ role: 'system', content: systemPrompt }, { role: 'user', content: userPrompt }],
    { temperature: 0.2, jsonMode: true, maxTokens: 6000 }
  );
  const parsed = parseJsonOutput(raw);

  // 规整每题得分并汇总
  const detail = {};
  const dims = {};
  for (const q of TASK_QUESTIONS) {
    const s = parsed.scores?.[q.id];
    let score = 0;
    let comment = '';
    if (s) {
      score = Math.max(0, Math.min(q.maxScore, Math.round(Number(s.score) || 0)));
      comment = String(s.comment || '');
    }
    detail[q.id] = { no: q.no, title: q.title, maxScore: q.maxScore, score, comment };
    dims[q.dimension] = (dims[q.dimension] || 0) + score;
  }
  const total = TASK_QUESTIONS.reduce((sum, q) => sum + detail[q.id].score, 0);
  const percentage = Math.round((total / TOTAL_SCORE) * 1000) / 10;

  return {
    detail,
    dimensionScores: dims,
    sectionMax: Object.fromEntries(Object.entries(SECTION_SCORES).map(([k, v]) => [k, v.max])),
    total,
    percentage,
    level: abilityLevel(percentage),
    dimensionComments: parsed.dimensionComments || {},
    strengths: parsed.strengths || [],
    weaknesses: parsed.weaknesses || [],
  };
}

// ---------- 生成评价结论 ----------
export async function generateConclusion(studentInfo, selfResult, taskResult) {
  const { level } = taskResult;
  const systemPrompt = `你是一位专业的高中信息技术教师，正在为学生撰写计算思维测评报告的"评价结论"。

要求：
1. 结合基本信息、自评量表得分和情境测试得分进行综合评价，指出自评与实测是否一致。
2. 用学生能理解的、鼓励性的语言，客观指出四个维度（分解问题、模式识别、抽象、算法设计）的表现。
3. 明确指出最需要提升的1-2个维度。
4. 长度300-500字，使用中文，分为2-3个自然段。
5. 直接输出结论文字，不要任何前后缀。`;

  const userPrompt = `学生：${studentInfo.name || '某同学'}，${studentInfo.grade}，编程经历：${studentInfo.programmingExp}，接触过的语言：${studentInfo.languagesText}，使用图表/流程图整理问题的频率：${studentInfo.chartsUsage}。

自评量表（各维度满分25）：
- 分解问题：${selfResult.scores.decomposition}分（${selfResult.levels.decomposition}）
- 模式识别：${selfResult.scores.pattern}分（${selfResult.levels.pattern}）
- 抽象：${selfResult.scores.abstraction}分（${selfResult.levels.abstraction}）
- 算法设计：${selfResult.scores.algorithm}分（${selfResult.levels.algorithm}）

情境测试（总分85，百分制${taskResult.percentage}分，能力水平：${level.level}——${level.desc}）：
- 分解问题（满分20）：${taskResult.dimensionScores.decomposition || 0}分
- 模式识别（满分13）：${taskResult.dimensionScores.pattern || 0}分
- 抽象（满分16）：${taskResult.dimensionScores.abstraction || 0}分
- 算法设计（满分16）：${taskResult.dimensionScores.algorithm || 0}分
- 综合开放题（满分12）：${taskResult.dimensionScores.comprehensive || 0}分
- 人工智能问题（满分8）：${taskResult.dimensionScores.ai || 0}分

各维度教师点评：${JSON.stringify(taskResult.dimensionComments)}
优势：${JSON.stringify(taskResult.strengths)}
不足：${JSON.stringify(taskResult.weaknesses)}`;

  const conclusion = await chat(
    [{ role: 'system', content: systemPrompt }, { role: 'user', content: userPrompt }],
    { temperature: 0.5, maxTokens: 1500 }
  );
  return conclusion.trim();
}
