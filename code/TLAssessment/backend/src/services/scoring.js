import { questionnaire, DIMENSION_WEIGHTS, SCORE_BANDS } from '../data/questionnaire.js';

// 计算维度/子维度得分（N/A 不计入分母），源自问卷第八节计算方式
export function computeScores(answers, overallRatings = {}) {
  const dimensionResults = [];
  const weakPoints = [];   // 低于3分的题目
  const strongPoints = []; // 4分及以上的题目

  for (const dim of questionnaire) {
    const sectionResults = [];
    let dimSum = 0;
    let dimCount = 0;

    for (const sec of dim.sections) {
      let secSum = 0;
      let secCount = 0;
      for (const question of sec.questions) {
        const v = answers[String(question.id)];
        if (typeof v === 'number' && v >= 1 && v <= 5) {
          secSum += v;
          secCount++;
          if (v < 3) weakPoints.push({ id: question.id, text: question.text, score: v, dimension: dim.name, section: sec.name });
          if (v >= 4) strongPoints.push({ id: question.id, text: question.text, score: v, dimension: dim.name, section: sec.name });
        }
      }
      const secScore = secCount > 0 ? round2(secSum / secCount) : null;
      sectionResults.push({
        key: sec.key,
        name: sec.name,
        score: secScore,
        answered: secCount,
        total: sec.questions.length
      });
      if (secScore !== null) {
        dimSum += secSum;
        dimCount += secCount;
      }
    }

    dimensionResults.push({
      key: dim.key,
      name: dim.name,
      weight: dim.weight,
      score: dimCount > 0 ? round2(dimSum / dimCount) : null,
      answered: dimCount,
      total: dim.sections.reduce((s, x) => s + x.questions.length, 0),
      sections: sectionResults,
      overallRating: overallRatings[dim.key] ?? null
    });
  }

  // 加权总分（维度得分 * 建议权重）
  let weightedSum = 0;
  let weightSum = 0;
  for (const d of dimensionResults) {
    if (d.score !== null) {
      weightedSum += d.score * d.weight;
      weightSum += d.weight;
    }
  }
  const totalScore = weightSum > 0 ? round2(weightedSum / weightSum) : null;

  return {
    dimensions: dimensionResults,
    totalScore,
    band: getBand(totalScore),
    weakPoints,
    strongPoints,
    overallRating: overallRatings.overall ?? null
  };
}

export function getBand(score) {
  if (score === null || score === undefined) return null;
  for (const b of SCORE_BANDS) {
    if (score >= b.min && score <= b.max) return b;
  }
  return null;
}

function round2(n) {
  return Math.round(n * 100) / 100;
}

// 生成给 DeepSeek 的结构化评分摘要
export function buildScoreSummary(scores, basicInfo, openAnswers, overall) {
  const lines = [];
  lines.push(`被评价人：${basicInfo.evaluateeName || '未填写'}｜部门：${basicInfo.department || '未填写'}｜职位：${basicInfo.position || '未填写'}`);
  lines.push(`评价人：${basicInfo.evaluatorName || '未填写'}｜关系：${basicInfo.relationship || '未填写'}｜共事时间：${basicInfo.workDuration || '未填写'}｜评价周期：${basicInfo.period || '未填写'}`);
  lines.push('');
  lines.push('【各维度得分（1-5分，N/A不计入）】');
  for (const d of scores.dimensions) {
    lines.push(`- ${d.name}：${d.score ?? '无有效评分'}（权重${Math.round(d.weight * 100)}%，${d.answered}/${d.total}题有效）`);
    for (const s of d.sections) {
      lines.push(`  - ${s.name}：${s.score ?? '无有效评分'}`);
    }
  }
  lines.push(`加权总分：${scores.totalScore ?? '无'}（结果解释：${scores.band ? scores.band.label + '，' + scores.band.desc : '无'}）`);
  lines.push('');
  if (scores.strongPoints.length > 0) {
    lines.push('【高分题（≥4分）】');
    for (const p of scores.strongPoints.slice(0, 15)) lines.push(`- [${p.dimension}] ${p.text}（${p.score}分）`);
    lines.push('');
  }
  if (scores.weakPoints.length > 0) {
    lines.push('【低分题（<3分，重点关注）】');
    for (const p of scores.weakPoints) lines.push(`- [${p.dimension}/${p.section}] ${p.text}（${p.score}分）`);
    lines.push('');
  }
  if (openAnswers && Object.keys(openAnswers).length > 0) {
    lines.push('【开放题回答】');
    for (const dim of questionnaire) {
      (openAnswers[dim.key] || []).forEach((ans, i) => {
        if (ans && ans.trim()) lines.push(`- [${dim.name}] ${dim.openQuestions[i]}：${ans.trim()}`);
      });
    }
    lines.push('');
  }
  if (overall) {
    const parts = [];
    if (overall.topStrengths?.length) parts.push(`最突出的三项能力：${overall.topStrengths.filter(Boolean).join('、')}`);
    if (overall.topImprovements?.length) parts.push(`最需改进的三项能力：${overall.topImprovements.filter(Boolean).join('、')}`);
    if (overall.keyCase) parts.push(`关键事实与案例：${overall.keyCase}`);
    if (overall.developmentAreas?.length) parts.push(`建议重点提升方向：${overall.developmentAreas.filter(Boolean).join('、')}`);
    if (parts.length) {
      lines.push('【综合评价】');
      lines.push(parts.join('\n'));
    }
  }
  return lines.join('\n');
}
