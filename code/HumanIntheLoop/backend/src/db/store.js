'use strict';

const { nanoid } = require('nanoid');
const { query, getClient } = require('./pool');

/* ============================================================
 * Thread
 * ============================================================ */

async function createThread(title = '新会话') {
  const threadId = nanoid(12);
  const client = await getClient();
  try {
    await client.query('BEGIN');
    await client.query(
      `INSERT INTO threads (thread_id, title) VALUES ($1, $2)`,
      [threadId, title]
    );
    // 预初始化 thread_state，使前端 GET 线程时不会因没有 checkpoint 而 404
    await client.query(
      `INSERT INTO thread_state (thread_id, current_cp_id, lnode, count, scratch)
       VALUES ($1, NULL, NULL, 0, NULL)
       ON CONFLICT (thread_id) DO NOTHING`,
      [threadId]
    );
    await client.query('COMMIT');
    return threadId;
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
  }
}

async function listThreads() {
  const { rows } = await query(
    `SELECT thread_id, title, created_at, updated_at
       FROM threads
       ORDER BY updated_at DESC
       LIMIT 100`
  );
  return rows;
}

async function getThread(threadId) {
  const { rows } = await query(
    `SELECT thread_id, title, created_at, updated_at
       FROM threads WHERE thread_id = $1`,
    [threadId]
  );
  return rows[0] || null;
}

async function deleteThread(threadId) {
  // 由于 messages / checkpoints / thread_state 都设置了 ON DELETE CASCADE，
  // 删除 threads 行会自动清理所有关联数据，无需手动逐表删除。
  const { rowCount } = await query(
    `DELETE FROM threads WHERE thread_id = $1`,
    [threadId]
  );
  return rowCount > 0;
}

async function renameThread(threadId, title) {
  await query(
    `UPDATE threads SET title = $1 WHERE thread_id = $2`,
    [title, threadId]
  );
}

/* ============================================================
 * Messages
 * ============================================================ */

/**
 * 替换 thread 中的所有 messages（实现 LangGraph 中 replace_messages 的合并语义）。
 * - 若消息 msg_id 已存在，则覆盖；
 * - 否则追加。
 */
/**
 * 保存消息（可复用外部事务连接）。
 * - 若消息 msg_id 已存在，则覆盖（保留分支内更新语义）；
 * - providedClient 传入时不再自行开事务，由调用方管理 COMMIT/ROLLBACK。
 */
async function saveMessages(threadId, messages, providedClient) {
  const client = providedClient || (await getClient());
  const ownsTx = !providedClient;
  try {
    if (ownsTx) await client.query('BEGIN');
    for (let i = 0; i < messages.length; i += 1) {
      const m = messages[i];
      await client.query(
        `INSERT INTO messages
            (thread_id, msg_id, role, content, name, tool_call_id, tool_calls, decision, reasoning_content, position)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
         ON CONFLICT (thread_id, msg_id) DO UPDATE SET
            role             = EXCLUDED.role,
            content          = EXCLUDED.content,
            name             = EXCLUDED.name,
            tool_call_id     = EXCLUDED.tool_call_id,
            tool_calls       = EXCLUDED.tool_calls,
            decision         = EXCLUDED.decision,
            reasoning_content= EXCLUDED.reasoning_content,
            position         = EXCLUDED.position`,
        [
          threadId,
          m.id,
          m.role,
          m.content ?? null,
          m.name ?? null,
          m.tool_call_id ?? null,
          m.tool_calls ? JSON.stringify(m.tool_calls) : null,
          m.decision ?? null,
          m.reasoning_content ?? null,
          i,
        ]
      );
    }
    if (ownsTx) await client.query('COMMIT');
  } catch (e) {
    if (ownsTx) await client.query('ROLLBACK');
    throw e;
  } finally {
    if (ownsTx) client.release();
  }
}

async function listMessages(threadId) {
  const { rows } = await query(
    `SELECT msg_id AS id, role, content, name, tool_call_id, tool_calls, decision, reasoning_content
       FROM messages
       WHERE thread_id = $1
       ORDER BY position ASC`,
    [threadId]
  );
  return rows.map((r) => ({
    id: r.id,
    role: r.role,
    content: r.content ?? '',
    name: r.name ?? null,
    tool_call_id: r.tool_call_id ?? null,
    tool_calls: r.tool_calls ?? null,
    decision: r.decision ?? null,
    reasoning_content: r.reasoning_content ?? null,
  }));
}

/* ============================================================
 * Checkpoint
 * ============================================================ */

