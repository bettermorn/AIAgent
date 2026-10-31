import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '../..');

// 读取顺序：进程环境变量 > backend/.env（本地覆盖，可选） > 项目根目录 config.env
// dotenv 默认不覆盖已存在的变量，因此先加载的优先级更高
for (const file of [path.join(ROOT, 'backend', '.env'), path.join(ROOT, 'config.env')]) {
  if (fs.existsSync(file)) dotenv.config({ path: file, quiet: true });
}

const num = (v, d) => (v === undefined || v === '' || Number.isNaN(Number(v)) ? d : Number(v));

export const config = {
  port: num(process.env.PORT, 8080),
  deepseek: {
    apiKey: process.env.DEEPSEEK_API_KEY || '',
    baseUrl: process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com',
    model: process.env.DEEPSEEK_MODEL || 'deepseek-chat',
    timeoutMs: num(process.env.DEEPSEEK_TIMEOUT_MS, 60000),
    temperature: num(process.env.DEEPSEEK_TEMPERATURE, 0.2),
  },
  pg: {
    host: process.env.PGHOST || 'localhost',
    port: num(process.env.PGPORT, 5432),
    user: process.env.PGUSER || 'postgres',
    password: process.env.PGPASSWORD || undefined,
    // 优先 FDIRM_PGDATABASE，其次 PGDATABASE，默认 fdirm_agent
    database: process.env.FDIRM_PGDATABASE || process.env.PGDATABASE || 'fdirm_agent',
  },
  risk: {
    // PD 超过该阈值必须转人工（与课件 HUMAN_REVIEW_PD = 0.05 一致，示意阈值）
    humanReviewPd: num(process.env.HUMAN_REVIEW_PD, 0.05),
    // 评分卡刻度：基准分 600 对应好坏比 20:1，PDO = 50
    baseScore: 600,
    baseOdds: 20,
    pdo: 50,
    maxAgentIterations: 2,
  },
};

export const llmEnabled = () => Boolean(config.deepseek.apiKey);
