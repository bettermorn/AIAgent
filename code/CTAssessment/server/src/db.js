import pg from 'pg';
import { config } from './config.js';

export const pool = new pg.Pool(config.postgres);

export async function initDb() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS assessments (
      id SERIAL PRIMARY KEY,
      student_name TEXT NOT NULL,
      grade TEXT,
      programming_exp TEXT,
      languages JSONB DEFAULT '[]'::jsonb,
      charts_usage TEXT,
      answers JSONB DEFAULT '{}'::jsonb,
      self_scores JSONB DEFAULT '{}'::jsonb,
      self_levels JSONB DEFAULT '{}'::jsonb,
      test_scores JSONB DEFAULT '{}'::jsonb,
      dimension_scores JSONB DEFAULT '{}'::jsonb,
      task_detail JSONB DEFAULT '{}'::jsonb,
      total_score NUMERIC DEFAULT 0,
      percentage NUMERIC DEFAULT 0,
      level TEXT,
      conclusion TEXT,
      advice JSONB,
      created_at TIMESTAMPTZ DEFAULT now()
    );
  `);
  await pool.query(`
    CREATE TABLE IF NOT EXISTS search_cache (
      query TEXT PRIMARY KEY,
      results JSONB,
      created_at TIMESTAMPTZ DEFAULT now()
    );
  `);
  console.log('[db] 数据表已就绪');
}
