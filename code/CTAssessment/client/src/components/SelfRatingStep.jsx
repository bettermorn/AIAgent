import React from 'react';
import { api } from '../api.js';

const SCALE = [
  { value: 1, label: '非常不同意' },
  { value: 2, label: '不同意' },
  { value: 3, label: '不确定' },
  { value: 4, label: '同意' },
  { value: 5, label: '非常同意' },
];

const DIM_TITLES = {
  decomposition: 'A. 分解问题',
  pattern: 'B. 模式识别',
  abstraction: 'C. 抽象',
  algorithm: 'D. 算法设计',
};

export default function SelfRatingStep({ selfRating, setSelfRating, onPrev, onNext }) {
  const [items, setItems] = React.useState([]);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    api.getQuestionnaire()
      .then((d) => setItems(d.selfRatingItems))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const answeredCount = Object.keys(selfRating).length;

  function renderGroup(dim) {
    const group = items.filter((i) => i.dimension === dim);
    if (!group.length) return null;
    return (
      <div className="self-group" key={dim}>
        <h3 className="self-group-title">{DIM_TITLES[dim]}</h3>
        {group.map((item) => (
          <div className="self-item" key={item.id}>
            <div className="self-question">
              <span className="q-no">{item.no}.</span> {item.text}
              {item.reverse && <span className="badge-reverse">反向题</span>}
            </div>
            <div className="scale">
              {SCALE.map((s) => (
                <button
                  key={s.value}
                  type="button"
                  className={`scale-btn ${selfRating[item.id] === s.value ? 'selected' : ''}`}
                  onClick={() => setSelfRating({ ...selfRating, [item.id]: s.value })}
                  title={s.label}
                >
                  {s.value}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="panel">
      <h2 className="panel-title">第二部分 · 计算思维自评量表</h2>
      <p className="panel-desc">
        请根据自己的实际情况选择（1=非常不同意，5=非常同意）。自评结果只反映主观感受，会结合后面的情境任务综合评价。
        <span className="progress-text"> 已答 {answeredCount}/20</span>
      </p>
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${(answeredCount / 20) * 100}%` }} />
      </div>

      {loading ? (
        <div className="loading-inline">加载题目中…</div>
      ) : (
        Object.keys(DIM_TITLES).map(renderGroup)
      )}

      <div className="step-actions">
        <button className="btn-ghost" onClick={onPrev}>← 上一步</button>
        <button className="btn-primary" disabled={answeredCount < 20} onClick={onNext}>
          下一步：情境测试 →
        </button>
      </div>
    </div>
  );
}
