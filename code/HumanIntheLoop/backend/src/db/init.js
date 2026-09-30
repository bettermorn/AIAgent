'use strict';

/**
 * 初始化 PostgreSQL 数据库与表结构。
 * 可通过 `npm run db:init` 单独执行。
 */

const fs = require('fs');
const path = require('path');
const { pool, ensureDatabase, query, closePool } = require('./pool');
const { config } = require('../config');

async function init() {
  console.log('[db-init] 正在检查数据库...');
  await ensureDatabase();

  const sql = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf-8');
  console.log('[db-init] 正在创建/更新表结构...');
  await query(sql);

  console.log('[db-init] 完成。当前配置:');
  console.log(`  host     = ${config.postgres.host}`);
  console.log(`  port     = ${config.postgres.port}`);
  console.log(`  database = ${config.postgres.database}`);
  console.log(`  user     = ${config.postgres.user}`);
}

if (require.main === module) {
  init()
    .then(() => closePool())
    .then(() => process.exit(0))
    .catch((err) => {
      console.error('[db-init] 失败:', err.message);
      console.error('');
      console.error('💡 排查建议：');
      console.error('  1) 确认 PostgreSQL 已启动:');
      console.error('       macOS (brew):  brew services start postgresql@16');
      console.error('       macOS (app):   打开 Postgres.app 即可');
      console.error('       Docker:        docker run --name pg -d -p 5432:5432 \\');
      console.error('                          -e POSTGRES_PASSWORD=postgres postgres:16');
      console.error('  2) 查看本地 PostgreSQL 用户列表:');
      console.error('       psql -h localhost -p 5432 -U postgres -l');
      console.error('     如果提示 role 不存在，请改用你的 macOS 用户名，或先执行：');
      console.error('       createuser -s postgres   # 以管理员身份创建一个 postgres 超级用户');
      console.error('  3) 编辑根目录 config.env，把 POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_HOST');
      console.error('     改为你本机的真实值后再次启动。');
      closePool().finally(() => process.exit(1));
    });
}

module.exports = { init };
