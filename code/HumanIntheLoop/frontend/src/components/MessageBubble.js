import React from 'react';

const roleLabel = {
  user: '你',
  assistant: '助手',
  system: '系统',
  tool: '工具',
};

const roleClass = {
  user: 'msg-user',
  assistant: 'msg-assistant',
  system: 'msg-system',
  tool: 'msg-tool',
};

// 决策徽章：让"同意 / 拒绝 / 修改"在助手消息上一目了然
const DECISION_META = {
  approve: { label: '✅ 同意', cls: 'decision-approve' },
  reject:  { label: '❌ 拒绝', cls: 'decision-reject' },
  modify:  { label: '✏️ 修改', cls: 'decision-modify' },
};

export default function MessageBubble({ message }) {
  const cls = roleClass[message.role] || 'msg-assistant';
  const dec = message.decision ? DECISION_META[message.decision] : null;
  return (
    <div className={`message ${cls}${dec ? ' ' + dec.cls : ''}`}>
      <div className="message-avatar">
        {message.role === 'user' ? '🧑' : message.role === 'assistant' ? '🤖' : '⚙️'}
      </div>
      <div className="message-body">
        <div className="message-meta">
          <span className="message-role">{roleLabel[message.role] || message.role}</span>
          {dec && <span className="decision-badge">{dec.label}</span>}
        </div>
        {message.content && (
          <div className="message-text">{message.content}</div>
        )}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="message-tool-calls">
            {message.tool_calls.map((tc, i) => (
              <div key={tc.id || i} className="mini-tool-call">
                <strong>{tc.name}</strong>: {JSON.stringify(tc.args)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
