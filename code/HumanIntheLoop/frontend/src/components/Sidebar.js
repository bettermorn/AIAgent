import React from 'react';
import { useToast } from './Toast';

export default function Sidebar({ threads, currentId, onSelect, onCreate, onDelete }) {
  const toast = useToast();

  async function handleDelete(threadId, title) {
    const ok = await toast.confirm({
      kind: 'error',
      title: '删除会话',
      message: `确认删除「${title || '未命名'}」及其所有 checkpoint 吗？此操作不可撤销。`,
      confirmText: '删除',
      danger: true,
    });
    if (ok) {
      // 只在父组件 App.js 的 onDelete 中统一提示，避免出现两条「会话已删除」
      onDelete(threadId);
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>会话</h2>
        <button className="btn btn-primary btn-sm" onClick={onCreate}>
          ＋ 新建
        </button>
      </div>
      <div className="thread-list">
        {threads.length === 0 && (
          <div className="empty-state">还没有会话，点击「新建」开始</div>
        )}
        {threads.map((t) => (
          <div
            key={t.thread_id}
            className={`thread-item ${t.thread_id === currentId ? 'active' : ''}`}
            onClick={() => onSelect(t.thread_id)}
          >
            <div className="thread-title">{t.title || '未命名会话'}</div>
            <div className="thread-time">
              {new Date(t.updated_at).toLocaleString()}
            </div>
            <button
              className="btn btn-ghost btn-xs thread-delete"
              onClick={(e) => {
                e.stopPropagation();
                handleDelete(t.thread_id, t.title);
              }}
              aria-label="删除会话"
            >
              🗑
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}