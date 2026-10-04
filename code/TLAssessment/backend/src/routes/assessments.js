import { Router } from 'express';
import { query } from '../db.js';
import { computeScores, buildScoreSummary } from '../services/scoring.js';
import { generateConclusion, generateLearningAdvice } from '../services/deepseek.js';
import { searchLearningResources, formatSearchContext } from '../services/search.js';
import { questionnaire, SCORING_GUIDE, DIMENSION_WEIGHTS, SCORE_BANDS, RELATIONSHIPS, WORK_DURATIONS, DEVELOPMENT_AREAS, OVERALL_RATING_ITEMS, CASE_PROMPTS, TOTAL_QUESTIONS } from '../data/questionnaire.js';
import { DIMENSION_KNOWLEDGE, CORE_METHODOLOGY, GROWTH_PRINCIPLES } from '../data/knowledge.js';
import { config } from '../config.js';

export const router = Router();

// ---------- 问卷结构 ----------
router.get('/questionnaire', (_req, res) => {
  res.json({
    title: '技术领导力评测问卷',
    scaleGuide: SCORING_GUIDE,
    weights: DIMENSION_WEIGHTS,
    scoreBands: SCORE_BANDS,
    relationships: RELATIONSHIPS,
    workDurations: WORK_DURATIONS,
    developmentAreas: DEVELOPMENT_AREAS,
    overallRatingItems: OVERALL_RATING_ITEMS,
    casePrompts: CASE_PROMPTS,
    totalQuestions: TOTAL_QUESTIONS,
    dimensions: questionnaire
  });
});

// ---------- 提交评测，异步生成报告 ----------
router.post('/assessments', async (req, res) => {
  try {
    const { basicInfo = {}, answers = {}, openAnswers = {}, overall = {} } = req.body || {};

    // 校验：至少有部分有效评分
    const validAnswers = Object.fromEntries(
      Object.entries(answers).filter(([, v]) => (typeof v === 'number' && v >= 1 && v <= 5) || v === 'N/A')
    );
    const numericCount = Object.values(validAnswers).filter((v) => typeof v === 'number').length;
    if (numericCount < 5) {
      return res.status(400).json({ error: '有效评分题目过少（至少需要 5 道 1-5 分的评分题）' });
    }

    const scores = computeScores(validAnswers, overall.ratings || {});

    const { rows } = await query(
      `INSERT INTO assessments
        (evaluatee_name, department, position, evaluator_name, relationship, work_duration, period,
         answers, open_answers, overall, scores, status)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'processing')
       RETURNING id, created_at`,
      [
        basicInfo.evaluateeName || '', basicInfo.department || '', basicInfo.position || '',
        basicInfo.evaluatorName || '', basicInfo.relationship || '', basicInfo.workDuration || '',
        basicInfo.period || '',
        JSON.stringify(validAnswers), JSON.stringify(openAnswers || {}),
        JSON.stringify(overall || {}), JSON.stringify(scores)
      ]
    );
    const id = rows[0].id;

    // 异步生成报告（评价结论 + 搜索资源 + 学习建议）
    generateReport(id).catch((err) => console.error(`[report#${id}] 生成失败:`, err.message));

    res.status(201).json({ id, status: 'processing', scores });
  } catch (err) {
    console.error('[assessments] 提交失败:', err);
    res.status(500).json({ error: `提交失败: ${err.message}` });
  }
});

async function generateReport(id) {
  try {
    const { rows } = await query('SELECT * FROM assessments WHERE id = $1', [id]);
    const rec = rows[0];
    if (!rec) return;

    const scores = rec.scores;
    const scoreSummary = buildScoreSummary(scores, {
      evaluateeName: rec.evaluatee_name,
      department: rec.department,
      position: rec.position,
      evaluatorName: rec.evaluator_name,
      relationship: rec.relationship,
      workDuration: rec.work_duration,
      period: rec.period
    }, rec.open_answers, rec.overall);

    // 1) 评价结论 与 网络搜索 并行执行
    const [conclusionResult, searchResults] = await Promise.allSettled([
      generateConclusion(scoreSummary, scores),
      searchLearningResources(scores.dimensions)
    ]);

    const conclusion =
      conclusionResult.status === 'fulfilled'
        ? conclusionResult.value
        : fallbackConclusion(scores, rec);
    if (conclusionResult.status === 'rejected') {
      console.warn(`[report#${id}] DeepSeek 生成评价结论失败，使用规则降级结论:`, conclusionResult.reason?.message);
    }

    const resources = searchResults.status === 'fulfilled' ? searchResults.value : [];
    const searchContext = formatSearchContext(resources);

    // 2) 学习建议（结合知识库 + 搜索资源）
    const knowledgeContext = [
      CORE_METHODOLOGY,
      ...Object.values(DIMENSION_KNOWLEDGE).map((k) =>
        `【${k.name}】要点：${k.essentials.join('；')}\n推荐书籍：${k.books.join('、')}\n实践建议：${k.practices.join('；')}`
      ),
      `成长原则：${GROWTH_PRINCIPLES.join('；')}`
    ].join('\n\n');

    let advice;
    try {
      advice = await generateLearningAdvice({ scoreSummary, knowledgeContext, searchContext });
    } catch (err) {
      console.warn(`[report#${id}] DeepSeek 生成学习建议失败，使用知识库降级建议:`, err.message);
      advice = fallbackAdvice(scores, knowledgeContext);
    }

    await query(
      `UPDATE assessments
         SET conclusion = $1, learning_advice = $2, learning_resources = $3, model = $4,
             status = 'completed', error = NULL, updated_at = now()
       WHERE id = $5`,
      [conclusion, advice, JSON.stringify(resources.slice(0, 30)), config.deepseekModel, id]
    );
    console.log(`[report#${id}] 报告生成完成`);
  } catch (err) {
    await query(
      `UPDATE assessments SET status = 'failed', error = $1, updated_at = now() WHERE id = $2`,
      [err.message, id]
    ).catch(() => {});
    console.error(`[report#${id}]`, err);
  }
}

