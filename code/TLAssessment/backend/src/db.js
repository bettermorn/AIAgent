import pg from 'pg';
import { config } from './config.js';

export const pool = new pg.Pool({
  host: config.pg.host,
  port: config.pg.port,
  database: config.pg.database,
  user: config.pg.user,
  password: config.pg.password,
  max: 10,
  idleTimeoutMillis: 30000
});

const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS assessments (
  id SERIAL PRIMARY KEY,
  evaluatee_name TEXT NOT NULL DEFAULT '',
  department TEXT NOT NULL DEFAULT '',
  position TEXT NOT NULL DEFAULT '',
  evaluator_name TEXT NOT NULL DEFAULT '',
  relationship TEXT NOT NULL DEFAULT '',
  work_duration TEXT NOT NULL DEFAULT '',
  period TEXT NOT NULL DEFAULT '',
  answers JSONB NOT NULL,
  open_answers JSONB NOT NULL DEFAULT '{}',
  overall JSONB NOT NULL DEFAULT '{}',
  scores JSONB NOT NULL,
  conclusion TEXT,
  learning_advice TEXT,
  learning_resources JSONB NOT NULL DEFAULT '[]',
  model TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'processing',  -- processing | completed | failed
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assessments_created_at ON assessments (created_at DESC);
`;

export async function initDb() {
  const client = await pool.connect();
  try {
    await client.query(SCHEMA_SQL);
    console.log(`[db] 已连接 PostgreSQL 并初始化表结构（${config.pg.database}@${config.pg.host}:${config.pg.port}）`);
  } finally {
    client.release();
  }
}

export async function query(text, params) {
  const res = await pool.query(text, params);
  return res;
}
