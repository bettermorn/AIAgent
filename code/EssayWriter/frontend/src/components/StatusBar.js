import React from 'react';

const STAGES = [
  { key: 'planner', label: '1. 拟定大纲' },
  { key: 'research_plan', label: '2. 检索资料' },
  { key: 'generate', label: '3. 撰写草稿' },
  { key: 'reflect', label: '4. 教师批改' },
  { key: 'research_critique', label: '5. 补充资料' },
];

function StatusBar({ currentNode, revisionNumber, maxRevisions, error, done }) {
  if (error) {
    return (
      <div className="status-bar error">
        <span>生成出错：{error}</span>
      </div>
    );
  }
  if (!currentNode && !done) return null;

  if (done) {
    return (
      <div className="status-bar done">
        <span>✅ 全部完成 · 共迭代 {revisionNumber} 轮（最大 {maxRevisions}）</span>
      </div>
    );
  }

  const idx = STAGES.findIndex((s) => s.key === currentNode);
  return (
    <div className="status-bar running">
      <div className="status-stages">
        {STAGES.map((s, i) => (
          <div
            key={s.key}
            className={`stage-chip ${i <= idx ? 'active' : ''} ${
              i === idx ? 'current' : ''
            }`}
          >
            {s.label}
          </div>
        ))}
      </div>
      <div className="status-meta">
        当前：{STAGES[idx]?.label || currentNode} · 第 {revisionNumber} 轮
      </div>
    </div>
  );
}

export default StatusBar;