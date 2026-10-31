// 风险预警智能体（对应课件“重银晓警”）：多源信号并行（图计算 / 异常检测 / 评分模型）→ 智能体汇总研判 → 预警触发 → 处置留痕
import { many, one } from '../db/pool.js';
import { analyzeGraph } from '../tools/graph.js';
import { detectAnomalies } from '../tools/anomaly.js';
import { getFinancials, getLegalRisk, getCreditBureau } from '../tools/enterprise.js';
import { scorePd } from '../tools/scoring.js';
import { RunRecorder } from './recorder.js';
import { warningAnalyst } from './roles.js';

/** 预警等级由确定性规则计算 */
export function warningLevel({ graph, anomaly, scoring, legal }) {
  let points = 0;
  const reasons = [];
  if (graph.risk_flags.fraud_ring) { points += 2; reasons.push('设备/电话共用团伙'); }
  if (graph.risk_flags.guarantee_circle) { points += 2; reasons.push('循环担保圈'); }
  if (graph.risk_flags.fund_loop) { points += 2; reasons.push('资金闭环'); }
  if (graph.risk_flags.fund_collector) { points += 1; reasons.push('资金汇集账户'); }
  if (anomaly.anomaly_count >= 2) { points += 2; reasons.push(`${anomaly.anomaly_count} 笔异常交易`); } else if (anomaly.anomaly_count === 1) { points += 1; reasons.push('1 笔异常交易'); }
  if (scoring.pd >= 0.1) { points += 2; reasons.push(`PD ${scoring.pd}`); } else if (scoring.pd >= 0.05) { points += 1; reasons.push(`PD ${scoring.pd}`); }
  if (legal.dishonest_executor) { points += 2; reasons.push('失信被执行'); }
  const level = points >= 4 ? '高' : points >= 2 ? '中' : points >= 1 ? '低' : '无';
  return { level, points, reasons };
}

const signalType = (s) => {
  if (s.graph.risk_flags.fraud_ring || s.graph.risk_flags.guarantee_circle || s.graph.risk_flags.fund_loop) return '图关联';
  if (s.anomaly.anomaly_count) return '异常交易';
  return '信用评分';
};

export async function runEarlyWarning({ companyIds, onEvent } = {}) {
  const companies = companyIds?.length
    ? await many('SELECT * FROM companies WHERE id = ANY($1) ORDER BY id', [companyIds])
    : await many('SELECT * FROM companies ORDER BY id');
  const rec = await new RunRecorder({
    agent: 'early_warning', target: companies.length === 1 ? companies[0].name : `批量扫描 ${companies.length} 家企业`,
    companyId: companies.length === 1 ? companies[0].id : null, goal: '多源信号融合的风险预警扫描', onEvent,
  }).start();

  try {
    const results = [];
    for (const c of companies) {
      // 三路信号并行（Fan-out）
      const [graph, anomaly, scoring, legal] = await rec.timed('tool', `${c.name}：图计算 / 异常检测 / 评分 三路并行`, async () => {
        const [fin, lg, credit] = await Promise.all([getFinancials(c.id), getLegalRisk(c.id), getCreditBureau(c.id)]);
        const [g, a, s] = await Promise.all([analyzeGraph(c.id), detectAnomalies(c.id), scorePd({ financials: fin, legal: lg, credit })]);
        return [g, a, s, lg];
      }, ([g, a, s]) => ({ graph_flags: g.risk_flags, anomaly_count: a.anomaly_count, max_score: a.max_score, pd: s.pd }));

      const lv = warningLevel({ graph, anomaly, scoring, legal });
      await rec.log('calculator', `${c.name}：预警等级计算`, lv);
      const item = { company: { id: c.id, name: c.name, industry: c.industry }, ...lv, pd: scoring.pd, score: scoring.score };

      if (lv.level === '高' || lv.level === '中') {
        const signals = {
          level: lv.level,
          graph: { risk_flags: graph.risk_flags, suspicious_rings: graph.suspicious_rings, guarantee_cycles: graph.guarantee_cycles, fund_cycles: graph.fund_cycles, hidden_controllers: graph.hidden_controllers, fund_collectors: graph.fund_collectors },
          anomaly: { anomaly_count: anomaly.anomaly_count, threshold: anomaly.threshold, max_score: anomaly.max_score, rule_hit_count: anomaly.rule_hit_count, top: anomaly.items.slice(0, 3).map((i) => ({ account: i.account, amount: i.amount, txn_hour: i.txn_hour, anomaly_score: i.anomaly_score, rule_hits: i.rule_hits })) },
          scoring: { pd: scoring.pd, score: scoring.score, reason_codes: scoring.reason_codes },
          legal: { lawsuits_12m: legal.lawsuits_12m, dishonest_executor: legal.dishonest_executor },
        };
        const analysis = await rec.timed('llm', `${c.name}：智能体汇总研判`, () => warningAnalyst({ company: c, signals }), (r) => ({ mode: r.mode, length: r.text.length }));
        // 去重：同一企业同类未关闭预警不重复生成
        const type = signalType(signals);
        const exists = await one("SELECT id FROM alerts WHERE company_id=$1 AND signal_type=$2 AND status <> '已关闭' AND level=$3", [c.id, type, lv.level]);
        let alertId = exists?.id;
        if (!exists) {
          const a = await one(
            `INSERT INTO alerts (run_id, company_id, level, signal_type, title, detail) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id`,
            [rec.id, c.id, lv.level, type, `${c.name}：${lv.reasons.join('、')}`, JSON.stringify({ signals, analysis: analysis.text })],
          );
          alertId = a.id;
          await rec.log('system', `${c.name}：触发${lv.level}等级预警`, { alert_id: alertId, signal_type: type });
        } else {
          await rec.log('system', `${c.name}：已有未关闭预警，跳过重复触发`, { alert_id: alertId });
        }
        Object.assign(item, { alert_id: alertId, analysis: analysis.text, signal_type: type });
      }
      results.push(item);
    }
    const summary = {
      scanned: results.length,
      high: results.filter((r) => r.level === '高').length,
      medium: results.filter((r) => r.level === '中').length,
      items: results,
    };
    await rec.finish({ status: 'completed', result: summary });
    return { run_id: rec.id, ...summary };
  } catch (e) {
    await rec.fail(e);
    throw e;
  }
}
