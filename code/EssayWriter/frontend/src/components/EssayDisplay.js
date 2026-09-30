import React, { useMemo } from 'react';

function EssayDisplay({ draft }) {
  const rendered = useMemo(() => draft || '', [draft]);
  if (!rendered) {
    return (
      <div className="card empty essay-card">
        <h3>📝 作文草稿</h3>
        <p className="empty-text">尚未生成</p>
      </div>
    );
  }
  return (
    <div className="card essay-card">
      <h3>📝 作文草稿</h3>
      <pre className="text-block essay-text">{rendered}</pre>
    </div>
  );
}

export default EssayDisplay;