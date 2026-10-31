// 运行记录与审计留痕：每一步写入 audit_logs，同时通过回调实时推送给前端（SSE）
import { one, query } from '../db/pool.js';
import { deepseek } from '../llm/deepseek.js';

const sanitize = (obj) => JSON.parse(JSON.stringify(obj ?? null, (k, v) => (typeof v === 'bigint' ? Number(v) : v)));

export class RunRecorder {
  constructor({ agent, target, companyId, goal, onEvent }) {
    Object.assign(this, { agent, target, companyId, goal });
    this.onEvent = onEvent || (() => {});
    this.seq = 0;
    this.id = null;
  }

  async start() {
    const row = await one(
      `INSERT INTO agent_runs (agent, target, company_id, goal, llm_model, llm_mode)
       VALUES ($1,$2,$3,$4,$5,$6) RETURNING id, started_at`,
      [this.agent, this.target, this.companyId || null, this.goal, deepseek.model, deepseek.mode],
    );
    this.id = row.id;
    this.emit('run_started', { run_id: this.id, agent: this.agent, target: this.target, llm_mode: deepseek.mode, llm_model: deepseek.model });
    return this;
  }

  emit(type, data) {
    try { this.onEvent({ type, ...data }); } catch { /* 客户端断开时忽略 */ }
  }

  /** 记录一步：actor 为执行者（planner/tool/calculator/llm/guardrail/human/system） */
  async log(actor, step, detail, latencyMs) {
    this.seq += 1;
    const payload = sanitize(detail);
    await query(
      'INSERT INTO audit_logs (run_id, seq, actor, step, detail, latency_ms) VALUES ($1,$2,$3,$4,$5,$6)',
      [this.id, this.seq, actor, step, JSON.stringify(payload), latencyMs ?? null],
    );
    this.emit('step', { seq: this.seq, actor, step, detail: payload, latency_ms: latencyMs ?? null, at: new Date().toISOString() });
  }

  /** 计时执行并留痕 */
  async timed(actor, step, fn, summarize = (r) => r) {
    const t0 = Date.now();
    this.emit('step_started', { actor, step });
    try {
      const r = await fn();
      await this.log(actor, step, summarize(r), Date.now() - t0);
      return r;
    } catch (e) {
      await this.log(actor, `${step}（失败）`, { error: e.message }, Date.now() - t0);
      throw e;
    }
  }

  async finish({ status = 'completed', plan, result, pd, score, riskLevel, needHuman }) {
    await query(
      `UPDATE agent_runs SET status=$2, plan=$3, result=$4, pd=$5, score=$6, risk_level=$7, need_human=$8, finished_at=now()
       WHERE id=$1`,
      [this.id, status, JSON.stringify(sanitize(plan)), JSON.stringify(sanitize(result)), pd ?? null, score ?? null, riskLevel ?? null, needHuman ?? null],
    );
    this.emit('run_finished', { run_id: this.id, status, result: sanitize(result) });
  }

  async fail(error) {
    await query("UPDATE agent_runs SET status='failed', error=$2, finished_at=now() WHERE id=$1", [this.id, error.message]);
    this.emit('run_failed', { run_id: this.id, error: error.message });
  }
}
