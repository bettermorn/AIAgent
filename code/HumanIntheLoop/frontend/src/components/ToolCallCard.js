import React from 'react';
import { useToast } from './Toast';

/**
 * 工具调用卡片 - 展示 LLM 想调用的工具，支持三大分支：
 *  - 同意（approve）：发送给后端按原始参数执行  →  decision = 'approve'
 *  - 拒绝（reject）：让模型放弃工具，基于已有信息回答 →  decision = 'reject'
 *  - 修改（modify）：编辑参数后再执行  →  decision = 'modify'
 *
 *  onApprove(modifications) 接收 [{ id, name, args, modified }]
 *    - modified=true   → App.js 走 /modify 分支
 *    - modified=false  → App.js 走 /approve 分支
 */
export default function ToolCallCard({ toolCall, index, onApprove, onReject }) {
  const toast = useToast();
  const [editing, setEditing] = React.useState(false);
  const [editedArgs, setEditedArgs] = React.useState(
    JSON.stringify(toolCall.args || {}, null, 2)
  );

  // 进入编辑模式时，若 args 变更需重置 editedArgs
  React.useEffect(() => {
    setEditedArgs(JSON.stringify(toolCall.args || {}, null, 2));
  }, [toolCall.id, toolCall.args]);

  /** 共用的"提交审批"逻辑（不论是否改参数都走这里） */
  const submit = (modified) => {
    let args = toolCall.args;
    if (modified) {
      try {
        args = JSON.parse(editedArgs);
      } catch (e) {
        toast.error('参数 JSON 格式错误: ' + e.message);
        return;
      }
    }
    onApprove([{ id: toolCall.id, name: toolCall.name, args, modified }]);
    setEditing(false);
  };

  return (
    <div className="tool-call-card">
      <div className="tool-call-header">
        <span className="tool-call-badge">🔧 工具调用 #{index + 1}</span>
        <span className="tool-call-name">{toolCall.name}</span>
      </div>

      {editing ? (
        <textarea
          className="tool-call-editor"
          value={editedArgs}
          onChange={(e) => setEditedArgs(e.target.value)}
          spellCheck={false}
          rows={4}
        />
      ) : (
        <pre className="tool-call-args">{JSON.stringify(toolCall.args, null, 2)}</pre>
      )}

      <div className="tool-call-actions">
        {/* 编辑模式下：只显示一个 "保存修改并执行" 按钮，避免和"同意执行"重复 */}
        {editing ? (
          <>
            <button className="btn btn-primary" onClick={() => submit(true)}>
              ✅ 保存修改并执行
            </button>
            <button className="btn btn-ghost" onClick={() => setEditing(false)}>
              ↩️ 取消编辑
            </button>
          </>
        ) : (
          <>
            <button className="btn btn-primary" onClick={() => submit(false)}>
              ✅ 同意执行（原始参数）
            </button>
            <button className="btn btn-danger" onClick={() => onReject(toolCall.id)}>
              ❌ 拒绝
            </button>
            <button className="btn btn-secondary" onClick={() => setEditing(true)}>
              ✏️ 修改参数
            </button>
          </>
        )}
      </div>
    </div>
  );
}