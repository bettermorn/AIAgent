import { runPipeline } from '../services/pipeline.js';
import { pool, ensureDatabase } from '../db/pool.js';

async function main() {
  await ensureDatabase();
  console.log('[cli] 手动执行一次采集任务');
  const result = await runPipeline({ trigger: 'cli' });
  if (result?.skipped) {
    console.log('[cli] 跳过:', result.reason);
  } else {
    console.log(
      `[cli] 完成：检索 ${result.collected} 条 / 新增 ${result.inserted} 条 / 总结 ${result.summarized} 条`,
    );
    console.log(`[cli] 日报：${result.report?.title}`);
  }
  await pool.end();
  process.exit(0);
}

main().catch(async (err) => {
  console.error('[cli] 失败:', err.message);
  await pool.end().catch(() => {});
  process.exit(1);
});
