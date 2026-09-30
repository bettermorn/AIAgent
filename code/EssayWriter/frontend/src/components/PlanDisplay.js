import React from 'react';

function PlanDisplay({ plan }) {
  if (!plan) {
    return (
      <div className="card empty">
        <h3>📋 写作大纲</h3>
        <p className="empty-text">尚未生成</p>
      </div>
    );
  }
  return (
    <div className="card">
      <h3>📋 写作大纲</h3>
      <pre className="text-block">{plan}</pre>
    </div>
  );
}

export default PlanDisplay;