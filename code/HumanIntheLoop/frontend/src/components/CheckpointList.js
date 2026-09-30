import React from 'react';

const DECISION_META = {
  approve: { label: '✅ 同意', cls: 'decision-approve' },
  reject:  { label: '❌ 拒绝', cls: 'decision-reject' },
  modify:  { label: '✏️ 修改', cls: 'decision-modify' },
};

/**
 * 把平铺的 checkpoint 列表按 parent_id 组织成树（森林）。
 * LangGraph 的 checkpoint 天然构成一棵树：
 *   根节点 = 首条消息；每次「时间回溯」都会从历史节点分叉出新分支。
 * 返回根节点数组，每个节点形如 { ...cp, children: [...] }。
 */
function buildTree(checkpoints) {
  const byId = new Map();
  const sorted = [...checkpoints].sort(
    (a, b) =>
      (a.step ?? 0) - (b.step ?? 0) ||
      new Date(a.created_at) - new Date(b.created_at)
  );
  for (const cp of sorted) {
    byId.set(cp.checkpoint_id, { ...cp, children: [] });
  }
  const roots = [];
  for (const cp of sorted) {
    const node = byId.get(cp.checkpoint_id);
    const parent = cp.parent_id ? byId.get(cp.parent_id) : null;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  return roots;
}

/** 收集「当前 checkpoint → 根」路径上所有祖先 id，用于高亮当前分支 */
function collectPathIds(checkpoints, currentId) {
  const byId = new Map(checkpoints.map((c) => [c.checkpoint_id, c]));
  const path = new Set();
  let cur = currentId && byId.get(currentId);
  while (cur) {
    path.add(cur.checkpoint_id);
    cur = cur.parent_id ? byId.get(cur.parent_id) : null;
  }
  return path;
}

export default function CheckpointList({ checkpoints, currentId, onReplay }) {
  if (!checkpoints || checkpoints.length === 0) {
    return <div className="empty-state">尚无 checkpoint</div>;
  }

  const roots = buildTree(checkpoints);
  const pathIds = collectPathIds(checkpoints, currentId);

  return (
    <div className="checkpoint-tree">
      {roots.map((root) => (
        <CheckpointNode
          key={root.checkpoint_id}
          node={root}
          depth={0}
          currentId={currentId}
          pathIds={pathIds}
          onReplay={onReplay}
          isLastSibling={true}
        />
      ))}
      <div className="checkpoint-tree-legend">
        树形视图：每次时间回溯会从历史节点分叉出新分支，当前分支已高亮
      </div>
    </div>
  );
}

function CheckpointNode({ node, depth, currentId, pathIds, onReplay, isLastSibling }) {
  const isCurrent = node.checkpoint_id === currentId;
  const onPath = pathIds.has(node.checkpoint_id);
  const dec = DECISION_META[node.decision];
  const isBranchPoint = node.children.length > 1;

  return (
    <div
      className={`checkpoint-branch ${isLastSibling ? 'last' : ''}`}
    >
      <div
        className={[
          'checkpoint-item',
          isCurrent ? 'current' : '',
          onPath ? 'on-path' : '',
          dec ? dec.cls : '',
          isBranchPoint ? 'branch-point' : '',
        ]
          .filter(Boolean)
          .join(' ')}
        style={{ paddingLeft: depth * 18 }}
      >
        <div className="checkpoint-line">
          {depth > 0 && (
            <span className="checkpoint-branch-mark">{isLastSibling ? '└' : '├'}</span>
          )}
          <span className="checkpoint-step">step {node.step}</span>
          {isCurrent && <span className="checkpoint-tag">current</span>}
          {isBranchPoint && !isCurrent && (
            <span className="checkpoint-tag branch-tag">分支</span>
          )}
          {dec && <span className="checkpoint-decision">{dec.label}</span>}
          <span className="checkpoint-id">{node.checkpoint_id.slice(0, 8)}</span>
        </div>
        <div className="checkpoint-meta">
          next: [{node.next_nodes?.join(', ') || 'END'}]
        </div>
        {node.decision_note && (
          <div className="checkpoint-note">📝 {node.decision_note}</div>
        )}
        <div className="checkpoint-time">
          {new Date(node.created_at).toLocaleString()}
        </div>
        {!isCurrent && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => onReplay(node.checkpoint_id)}
          >
            ⏪ 时间回溯到此
          </button>
        )}
      </div>

      {node.children.length > 0 && (
        <div className="checkpoint-children">
          {node.children.map((child, i) => (
            <CheckpointNode
              key={child.checkpoint_id}
              node={child}
              depth={depth + 1}
              currentId={currentId}
              pathIds={pathIds}
              onReplay={onReplay}
              isLastSibling={i === node.children.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}
