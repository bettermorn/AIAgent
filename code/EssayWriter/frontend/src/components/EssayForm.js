import React from 'react';

const PRESETS = [
  'the impact of artificial intelligence on modern education',
  'why renewable energy is critical for the next decade',
  'comparison of remote work and office work',
  'the role of reading in the age of short videos',
];

function EssayForm({ task, setTask, maxRevisions, setMaxRevisions, onSubmit, loading }) {
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!task.trim()) return;
    onSubmit();
  };

  return (
    <form className="essay-form" onSubmit={handleSubmit}>
      <label className="form-label">
        作文题目 / 主题
        <textarea
          className="form-textarea"
          rows={3}
          placeholder="例如：人工智能对现代教育的影响"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          disabled={loading}
        />
      </label>

      <label className="form-label">
        最大修订次数（1 - 5）
        <input
          type="number"
          min={1}
          max={5}
          value={maxRevisions}
          onChange={(e) =>
            setMaxRevisions(Math.min(5, Math.max(1, Number(e.target.value) || 1)))
          }
          disabled={loading}
          className="form-input"
        />
      </label>

      <div className="preset-row">
        <span className="preset-label">快速示例：</span>
        {PRESETS.map((p) => (
          <button
            key={p}
            type="button"
            className="preset-chip"
            disabled={loading}
            onClick={() => setTask(p)}
          >
            {p}
          </button>
        ))}
      </div>

      <button
        type="submit"
        className="submit-btn"
        disabled={loading || !task.trim()}
      >
        {loading ? '生成中…' : '开始生成'}
      </button>
    </form>
  );
}

export default EssayForm;