// ---------- 列表 ----------
router.get('/assessments', async (_req, res) => {
  try {
    const { rows } = await query(
      `SELECT id, evaluatee_name, department, position, relationship, period,
              scores->>'totalScore' AS total_score, status, created_at
         FROM assessments ORDER BY created_at DESC LIMIT 100`
    );
    res.json(rows);
  } catch (err) {
    console.error('[assessments] 查询列表失败:', err);
    res.status(500).json({ error: `查询失败: ${err.message}` });
  }
});

// ---------- 详情 ----------
router.get('/assessments/:id', async (req, res) => {
  try {
    const { rows } = await query('SELECT * FROM assessments WHERE id = $1', [req.params.id]);
    if (rows.length === 0) return res.status(404).json({ error: '记录不存在' });
    res.json(rows[0]);
  } catch (err) {
    res.status(500).json({ error: `查询失败: ${err.message}` });
  }
});

// ---------- 降级：规则版结论 ----------
function fallbackConclusion(scores, rec) {
  const lines = ['> 注：AI 生成暂不可用，以下为基于评分规则的自动结论。\n'];
  lines.push(`## 总体评价\n加权总分 **${scores.totalScore ?? '无'}**，等级：**${scores.band ? scores.band.label : '无法判断'}**（${scores.band ? scores.band.desc : ''}）。\n`);
  lines.push('## 分维度得分');
  for (const d of scores.dimensions) {
    lines.push(`- **${d.name}**：${d.score ?? '无有效评分'}（权重 ${Math.round(d.weight * 100)}%）`);
    for (const s of d.sections) lines.push(`  - ${s.name}：${s.score ?? '无'}`);
  }
  if (scores.weakPoints.length) {
    lines.push('\n## 主要短板（低于3分的题目）');
    for (const p of scores.weakPoints) lines.push(`- [${p.dimension}] ${p.text}（${p.score}分）`);
  }
  if (scores.strongPoints.length) {
    lines.push('\n## 关键优势（4分及以上题目，示例）');
    for (const p of scores.strongPoints.slice(0, 8)) lines.push(`- [${p.dimension}] ${p.text}（${p.score}分）`);
  }
  return lines.join('\n');
}

// ---------- 降级：知识库版学习建议 ----------
function fallbackAdvice(scores, knowledgeContext) {
  const lines = ['> 注：AI 生成暂不可用，以下为基于知识库的默认学习建议。\n'];
  const sorted = [...scores.dimensions].filter((d) => d.score !== null).sort((a, b) => a.score - b.score);
  lines.push('## 优先提升维度（按得分从低到高）');
  for (const d of sorted) lines.push(`- **${d.name}**：${d.score} 分`);
  for (const d of sorted.slice(0, 2)) {
    const k = DIMENSION_KNOWLEDGE[d.key];
    if (!k) continue;
    lines.push(`\n## ${k.name} 学习建议`);
    lines.push('**学习要点**');
    k.essentials.forEach((e) => lines.push(`- ${e}`));
    lines.push('**推荐书籍**');
    k.books.forEach((b) => lines.push(`- ${b}`));
    lines.push('**实践行动**');
    k.practices.forEach((p) => lines.push(`- ${p}`));
  }
  lines.push('\n## 成长原则');
  GROWTH_PRINCIPLES.forEach((p) => lines.push(`- ${p}`));
  lines.push(`\n<details><summary>知识库全文</summary>\n\n${knowledgeContext}\n\n</details>`);
  return lines.join('\n');
}
