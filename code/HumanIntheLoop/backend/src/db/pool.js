'use strict';

const { Pool, Client } = require('pg');
const { config } = require('../config');

let pool = null;

function getPool() {
  if (!pool) {
    pool = new Pool({
      host: config.postgres.host,
      port: config.postgres.port,
      user: config.postgres.user,
      password: config.postgres.password,
      database: config.postgres.database,
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
    });

    pool.on('error', (err) => {
      console.error('[pg] 意外的 PostgreSQL 客户端错误:', err);
    });
  }
  return pool;
}

async function query(text, params) {
  return getPool().query(text, params);
}

async function getClient() {
  return getPool().connect();
}

/**
 * 确保目标数据库存在。如果不存在则先连接到默认 postgres 数据库创建。
 */
async function ensureDatabase() {
  const adminClient = new Client({
    host: config.postgres.host,
    port: config.postgres.port,
    user: config.postgres.user,
    password: config.postgres.password,
    database: 'postgres',
  });

  try {
    await adminClient.connect();
    const result = await adminClient.query(
      'SELECT 1 FROM pg_database WHERE datname = $1',
      [config.postgres.database]
    );
    if (result.rowCount === 0) {
      const safeName = config.postgres.database.replace(/"/g, '""');
      await adminClient.query(`CREATE DATABASE "${safeName}"`);
      console.log(`[pg] 已创建数据库: ${config.postgres.database}`);
    } else {
      console.log(`[pg] 数据库已存在: ${config.postgres.database}`);
    }
  } finally {
    await adminClient.end();
  }
}

async function closePool() {
  if (pool) {
    await pool.end();
    pool = null;
  }
}

module.exports = {
  getPool,
  query,
  getClient,
  ensureDatabase,
  closePool,
};
