import express from 'express';
import cors from 'cors';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { config } from './config.js';
import { apiRouter } from './routes/api.js';
import { startScheduler } from './services/scheduler.js';
import { healthCheck, ensureDatabase } from './db/pool.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();

app.use(cors());
app.use(express.json({ limit: '1mb' }));
app.use('/api', apiRouter);

// 生产模式下托管前端构建产物
const webDist = path.resolve(__dirname, '..', '..', 'web', 'dist');
if (fs.existsSync(webDist)) {
  app.use(express.static(webDist));
  app.get('*', (req, res, next) => {
    if (req.path.startsWith('/api')) return next();
    res.sendFile(path.join(webDist, 'index.html'));
  });
}

app.use((err, req, res, next) => {
  console.error('[api] 异常:', err);
  res.status(500).json({ error: err.message || '服务器内部错误' });
});

const port = config.port;
const server = app.listen(port, async () => {
  console.log(`[server] 后端已启动 http://localhost:${port}`);
  console.log(`[server] DeepSeek: ${config.deepseek.apiKey ? '已配置' : '未配置（将使用规则摘要）'}`);
  try {
    await ensureDatabase();
    await healthCheck();
    console.log('[server] PostgreSQL 连接正常');
    await startScheduler();
  } catch (err) {
    console.error('[server] PostgreSQL 连接失败:', err.message);
    if (!config.db.autoCreate) {
      console.error('  当前已关闭自动建库（PG_AUTO_CREATE=false）');
    }
    console.error('  请确认 PostgreSQL 已启动，且 config.env 中 PG* 配置正确');
  }
});

const shutdown = async () => {
  console.log('\n[server] 正在退出 ...');
  server.close();
  process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
