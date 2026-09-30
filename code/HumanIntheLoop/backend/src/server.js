'use strict';

const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');

const { config, validate } = require('./config');
const { init: initDb } = require('./db/init');
const store = require('./db/store');
const { Agent } = require('./agent');

const app = express();

app.use(cors());
app.use(express.json({ limit: '2mb' }));

const agent = new Agent();

/* ============================================================
 * REST API
 * ============================================================ */

app.get('/api/health', async (_req, res) => {
  res.json({
    ok: true,
    deepseek_configured: !!(config.deepseekApiKey && config.deepseekApiKey !== 'your-deepseek-api-key-here'),
    tavily_configured: !!config.tavilyApiKey,
    postgres: `${config.postgres.host}:${config.postgres.port}/${config.postgres.database}`,
    model: config.deepseekModel,
  });
});

// --- Thread ---

app.post('/api/threads', async (req, res) => {
  try {
    const title = req.body?.title || '新会话';
    const id = await store.createThread(title);
    res.json({ thread_id: id });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/threads', async (_req, res) => {
  try {
    const rows = await store.listThreads();
    res.json({ threads: rows });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/threads/:threadId', async (req, res) => {
  try {
    // 先确认线程确实存在（即便还没有任何 checkpoint）
    const thread = await store.getThread(req.params.threadId);
    if (!thread) return res.status(404).json({ error: 'thread 不存在' });

    const state = await store.getCurrentState(req.params.threadId);
    // 即便 state 为空（线程刚创建、首条消息还没产生 checkpoint），
    // 也返回空 messages，而不是 404，避免前端在创建后立即拉取时出现 race condition。
    res.json({
      thread,
      state: state || {
        thread_id: req.params.threadId,
        checkpoint_id: null,
        lnode: null,
        count: 0,
        scratch: null,
        messages: [],
      },
    });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.delete('/api/threads/:threadId', async (req, res) => {
  try {
    const existed = await store.deleteThread(req.params.threadId);
    if (!existed) return res.status(404).json({ error: 'thread 不存在' });
    res.json({ ok: true });
  } catch (e) {
    console.error('[delete-thread]', e);
    res.status(500).json({ error: e.message });
  }
});

app.patch('/api/threads/:threadId', async (req, res) => {
  try {
    const { title } = req.body || {};
    if (typeof title === 'string' && title.trim()) {
      await store.renameThread(req.params.threadId, title.trim());
    }
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// --- Agent ---

app.post('/api/threads/:threadId/invoke', async (req, res) => {
  try {
    const { messages = [] } = req.body || {};
    const result = await agent.invoke(req.params.threadId, messages);
    res.json(result);
  } catch (e) {
    console.error('[invoke]', e);
    res.status(500).json({ error: e.message });
  }
});

/* ============================================================
 * Human-in-the-Loop 三大分支：
 *   approve  → /api/threads/:id/approve        同意执行工具
 *   reject   → /api/threads/:id/reject         拒绝执行
 *   modify   → /api/threads/:id/modify         修改参数后执行
 * 兼容旧路由 /continue 和 /modify（行为完全等价）
 * ============================================================ */

app.post('/api/threads/:threadId/approve', async (req, res) => {
  try {
    const { note = '' } = req.body || {};
    const result = await agent.approve(req.params.threadId, note);
    res.json(result);
  } catch (e) {
    console.error('[approve]', e);
    res.status(500).json({ error: e.message });
  }
});

// 旧版兼容：continue ≡ approve
app.post('/api/threads/:threadId/continue', async (req, res) => {
  try {
    const result = await agent.approve(req.params.threadId);
    res.json(result);
  } catch (e) {
    console.error('[continue]', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/threads/:threadId/reject', async (req, res) => {
  try {
    const { reason = '' } = req.body || {};
    const result = await agent.reject(req.params.threadId, reason);
    res.json(result);
  } catch (e) {
    console.error('[reject]', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/threads/:threadId/modify', async (req, res) => {
  try {
    const { modifications = [], note = '' } = req.body || {};
    const result = await agent.modifyAndApprove(req.params.threadId, modifications, note);
    res.json(result);
  } catch (e) {
    console.error('[modify]', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/threads/:threadId/replay', async (req, res) => {
  try {
    const { checkpoint_id } = req.body || {};
    if (!checkpoint_id) return res.status(400).json({ error: 'checkpoint_id 必填' });
    const result = await agent.replayFrom(req.params.threadId, checkpoint_id);
    res.json(result);
  } catch (e) {
    console.error('[replay]', e);
    res.status(500).json({ error: e.message });
  }
});

// --- Checkpoints ---

app.get('/api/threads/:threadId/checkpoints', async (req, res) => {
  try {
    const rows = await store.listCheckpoints(req.params.threadId);
    res.json({ checkpoints: rows });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/checkpoints/:checkpointId', async (req, res) => {
  try {
    const cp = await store.getCheckpoint(req.params.checkpointId);
    if (!cp) return res.status(404).json({ error: 'checkpoint 不存在' });
    res.json({ checkpoint: cp });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

/* ============================================================
 * 启动
 * ============================================================ */

async function main() {
  validate();
  console.log('[server] 正在初始化 PostgreSQL...');
  try {
    await initDb();
  } catch (e) {
    console.error('[server] 数据库初始化失败:', e.message);
    console.error('[server] 请确认 PostgreSQL 已启动，并检查 config.env 中的连接信息。');
    process.exit(1);
  }

  // 可选：托管前端构建产物
  const frontendDist = path.resolve(__dirname, '..', '..', 'frontend', 'build');
  if (fs.existsSync(frontendDist)) {
    app.use(express.static(frontendDist));
    app.get(/^(?!\/api).*/, (_req, res) => {
      res.sendFile(path.join(frontendDist, 'index.html'));
    });
    console.log('[server] 已托管前端静态文件:', frontendDist);
  }

  app.listen(config.port, () => {
    console.log('============================================');
    console.log('  Human in the Loop 后端已启动');
    console.log(`  端口       : ${config.port}`);
    console.log(`  数据库     : ${config.postgres.host}:${config.postgres.port}/${config.postgres.database}`);
    console.log(`  DeepSeek   : ${config.deepseekBaseUrl}  model=${config.deepseekModel}`);
    console.log(`  代理       : ${config.httpsProxy || '(直连，无代理)'}`);
    console.log(`  健康检查   : http://localhost:${config.port}/api/health`);
    console.log('============================================');
  });
}

main();
