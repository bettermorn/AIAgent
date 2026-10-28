import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pool, ensureDatabase } from './pool.js';
import { seedDefaultSettings } from './settingsRepo.js';
import { config } from '../config.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

async function main() {
  await ensureDatabase();
  const sql = fs.readFileSync(path.join(__dirname, 'schema.sql'), 'utf8');
  console.log('[migrate] 正在初始化数据库 ...');
  await pool.query(sql);
  // 兼容已存在的旧表
  await pool.query('ALTER TABLE articles ADD COLUMN IF NOT EXISTS relevant BOOLEAN NOT NULL DEFAULT true');
  await seedDefaultSettings();
  console.log('[migrate] 完成，数据库:', config.db.database);
  await pool.end();
}

main().catch(async (err) => {
  console.error('[migrate] 失败:', err.message);
  console.error('  请确认 PostgreSQL 已启动，且 config.env 中 PG* 配置正确（必要时手动执行 createdb ' + config.db.database + '）');
  await pool.end().catch(() => {});
  process.exit(1);
});
