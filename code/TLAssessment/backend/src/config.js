import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// config.env 位于项目根目录（backend 的上一级）
dotenv.config({ path: path.resolve(__dirname, '../../config.env') });

export const config = {
  port: Number(process.env.PORT || 3001),
  // DeepSeek
  deepseekApiKey: process.env.DEEPSEEK_API_KEY || '',
  deepseekBaseUrl: (process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com').replace(/\/$/, ''),
  deepseekModel: process.env.DEEPSEEK_MODEL || 'deepseek-chat',
  // 搜索
  serpapiKey: process.env.SERPAPI_API_KEY || '',
  bochaApiKey: process.env.BOCHA_API_KEY || '',
  // PostgreSQL
  pg: {
    host: process.env.POSTGRES_HOST || 'localhost',
    port: Number(process.env.POSTGRES_PORT || 5432),
    database: process.env.POSTGRES_DB || 'tl_assessment',
    user: process.env.POSTGRES_USER || 'postgres',
    password: process.env.POSTGRES_PASSWORD || ''
  }
};
