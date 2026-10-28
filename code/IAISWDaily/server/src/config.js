import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const ROOT_DIR = path.resolve(__dirname, '..', '..');

// 优先加载仓库根目录的 config.env（API_KEY 存放位置），再加载 server/.env 作为覆盖项
const configEnvPath = path.join(ROOT_DIR, 'config.env');
if (fs.existsSync(configEnvPath)) {
  dotenv.config({ path: configEnvPath, override: false });
}
dotenv.config({ path: path.join(ROOT_DIR, 'server', '.env'), override: false });

const toBool = (v, def = false) => {
  if (v === undefined || v === null || v === '') return def;
  return ['1', 'true', 'yes', 'on'].includes(String(v).toLowerCase());
};
const toInt = (v, def) => {
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : def;
};

export const config = {
  port: toInt(process.env.PORT, 8787),
  // PostgreSQL
  db: {
    host: process.env.PGHOST || 'localhost',
    port: toInt(process.env.PGPORT, 5432),
    user: process.env.PGUSER || 'postgres',
    password: process.env.PGPASSWORD || '',
    database: process.env.PGDATABASE || 'iaisw_daily',
    ssl: toBool(process.env.PGSSL, false) ? { rejectUnauthorized: false } : false,
    max: toInt(process.env.PGPOOL_MAX, 10),
    // 启动时目标库不存在则自动创建（需要该用户具备 CREATEDB 权限）
    autoCreate: toBool(process.env.PG_AUTO_CREATE, true),
    // 用于检查/创建目标库的维护库，默认 postgres
    maintenanceDatabase: process.env.PG_MAINTENANCE_DB || 'postgres',
  },
  // DeepSeek（搜索内容的总结 / 分析模型 + Search / Fetch 工具接口）
  deepseek: {
    apiKey: process.env.DEEPSEEK_API_KEY || '',
    baseUrl: process.env.DEEPSEEK_BASE_URL || 'https://api.deepseek.com',
    model: process.env.DEEPSEEK_MODEL || 'deepseek-chat',
    temperature: Number(process.env.DEEPSEEK_TEMPERATURE || 0.3),
    // Search 工具：POST /v1/tools/search
    search: {
      enabled: toBool(process.env.DEEPSEEK_SEARCH_ENABLED, true),
      // off=不使用；fallback=其它源无结果时兜底；primary=优先使用；supplement=与其它源并行合并
      mode: ['off', 'fallback', 'primary', 'supplement'].includes(
        String(process.env.DEEPSEEK_SEARCH_MODE || '').toLowerCase(),
      )
        ? String(process.env.DEEPSEEK_SEARCH_MODE).toLowerCase()
        : 'supplement',
      needContent: toBool(process.env.DEEPSEEK_SEARCH_NEED_CONTENT, false),
      // 在 query 中追加 after: 日期，限定发布时间窗口
      useAfter: toBool(process.env.DEEPSEEK_SEARCH_AFTER, true),
      timeout: toInt(process.env.DEEPSEEK_SEARCH_TIMEOUT, 25000),
      retries: toInt(process.env.DEEPSEEK_SEARCH_RETRIES, 2),
    },
    // Fetch 工具：POST /v1/tools/fetch（补充正文，供总结使用）
    fetch: {
      enabled: toBool(process.env.DEEPSEEK_FETCH_ENABLED, true),
      limit: toInt(process.env.DEEPSEEK_FETCH_LIMIT, 12),
      minSnippet: toInt(process.env.DEEPSEEK_FETCH_MIN_SNIPPET, 200),
      concurrency: toInt(process.env.DEEPSEEK_FETCH_CONCURRENCY, 3),
      timeout: toInt(process.env.DEEPSEEK_FETCH_TIMEOUT, 20000),
      retries: toInt(process.env.DEEPSEEK_FETCH_RETRIES, 1),
    },
  },
  // 搜索引擎
  search: {
    serpapiKey: process.env.SERPAPI_API_KEY || '',
    bochaKey: process.env.BOCHA_API_KEY || '',
    // 无可用 Key 时返回演示数据，保证系统可跑通
    mock: toBool(process.env.SEARCH_MOCK, false),
  },
  // 定时任务
  schedule: {
    cron: process.env.DAILY_CRON || '0 8 * * *',
    timezone: process.env.CRON_TIMEZONE || 'Asia/Shanghai',
    runOnBoot: toBool(process.env.RUN_ON_BOOT, false),
  },
  // 采集窗口（天）
  collect: {
    windowDays: toInt(process.env.COLLECT_WINDOW_DAYS, 3),
    perKeywordLimit: toInt(process.env.COLLECT_PER_KEYWORD_LIMIT, 8),
  },
};

export const defaultKeywords = {
  zh: [
    '工业智能',
    '工业人工智能',
    '工业软件',
    '工业互联网',
    '智能制造',
    '数字孪生',
    '工业大模型',
    'CAD CAE PLM MES',
  ],
  en: [
    'industrial AI',
    'industrial software',
    'smart manufacturing',
    'digital twin manufacturing',
    'industrial internet of things platform',
  ],
};

export default config;
