import dotenv from 'dotenv';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// 优先加载项目根目录的 config.env，其次加载 server/.env
dotenv.config({ path: path.resolve(__dirname, '../../config.env') });
dotenv.config({ path: path.resolve(__dirname, '../.env') });

export const config = {
  port: Number(process.env.PORT || 3001),
  deepseek: {
    apiKey: process.env.DEEPSEEK_API_KEY,
    baseUrl: process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com',
    model: process.env.DEEPSEEK_MODEL || 'deepseek-chat',
  },
  search: {
    serpapiKey: process.env.SERPAPI_API_KEY,
    bochaApiKey: process.env.BOCHA_API_KEY,
  },
  postgres: {
    host: process.env.POSTGRES_HOST || 'localhost',
    port: Number(process.env.POSTGRES_PORT || 5432),
    database: process.env.POSTGRES_DB || 'ct_assessment',
    user: process.env.POSTGRES_USER || 'postgres',
    password: process.env.POSTGRES_PASSWORD || '',
  },
};
