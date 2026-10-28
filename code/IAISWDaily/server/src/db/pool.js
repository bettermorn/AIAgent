import pg from 'pg';
import { config } from '../config.js';

const { Pool, Client } = pg;

/**
 * 启动时确保目标数据库存在：不存在则创建，已存在则直接跳过。
 * 连接维护库（postgres / template1）检查 pg_database，再按需 CREATE DATABASE。
 * @returns {Promise<boolean>} 是否新建了数据库
 */
let dbEnsured = false;

const quoteIdent = (name) => `"${String(name).replace(/"/g, '""')}"`;

async function connectMaintenance() {
  const candidates = [...new Set([config.db.maintenanceDatabase || 'postgres', 'template1'])];
  let lastErr;
  for (const database of candidates) {
    const client = new Client({
      host: config.db.host,
      port: config.db.port,
      user: config.db.user,
      password: config.db.password,
      database,
      ssl: config.db.ssl,
      connectionTimeoutMillis: 10000,
    });
    try {
      await client.connect();
      return client;
    } catch (err) {
      lastErr = err;
      await client.end().catch(() => {});
    }
  }
  throw new Error(`无法连接 PostgreSQL 维护库（${candidates.join(' / ')}）：${lastErr?.message}`);
}

export async function ensureDatabase({ force = false } = {}) {
  if (dbEnsured && !force) return false;
  if (!config.db.autoCreate) {
    dbEnsured = true;
    return false;
  }

  const client = await connectMaintenance();
  try {
    const { rows } = await client.query('SELECT 1 FROM pg_database WHERE datname = $1::text', [
      config.db.database,
    ]);
    if (rows.length) {
      console.log(`[db] 数据库已存在，跳过创建：${config.db.database}`);
      dbEnsured = true;
      return false;
    }
    await client.query(`CREATE DATABASE ${quoteIdent(config.db.database)}`);
    console.log(`[db] 数据库不存在，已自动创建：${config.db.database}`);
    dbEnsured = true;
    return true;
  } catch (err) {
    // 42P04：并发下已被其它进程创建，视为已存在
    if (err.code === '42P04') {
      dbEnsured = true;
      return false;
    }
    if (err.code === '42501') {
      throw new Error(`当前用户无建库权限（需 CREATEDB）：${config.db.user}，请手动执行 createdb ${config.db.database}`);
    }
    throw err;
  } finally {
    await client.end().catch(() => {});
  }
}

export const pool = new Pool({
  host: config.db.host,
  port: config.db.port,
  user: config.db.user,
  password: config.db.password,
  database: config.db.database,
  ssl: config.db.ssl,
  max: config.db.max,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 10000,
});

pool.on('error', (err) => {
  console.error('[pg] 连接池异常:', err.message);
});

export async function query(text, params) {
  const start = Date.now();
  const res = await pool.query(text, params);
  const ms = Date.now() - start;
  if (ms > 500) console.warn(`[pg] 慢查询 ${ms}ms: ${text.slice(0, 80)}`);
  return res;
}

export async function healthCheck() {
  const { rows } = await pool.query('SELECT 1 AS ok');
  return rows[0]?.ok === 1;
}

export default pool;
