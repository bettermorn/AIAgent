import { chat, parseJsonOutput } from './deepseek.js';
import { webSearch } from './search.js';
import { LANGUAGE_TRAINING_KB, DAILY_TRAINING_KB } from '../data/knowledge.js';

// 根据学生的编程语言经历，挑选最相关的语言训练知识
function pickLanguageKb(languages) {
  const normalized = (languages || []).map((l) => String(l).toLowerCase());
  let lang = null;
  if (normalized.some((l) => l.includes('c'))) lang = 'C/C++';
  else if (normalized.some((l) => l.includes('java'))) lang = 'Java';
  else if (normalized.some((l) => l.includes('python'))) lang = 'Python';
  return lang;
}

// ---------- 生成学习建议（结合本地知识库 + 互联网搜索）----------
export async function generateAdvice(record) {
  const studentInfo = {
    name: record.student_name,
    grade: record.grade,
    programmingExp: record.programming_exp,
    languages: record.languages || [],
    chartsUsage: record.charts_usage,
  };
  const selfScores = record.self_scores || {};
  const dimScores = record.dimension_scores || {};
  const sectionMax = { decomposition: 20, pattern: 13, abstraction: 16, algorithm: 16, comprehensive: 12, ai: 8 };

  // 1. 先做互联网搜索：针对薄弱维度搜索学习资源
  const weakDims = Object.keys(sectionMax)
    .filter((k) => (dimScores[k] || 0) / sectionMax[k] < 0.7)
    .slice(0, 2);
  const dimNames = {
    decomposition: '问题分解', pattern: '模式识别', abstraction: '抽象思维',
    algorithm: '算法设计', comprehensive: '计算思维综合运用', ai: '人工智能基础',
  };
  const searchQueries = (weakDims.length ? weakDims : ['decomposition', 'pattern'])
    .map((k) => `高中生 ${dimNames[k]} 计算思维 训练方法 学习资源`);
  searchQueries.push('中学生 计算思维 培养 练习');

  const searchResults = [];
  for (const q of searchQueries) {
    try {
      const rs = await webSearch(q, { limit: 5 });
      searchResults.push(...rs.map((r) => `[${r.title}](${r.url}) ${r.snippet}`.slice(0, 300)));
    } catch (e) {
      console.warn('[advice] 搜索失败:', q, e.message);
    }
  }

  // 2. 组装本地知识库内容
  const lang = pickLanguageKb(studentInfo.languages);
  const langKb = lang
    ? `学生接触过 ${lang}（${LANGUAGE_TRAINING_KB[lang].focus}）针对各维度的训练知识：${JSON.stringify(LANGUAGE_TRAINING_KB[lang].dimensions)}`
    : `学生暂无明确编程语言基础，可从 Python 入门（${LANGUAGE_TRAINING_KB.Python.focus}）`;

  const systemPrompt = `你是一位专业的高中信息技术教师和学习规划顾问，需要为学生生成一份可操作的"计算思维学习建议"。

建议必须基于两部分材料：
A. 本地知识库（来自《用不同语言训练计算思维》和《日常任务练习计算思维》）：
- 语言训练知识库：${langKb}
- 日常任务训练知识库：${JSON.stringify(DAILY_TRAINING_KB)}

B. 互联网搜索到的参考资料（仅作为补充，挑选其中与本学生相关的、可靠的资源推荐给学生）：
${searchResults.length ? searchResults.join('\n') : '（本次搜索暂无结果，请主要依据本地知识库给出建议）'}

要求：
1. 建议必须针对该生的薄弱维度，具体、可执行、分阶段。
2. 结合学生编程水平：无基础的学生以日常任务训练和可视化工具为主；有编程基础的学生给出对应编程语言的训练路径。
3. 每个建议说明"练什么、怎么练、如何检验效果"。
4. 推荐资源链接时使用搜索结果中真实存在的 URL。
5. 全部使用中文。

请严格输出如下 JSON（不要输出任何其他内容）：
{
  "overall": "总体学习建议（150-250字，指出重点提升方向和大致时间规划）",
  "dimensionAdvice": [
    {
      "dimension": "decomposition|pattern|abstraction|algorithm",
      "dimensionName": "维度中文名",
      "priority": "高|中|低",
      "currentIssue": "当前主要问题（1-2句）",
      "actions": ["具体行动1：练什么、怎么练", "具体行动2", "具体行动3"],
      "dailyPractice": "结合日常生活的一个练习示例",
      "programmingPractice": "结合编程语言（或Scratch/流程图）的一个练习示例"
    }
  ],
  "weeklyPlan": ["第1周：...", "第2周：...", "第3周：...", "第4周：..."],
  "resources": [
    {"name": "资源名称", "type": "文章|课程|工具|视频", "description": "简介", "url": "链接或'—'"}
  ],
  "checkMethod": "如何检验训练效果（列出具体检验方法，100字左右）"
}`;

  const userPrompt = `学生：${studentInfo.name || '某同学'}，${studentInfo.grade}，编程经历：${studentInfo.programmingExp}，接触过的语言：${(studentInfo.languages || []).join('、') || '无'}，使用图表整理问题的频率：${studentInfo.chartsUsage}。

测评结果：
- 情境测试百分制得分：${record.percentage}，能力水平：${record.level}
- 各维度实测得分：分解问题 ${dimScores.decomposition || 0}/20，模式识别 ${dimScores.pattern || 0}/13，抽象 ${dimScores.abstraction || 0}/16，算法设计 ${dimScores.algorithm || 0}/16，综合开放题 ${dimScores.comprehensive || 0}/12，人工智能 ${dimScores.ai || 0}/8
- 自评得分：分解问题 ${selfScores.decomposition || 0}/25，模式识别 ${selfScores.pattern || 0}/25，抽象 ${selfScores.abstraction || 0}/25，算法设计 ${selfScores.algorithm || 0}/25
- 测评中发现的不足：${JSON.stringify(record.test_scores?.weaknesses || record.task_detail?.weaknesses || [])}

请为该学生生成学习建议。注意：请控制输出长度，dimensionAdvice 最多4项、resources 最多6项，确保 JSON 完整。`;

  // 大模型输出可能被截断或格式异常，最多重试2次
  let advice = null;
  let lastErr = null;
  for (let attempt = 0; attempt < 3 && !advice; attempt++) {
    try {
      const raw = await chat(
        [{ role: 'system', content: systemPrompt }, { role: 'user', content: userPrompt }],
        { temperature: attempt === 0 ? 0.5 : 0.2, jsonMode: true, maxTokens: 8000 }
      );
      advice = parseJsonOutput(raw);
    } catch (e) {
      lastErr = e;
      console.warn(`[advice] 第${attempt + 1}次生成失败，${attempt < 2 ? '重试中' : '放弃'}:`, e.message);
    }
  }
  if (!advice) throw lastErr || new Error('学习建议 JSON 解析失败');

  return {
    ...advice,
    _meta: {
      generatedAt: new Date().toISOString(),
      searchQueries,
      searchResultCount: searchResults.length,
      referencedKnowledge: ['用不同语言训练计算思维', '日常任务练习计算思维'],
    },
  };
}