async function saveCheckpoint(threadId, snapshot) {
  // snapshot: { parentId, step, nextNodes, messages, scratch, lnode, count,
  //             decision: 'approve'|'reject'|'modify'|null, decisionNote: string|null }
  const cpId = nanoid(16);
  const client = await getClient();
  try {
    await client.query('BEGIN');

    await client.query(
      `INSERT INTO checkpoints
         (checkpoint_id, thread_id, parent_id, step, next_nodes, decision, decision_note, scratch)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [
        cpId,
        threadId,
        snapshot.parentId || null,
        snapshot.step || 0,
        snapshot.nextNodes || [],
        snapshot.decision || null,
        snapshot.decisionNote || null,
        snapshot.scratch || null,
      ]
    );

    // 复用当前事务保存消息
    await saveMessages(threadId, snapshot.messages, client);

    // ★ 记录本 checkpoint 的消息快照（消息 id 的有序集合）。
    //   时间回溯时按此还原历史状态，避免把其它分支的消息混进来。
    for (let i = 0; i < snapshot.messages.length; i += 1) {
      const m = snapshot.messages[i];
      if (!m || !m.id) continue;
      await client.query(
        `INSERT INTO checkpoint_messages (checkpoint_id, thread_id, msg_id, position)
         VALUES ($1, $2, $3, $4)
         ON CONFLICT (checkpoint_id, msg_id) DO UPDATE SET position = EXCLUDED.position`,
        [cpId, threadId, m.id, i]
      );
    }

    await client.query(
      `INSERT INTO thread_state
         (thread_id, current_cp_id, lnode, count, scratch)
       VALUES ($1, $2, $3, $4, $5)
       ON CONFLICT (thread_id) DO UPDATE SET
         current_cp_id = EXCLUDED.current_cp_id,
         lnode         = EXCLUDED.lnode,
         count         = EXCLUDED.count,
         scratch       = EXCLUDED.scratch,
         updated_at    = NOW()`,
      [
        threadId,
        cpId,
        snapshot.lnode || null,
        snapshot.count || 0,
        snapshot.scratch || null,
      ]
    );

    await client.query('COMMIT');
    return cpId;
  } catch (e) {
    await client.query('ROLLBACK');
    throw e;
  } finally {
    client.release();
  }
}

/**
 * 读取某个 checkpoint 时刻的消息快照（按 checkpoint_messages 的顺序）。
 * 这是"时间回溯准确还原历史分支"的数据来源。
 * 兼容：快照表上线之前创建的旧 checkpoint 没有快照行，
 *       回退为整个 thread 的消息（旧行为，尽力而为）。
 */
async function listCheckpointMessages(checkpointId) {
  const { rows } = await query(
    `SELECT m.msg_id AS id, m.role, m.content, m.name, m.tool_call_id,
            m.tool_calls, m.decision, m.reasoning_content
       FROM checkpoint_messages cm
       JOIN messages m
         ON m.thread_id = cm.thread_id AND m.msg_id = cm.msg_id
      WHERE cm.checkpoint_id = $1
      ORDER BY cm.position ASC`,
    [checkpointId]
  );
  if (rows.length > 0) {
    return rows.map((r) => ({
      id: r.id,
      role: r.role,
      content: r.content ?? '',
      name: r.name ?? null,
      tool_call_id: r.tool_call_id ?? null,
      tool_calls: r.tool_calls ?? null,
      decision: r.decision ?? null,
      reasoning_content: r.reasoning_content ?? null,
    }));
  }
  // 旧数据回退：查 checkpoint 所属 thread，返回全部消息
  const cp = await query(
    `SELECT thread_id FROM checkpoints WHERE checkpoint_id = $1`,
    [checkpointId]
  );
  if (cp.rows[0]) return listMessages(cp.rows[0].thread_id);
  return [];
}

async function getCheckpoint(checkpointId) {
  const { rows } = await query(
    `SELECT checkpoint_id, thread_id, parent_id, step, next_nodes,
            decision, decision_note, scratch, created_at
       FROM checkpoints WHERE checkpoint_id = $1`,
    [checkpointId]
  );
  if (!rows[0]) return null;
  // ★ 使用快照消息（而非整个 thread 的全部消息），
  //   保证回溯时拿到的是该 checkpoint 时刻的真实历史状态
  const messages = await listCheckpointMessages(checkpointId);
  return {
    checkpoint_id: rows[0].checkpoint_id,
    thread_id: rows[0].thread_id,
    parent_id: rows[0].parent_id,
    step: rows[0].step,
    next_nodes: rows[0].next_nodes || [],
    decision: rows[0].decision,
    decision_note: rows[0].decision_note,
    scratch: rows[0].scratch,
    created_at: rows[0].created_at,
    messages,
  };
}

async function listCheckpoints(threadId) {
  const { rows } = await query(
    `SELECT checkpoint_id, parent_id, step, next_nodes,
            decision, decision_note, scratch, created_at
       FROM checkpoints
       WHERE thread_id = $1
       ORDER BY created_at DESC`,
    [threadId]
  );
  return rows;
}

async function getCurrentState(threadId) {
  const { rows } = await query(
    `SELECT current_cp_id, lnode, count, scratch
       FROM thread_state WHERE thread_id = $1`,
    [threadId]
  );
  if (!rows[0]) return null;
  // ★ 当前状态 = 当前 checkpoint 的快照消息。
  //   回溯/分支后，thread 里可能存在多条分支的消息，
  //   只读快照才能保证"当前分支"不被其它分支污染。
  const messages = rows[0].current_cp_id
    ? await listCheckpointMessages(rows[0].current_cp_id)
    : [];
  return {
    thread_id: threadId,
    checkpoint_id: rows[0].current_cp_id,
    lnode: rows[0].lnode,
    count: rows[0].count,
    scratch: rows[0].scratch,
    messages,
  };
}

module.exports = {
  createThread,
  listThreads,
  getThread,
  deleteThread,
  renameThread,
  saveMessages,
  listMessages,
  saveCheckpoint,
  getCheckpoint,
  listCheckpoints,
  listCheckpointMessages,
  getCurrentState,
};
