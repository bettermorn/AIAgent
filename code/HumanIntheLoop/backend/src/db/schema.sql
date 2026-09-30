-- ============================================
-- Human in the Loop - PostgreSQL Schema
-- ============================================

-- 1. 线程（会话）表：每个会话对应一条 thread
CREATE TABLE IF NOT EXISTS threads (
    thread_id      TEXT PRIMARY KEY,
    title          TEXT NOT NULL DEFAULT '新会话',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. 消息表：保存 AgentState 中的 messages 列表
CREATE TABLE IF NOT EXISTS messages (
    id             BIGSERIAL PRIMARY KEY,
    thread_id      TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    msg_id         TEXT NOT NULL,
    role           TEXT NOT NULL,
    content        TEXT,
    name           TEXT,
    tool_call_id   TEXT,
    tool_calls     JSONB,
    -- 决策标签（仅 assistant 消息可能非空），便于在 UI 上追溯本次回复
    -- 是由哪种人工决策触发的：approve / reject / modify
    decision       TEXT,
    -- DeepSeek 思考模式的推理内容：带 tool_calls 的 assistant 消息
    -- 在回溯/重放时必须把 reasoning_content 原样传回 API，否则 400
    reasoning_content TEXT,
    position       INT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(thread_id, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, position);

-- 3. 检查点（checkpoint）表：保存 AgentState 快照，用于时间回溯
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id  TEXT PRIMARY KEY,
    thread_id      TEXT NOT NULL REFERENCES threads(thread_id) ON DELETE CASCADE,
    parent_id      TEXT REFERENCES checkpoints(checkpoint_id) ON DELETE SET NULL,
    step           INT NOT NULL DEFAULT 0,
    next_nodes     TEXT[] NOT NULL DEFAULT '{}',
    -- 决策类型分支标签：
    --   NULL         普通状态推进
    --   'approve'    人工同意执行工具
    --   'reject'     人工拒绝执行工具
    --   'modify'     人工修改工具参数后再执行
    decision       TEXT,
    decision_note  TEXT,
    scratch        TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_decision CHECK (decision IS NULL OR decision IN ('approve','reject','modify'))
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread ON checkpoints(thread_id, created_at DESC);

-- 兼容旧库：补齐缺失列
ALTER TABLE checkpoints ADD COLUMN IF NOT EXISTS decision      TEXT;
ALTER TABLE checkpoints ADD COLUMN IF NOT EXISTS decision_note TEXT;
ALTER TABLE messages   ADD COLUMN IF NOT EXISTS decision       TEXT;
ALTER TABLE messages   ADD COLUMN IF NOT EXISTS reasoning_content TEXT;

-- 4. 最新检查点指向：加速读取当前状态
CREATE TABLE IF NOT EXISTS thread_state (
    thread_id        TEXT PRIMARY KEY REFERENCES threads(thread_id) ON DELETE CASCADE,
    current_cp_id    TEXT REFERENCES checkpoints(checkpoint_id) ON DELETE SET NULL,
    lnode            TEXT,
    count            INT NOT NULL DEFAULT 0,
    scratch          TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. checkpoint ↔ message 快照映射（时间回溯准确性的关键）：
--    messages 表保存所有消息（跨分支共享），checkpoint_messages 记录
--    "某个 checkpoint 时刻"消息集合与顺序。回溯时按此表还原历史快照，
--    而不是读取整个 thread 的全部消息（那会把未来分支的消息混进来）。
CREATE TABLE IF NOT EXISTS checkpoint_messages (
    checkpoint_id  TEXT NOT NULL REFERENCES checkpoints(checkpoint_id) ON DELETE CASCADE,
    thread_id      TEXT NOT NULL,
    msg_id         TEXT NOT NULL,
    position       INT NOT NULL,
    PRIMARY KEY (checkpoint_id, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_cp_messages ON checkpoint_messages(checkpoint_id, position);

-- 自动维护 updated_at
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_threads_updated_at ON threads;
CREATE TRIGGER trg_threads_updated_at
BEFORE UPDATE ON threads
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
