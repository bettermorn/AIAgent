import express from 'express';
import cors from 'cors';
import { config } from './config.js';
import { initDb, pool } from './db.js';
import { router as assessmentsRouter } from './routes/assessments.js';

const app = express();
app.use(cors());
app.use(express.json({ limit: '2mb' }));

app.get('/api/health', (req, res) => res.json({ status: 'ok' }));
app.use('/api/assessments', assessmentsRouter);

async function start() {
  try {
    await initDb();
  } catch (e) {
    console.error('[db] 初始化失败（请检查 PostgreSQL 配置）:', e.message);
    process.exit(1);
  }
  app.listen(config.port, () => {
    console.log(`[server] 计算思维测试智能体后端已启动: http://localhost:${config.port}`);
    console.log(`[server] DeepSeek 模型: ${config.deepseek.model}`);
  });
}

process.on('SIGINT', async () => {
  await pool.end();
  process.exit(0);
});

start();
