'use strict';

const path = require('path');
const dotenv = require('dotenv');

// 优先加载根目录的 config.env
const envPath = path.resolve(__dirname, '..', '..', 'config.env');
const result = dotenv.config({ path: envPath });

if (result.error) {
  // 兼容：也尝试加载 backend/.env
  dotenv.config();
}

function getEnv(key, defaultValue) {
  const value = process.env[key];
  if (value === undefined || value === '') {
    return defaultValue;
  }
  return value;
}

const config = {
  deepseekApiKey: getEnv('DEEPSEEK_API_KEY', ''),
  deepseekBaseUrl: getEnv(
    'DEEPSEEK_BASE_URL',
    'https://api.deepseek.com/v1'
  ),
  deepseekModel: getEnv('DEEPSEEK_MODEL', 'deepseek-chat'),
  tavilyApiKey: getEnv('TAVILY_API_KEY', ''),
  // 代理：dotenv.config() 已经把 HTTPS_PROXY 写进 process.env，
  // 此处额外保留一份只读副本以便日志/调试使用。
  httpsProxy: getEnv('HTTPS_PROXY', getEnv('HTTP_PROXY', '')),
  port: parseInt(getEnv('PORT', '3001'), 10),
  frontendPort: parseInt(getEnv('FRONTEND_PORT', '3000'), 10),
  apiBase: getEnv('REACT_APP_API_BASE', 'http://localhost:3001/api'),
  postgres: {
    host: getEnv('POSTGRES_HOST', 'localhost'),
    port: parseInt(getEnv('POSTGRES_PORT', '5432'), 10),
    user: getEnv('POSTGRES_USER', 'postgres'),
    password: getEnv('POSTGRES_PASSWORD', 'postgres'),
    database: getEnv('POSTGRES_DB', 'human_in_the_loop'),
  },
  envFilePath: envPath,
};

function validate() {
  if (!config.deepseekApiKey || config.deepseekApiKey === 'your-deepseek-api-key-here') {
    console.warn(
      `\n[警告] DEEPSEEK_API_KEY 未配置或仍为占位符。\n请在 ${config.envFilePath} 中填入你的 DeepSeek API Key 后重启服务。\n`
    );
    return false;
  }
  return true;
}

module.exports = { config, validate };
