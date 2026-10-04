import express from 'express';
import cors from 'cors';
import { config } from './config.js';
import { initDb } from './db.js';
import { router as apiRouter } from './routes/assessments.js';

const app = express();
app.use(cors());
app.use(express.json({ limit: '2mb' }));

// 健康检查
app.get('/api/health', (_req, res) => {
  res.json({
    status: 'ok',
    model: config.deepseekModel,
    searchProviders: {
      bocha: Boolean(config.bochaApiKey),
      serpapi: Boolean(config.serpapiKey)
    },
    time: new Date().toISOString()
  });
});

app.use('/api', apiRouter);

// 错误处理
app.use((err, _req, res, _next) => {
  console.error('[server] 未捕获错误:', err);
  res.status(500).json({ error: err.message || '服务器内部错误' });
});

async function main() {
  // 数据库初始化失败不阻塞启动（便于先联调前端）
  try {
    await initDb();
  } catch (err) {
    console.warn(`[db] 初始化失败，接口将在访问时报错: ${err.message}`);
    console.warn('[db] 请确认 PostgreSQL 已启动、数据库已创建（见 README）。');
  }

  if (!config.deepseekApiKey) console.warn('[config] 未配置 DEEPSEEK_API_KEY，报告将使用降级方案');
  if (!config.serpapiKey && !config.bochaApiKey) console.warn('[config] 未配置搜索 Key，将跳过网络资源搜索');

  app.listen(config.port, () => {
    console.log(`技术领导力评测智能体后端已启动: http://localhost:${config.port}`);
    console.log(`模型: ${config.deepseekModel} @ ${config.deepseekBaseUrl}`);
  });
}

main();
