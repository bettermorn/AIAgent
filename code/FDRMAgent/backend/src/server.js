import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import express from 'express';
import cors from 'cors';
import { config } from './config.js';
import routes from './api/routes.js';
import { deepseek } from './llm/deepseek.js';
import { pool } from './db/pool.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();

app.use(cors());
app.use(express.json({ limit: '1mb' }));
app.use((req, _res, next) => {
  if (req.path.startsWith('/api')) console.log(`[api] ${req.method} ${req.path}`);
  next();
});

app.use('/api', routes);

// 生产模式：托管前端构建产物
const dist = path.resolve(__dirname, '../../frontend/dist');
if (fs.existsSync(dist)) {
  app.use(express.static(dist));
  app.get(/^\/(?!api).*/, (_req, res) => res.sendFile(path.join(dist, 'index.html')));
}

app.use((err, _req, res, _next) => {
  const status = err.status || 500;
  if (status >= 500) console.error('[api] error:', err);
  res.status(status).json({ error: err.message || '服务器内部错误' });
});

const server = app.listen(config.port, () => {
  console.log(`[server] 金融智能风险管理智能体后端已启动：http://localhost:${config.port}`);
  console.log(`[server] 大模型：${deepseek.mode === 'deepseek' ? `DeepSeek (${deepseek.model})` : 'MockLLM（未配置 DEEPSEEK_API_KEY）'}`);
  console.log(`[server] 数据库：postgresql://${config.pg.user}@${config.pg.host}:${config.pg.port}/${config.pg.database}`);
});

const shutdown = () => {
  server.close(() => pool.end().finally(() => process.exit(0)));
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
