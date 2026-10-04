import { Router } from 'express';
import { pool } from '../db.js';
import { computeSelfScores, gradeTasks, generateConclusion } from '../services/assessment.js';
import { generateAdvice } from '../services/advice.js';
import { TASK_QUESTIONS, SELF_RATING_ITEMS } from '../data/questionnaire.js';

export const router = Router();

// 获取问卷结构（题目 + 评分标准不含参考答案，防止泄题）
router.get('/questionnaire', (req, res) => {
  res.json({
    basicInfoFields: ['grade', 'programmingExp', 'languages', 'chartsUsage'],
    selfRatingItems: SELF_RATING_ITEMS.map(({ id, no, dimension, text, reverse }) => ({ id, no, dimension, text, reverse: !!reverse })),
    taskQuestions: TASK_QUESTIONS.map(({ id, no, section, dimension, maxScore, title, prompt, type }) => ({ id, no, section, dimension, maxScore, title, prompt, type })),
  });
});

// 提交问卷：计算自评分 → DeepSeek 判分 → 生成结论 → 存库
router.post('/submit', async (req, res) => {
  try {
    const { studentName, basicInfo = {}, selfRating = {}, tasks = {} } = req.body;
    if (!studentName?.trim()) return res.status(400).json({ error: '请填写学生姓名' });

    const requiredSelf = SELF_RATING_ITEMS.filter((i) => !selfRating[i.id]);
    if (requiredSelf.length) {
      return res.status(400).json({ error: `自评量表第 ${requiredSelf.map((i) => i.no).join('、')} 题未作答` });
    }
    const unanswered = TASK_QUESTIONS.filter((q) => !(tasks[q.id] || '').trim());
    if (unanswered.length > 10) {
      return res.status(400).json({ error: '情境测试作答太少，无法有效评价' });
    }

    const studentInfo = {
      name: studentName.trim(),
      grade: basicInfo.grade || '未知年级',
      programmingExp: basicInfo.programmingExp || '未说明',
      languages: basicInfo.languages || [],
      languagesText: (basicInfo.languages || []).join('、') || '无',
      chartsUsage: basicInfo.chartsUsage || '未说明',
    };

    // 1. 自评计分
    const selfResult = computeSelfScores(selfRating);

    // 2. DeepSeek 情境判分
    const taskResult = await gradeTasks(tasks, studentInfo, selfResult.scores);

    // 3. 生成评价结论
    const conclusion = await generateConclusion(studentInfo, selfResult, taskResult);

    // 4. 存库
    const { rows } = await pool.query(
      `INSERT INTO assessments
        (student_name, grade, programming_exp, languages, charts_usage, answers,
         self_scores, self_levels, test_scores, dimension_scores, task_detail,
         total_score, percentage, level, conclusion)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
       RETURNING id`,
      [
        studentInfo.name, studentInfo.grade, studentInfo.programmingExp,
        JSON.stringify(studentInfo.languages), studentInfo.chartsUsage,
        JSON.stringify({ selfRating, tasks }),
        JSON.stringify(selfResult.scores), JSON.stringify(selfResult.levels),
        JSON.stringify({ dimensionComments: taskResult.dimensionComments, strengths: taskResult.strengths, weaknesses: taskResult.weaknesses, sectionMax: taskResult.sectionMax }),
        JSON.stringify(taskResult.dimensionScores),
        JSON.stringify(taskResult.detail),
        taskResult.total, taskResult.percentage, taskResult.level.level, conclusion,
      ]
    );

    res.json({
      id: rows[0].id,
      selfResult,
      taskResult,
      conclusion,
    });
  } catch (e) {
    console.error('[submit] 失败:', e);
    res.status(500).json({ error: `评价失败: ${e.message}` });
  }
});

// 生成学习建议（可重复生成）
router.post('/:id/advice', async (req, res) => {
  try {
    const { rows } = await pool.query('SELECT * FROM assessments WHERE id = $1', [req.params.id]);
    if (!rows.length) return res.status(404).json({ error: '未找到该测评记录' });
    const record = rows[0];

    const advice = await generateAdvice(record);
    await pool.query('UPDATE assessments SET advice = $1 WHERE id = $2', [JSON.stringify(advice), record.id]);
    res.json(advice);
  } catch (e) {
    console.error('[advice] 失败:', e);
    res.status(500).json({ error: `生成学习建议失败: ${e.message}` });
  }
});

// 测评详情
router.get('/:id', async (req, res) => {
  try {
    const { rows } = await pool.query('SELECT * FROM assessments WHERE id = $1', [req.params.id]);
    if (!rows.length) return res.status(404).json({ error: '未找到该测评记录' });
    res.json(rows[0]);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// 历史记录列表
router.get('/', async (req, res) => {
  try {
    const { rows } = await pool.query(
      `SELECT id, student_name, grade, percentage, level,
              (advice IS NOT NULL) AS has_advice, created_at
       FROM assessments ORDER BY created_at DESC LIMIT 50`
    );
    res.json(rows);
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});
