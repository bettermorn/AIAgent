import cron from 'node-cron';
import { config } from '../config.js';
import { getSettings } from '../db/settingsRepo.js';
import { runPipeline } from './pipeline.js';

let task = null;
let currentCron = null;

export async function startScheduler() {
  const settings = await getSettings();
  const expression = settings.cron || config.schedule.cron;
  const timezone = settings.timezone || config.schedule.timezone;
  schedule(expression, timezone);

  if (config.schedule.runOnBoot) {
    console.log('[scheduler] RUN_ON_BOOT=true，启动时执行一次采集');
    runPipeline({ trigger: 'boot' }).catch((err) => console.error('[scheduler] 启动采集失败:', err.message));
  }
}

function schedule(expression, timezone) {
  if (task && currentCron === expression) return;
  if (task) {
    task.stop();
    task = null;
  }
  if (!cron.validate(expression)) {
    console.warn(`[scheduler] 非法 cron 表达式 "${expression}"，使用默认 ${config.schedule.cron}`);
    expression = config.schedule.cron;
  }
  task = cron.schedule(
    expression,
    async () => {
      console.log(`[scheduler] 触发定时采集 (${expression})`);
      try {
        await runPipeline({ trigger: 'schedule' });
      } catch (err) {
        console.error('[scheduler] 定时采集失败:', err.message);
      }
    },
    { timezone },
  );
  currentCron = expression;
  console.log(`[scheduler] 已注册定时任务: "${expression}" (${timezone})`);
}

/** 配置变更后热更新调度表达式 */
export async function reloadScheduler() {
  const settings = await getSettings();
  schedule(settings.cron || config.schedule.cron, settings.timezone || config.schedule.timezone);
}

export function nextRunInfo() {
  return { cron: currentCron || config.schedule.cron };
}
