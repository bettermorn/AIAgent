import { query } from './pool.js';

export async function upsertReport(report) {
  const { rows } = await query(
    `INSERT INTO reports (report_date, title, overview, highlights, trends, by_channel, article_count, run_id)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
     ON CONFLICT (report_date) DO UPDATE SET
       title = EXCLUDED.title,
       overview = EXCLUDED.overview,
       highlights = EXCLUDED.highlights,
       trends = EXCLUDED.trends,
       by_channel = EXCLUDED.by_channel,
       article_count = EXCLUDED.article_count,
       run_id = EXCLUDED.run_id,
       updated_at = now()
     RETURNING *`,
    [
      report.reportDate,
      report.title,
      report.overview || '',
      JSON.stringify(report.highlights || []),
      JSON.stringify(report.trends || []),
      JSON.stringify(report.byChannel || {}),
      report.articleCount || 0,
      report.runId || null,
    ],
  );
  return rows[0];
}

export async function getReport(date) {
  const { rows } = await query('SELECT * FROM reports WHERE report_date = $1', [date]);
  return rows[0] || null;
}

export async function getLatestReport() {
  const { rows } = await query('SELECT * FROM reports ORDER BY report_date DESC LIMIT 1');
  return rows[0] || null;
}

export async function listReports(limit = 30) {
  const { rows } = await query(
    `SELECT report_date, title, article_count, overview, created_at, updated_at
     FROM reports ORDER BY report_date DESC LIMIT $1`,
    [limit],
  );
  return rows;
}

/* ---------------------------- 采集任务 runs ---------------------------- */

export async function createRun(run) {
  await query(
    `INSERT INTO runs (id, status, channels, keywords) VALUES ($1,$2,$3,$4)`,
    [run.id, 'running', run.channels || [], run.keywords || []],
  );
}

export async function finishRun(id, { status, collectedCount, insertedCount, error }) {
  await query(
    `UPDATE runs SET status = $2, finished_at = now(), collected_count = $3, inserted_count = $4, error = $5
     WHERE id = $1`,
    [id, status, collectedCount || 0, insertedCount || 0, error || null],
  );
}

export async function listRuns(limit = 20) {
  const { rows } = await query(
    `SELECT * FROM runs ORDER BY started_at DESC LIMIT $1`,
    [limit],
  );
  return rows;
}
