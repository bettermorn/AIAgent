import { query } from './pool.js';

/**
 * 批量写入文章，按 url 去重（已存在则刷新采集时间）
 */
export async function upsertArticles(articles) {
  if (!articles.length) return { inserted: 0, updated: 0, newIds: [] };
  let inserted = 0;
  let updated = 0;
  const newIds = [];
  for (const a of articles) {
    const res = await query(
      `INSERT INTO articles
         (url, title, source, channel, language, snippet, summary, category, tags, score,
          published_at, keyword, run_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       ON CONFLICT (url) DO UPDATE SET
         title = EXCLUDED.title,
         snippet = COALESCE(articles.snippet, EXCLUDED.snippet),
         collected_at = now()
       RETURNING id, (xmax = 0) AS inserted`,
      [
        a.url,
        a.title,
        a.source || null,
        a.channel,
        a.language || 'zh',
        a.snippet || null,
        a.summary || null,
        a.category || null,
        a.tags || [],
        a.score ?? null,
        a.publishedAt || null,
        a.keyword || null,
        a.runId || null,
      ],
    );
    const row = res.rows[0];
    if (row?.inserted) {
      inserted += 1;
      newIds.push(Number(row.id));
    } else {
      updated += 1;
    }
  }
  return { inserted, updated, newIds };
}

export async function updateArticleAnalysis(id, { summary, category, tags, score, relevant }) {
  await query(
    `UPDATE articles SET summary = $2, category = $3, tags = $4, score = $5, relevant = $6 WHERE id = $1`,
    [id, summary, category, tags || [], score ?? null, relevant !== false],
  );
}

export async function listArticles({
  limit = 50,
  offset = 0,
  channel,
  keyword,
  days,
  q,
  onlySummarized,
  includeIrrelevant = false,
} = {}) {
  const where = [];
  if (!includeIrrelevant) where.push('relevant = true');
  const params = [];
  const p = (val) => {
    params.push(val);
    return `$${params.length}`;
  };

  if (channel) where.push(`channel = ${p(channel)}`);
  if (keyword) where.push(`keyword ILIKE ${p(`%${keyword}%`)}`);
  if (typeof days === 'number' && days > 0) {
    where.push(
      `COALESCE(published_at, collected_at) >= now() - (${p(String(days))} || ' days')::interval`,
    );
  }
  if (q) {
    const like = `%${q}%`;
    where.push(
      `(title ILIKE ${p(like)} OR COALESCE(summary, snippet, '') ILIKE ${p(like)})`,
    );
  }
  if (onlySummarized) where.push('summary IS NOT NULL');

  const whereSql = where.join(' AND ');
  const { rows } = await query(
    `SELECT id, url, title, source, channel, language, snippet, summary, category, tags, score,
            published_at, collected_at, keyword
     FROM articles
     ${whereSql ? `WHERE ${whereSql}` : ''}
     ORDER BY COALESCE(published_at, collected_at) DESC
     LIMIT ${p(limit)} OFFSET ${p(offset)}`,
    params,
  );
  const countRes = await query(
    `SELECT COUNT(*)::int AS total FROM articles ${whereSql ? `WHERE ${whereSql}` : ''}`,
    params.slice(0, params.length - 2),
  );
  return { items: rows, total: countRes.rows[0]?.total || 0 };
}

export async function getArticlesByIds(ids) {
  if (!ids.length) return [];
  const { rows } = await query(
    `SELECT id, url, title, source, channel, snippet, summary, category, tags, score, published_at, relevant
     FROM articles WHERE id = ANY($1::bigint[])`,
    [ids],
  );
  return rows;
}

export async function getRecentArticlesForReport(hours = 24) {
  const { rows } = await query(
    `SELECT id, url, title, source, channel, language, snippet, summary, category, tags, score,
            published_at, collected_at, keyword
     FROM articles
     WHERE collected_at >= now() - ($1 || ' hours')::interval AND relevant = true
     ORDER BY score DESC NULLS LAST, collected_at DESC`,
    [String(hours)],
  );
  return rows;
}

/** 当天（按指定时区）采集到的全部相关条目 */
export async function getArticlesCollectedToday(tz = 'Asia/Shanghai') {
  const { rows } = await query(
    `SELECT id, url, title, source, channel, language, snippet, summary, category, tags, score,
            published_at, collected_at, keyword, relevant
     FROM articles
     WHERE collected_at >= (((now() AT TIME ZONE $1)::date)::timestamp AT TIME ZONE $1)
       AND relevant = true
     ORDER BY score DESC NULLS LAST, collected_at DESC`,
    [tz],
  );
  return rows;
}

export async function statsByChannel(days = 7) {
  const { rows } = await query(
    `SELECT channel, COUNT(*)::int AS count
     FROM articles
     WHERE collected_at >= now() - ($1 || ' days')::interval AND relevant = true
     GROUP BY channel ORDER BY count DESC`,
    [String(days)],
  );
  return rows;
}
