import React, { useEffect, useState } from 'react';
import { api } from '../api.js';

const SECTION_TITLES = {
  '分解问题': '一、分解问题',
  '模式识别': '二、模式识别',
  '抽象': '三、抽象',
  '算法设计': '四、算法设计',
  '综合开放测试': '五、综合开放测试',
  '人工智能与计算思维': '六、人工智能与计算思维',
};

export default function TasksStep({ tasks, setTasks, onPrev, onSubmit, submitting }) {
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getQuestionnaire()
      .then((d) => setQuestions(d.taskQuestions))
      .catch(() => setQuestions([]))
      .finally(() => setLoading(false));
  }, []);

  const answeredCount = questions.filter((q) => (tasks[q.id] || '').trim()).length;
  const totalScore = questions.reduce((s, q) => s + q.maxScore, 0);

  function renderSection(section) {
    const group = questions.filter((q) => q.section === section);
    if (!group.length) return null;
    return (
      <div className="task-group" key={section}>
        <h3 className="self-group-title">{SECTION_TITLES[section] || section}</h3>
        {group.map((q) => (
          <div className="task-item" key={q.id}>
            <div className="task-header">
              <span className="task-title">第 {q.no} 题 · {q.title}</span>
              <span className="badge-score">{q.maxScore} 分</span>
            </div>
            <pre className="task-prompt">{q.prompt}</pre>
            <textarea
              className="task-answer"
              placeholder="请在此写下你的答案…（可以用自然语言、伪代码或流程图描述）"
              rows={Math.min(12, Math.max(5, Math.ceil(q.prompt.length / 40) + 3))}
              value={tasks[q.id] || ''}
              onChange={(e) => setTasks({ ...tasks, [q.id]: e.target.value })}
            />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="panel">
      <h2 className="panel-title">第三部分 · 情境与能力测试</h2>
      <p className="panel-desc">
        本部分考查实际计算思维能力，请根据题意认真作答。答题时除特别说明外不建议使用网络搜索。
        <span className="progress-text"> 已答 {answeredCount}/{questions.length} 题（共 {totalScore} 分）</span>
      </p>
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${questions.length ? (answeredCount / questions.length) * 100 : 0}%` }} />
      </div>

      {loading ? (
        <div className="loading-inline">加载题目中…</div>
      ) : (
        Object.keys(SECTION_TITLES).map(renderSection)
      )}

      <div className="step-actions">
        <button className="btn-ghost" onClick={onPrev} disabled={submitting}>← 上一步</button>
        <button className="btn-primary btn-lg" disabled={submitting || answeredCount < questions.length - 2} onClick={onSubmit}>
          {submitting ? '提交中…' : '提交答卷，生成评价'}
        </button>
      </div>
      {answeredCount < questions.length && answeredCount >= questions.length - 2 && (
        <p className="hint">还有个别题目未作答，未作答题目将按 0 分计算。</p>
      )}
    </div>
  );
}
