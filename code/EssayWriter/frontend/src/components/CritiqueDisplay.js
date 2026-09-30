import React from 'react';

function CritiqueDisplay({ critique }) {
  if (!critique) {
    return (
      <div className="card empty">
        <h3>🧑‍🏫 教师批改</h3>
        <p className="empty-text">尚未批改</p>
      </div>
    );
  }
  return (
    <div className="card critique">
      <h3>🧑‍🏫 教师批改</h3>
      <pre className="text-block">{critique}</pre>
    </div>
  );
}

export default CritiqueDisplay;