// 授信尽调智能体工作流（对应 credit_agent_due_diligence.py 的升级版）
// 感知 → 规划 → 行动（工具调用+留痕）→ 反思（证据够了吗？）→ 代码计算 PD → 专项分析（并行）
// → 多空辩论（并行）→ 首席风险官裁决与报告 → 输出核验 → 人在回路（转人工）
import { config } from '../config.js';
import { findCompany } from '../tools/enterprise.js';
import { TOOLS } from '../tools/registry.js';
import { scorePd } from '../tools/scoring.js';
import { one } from '../db/pool.js';
import { RunRecorder } from './recorder.js';
import { detectInjection, quarantine, validatePlan, verifyNumbers } from './guardrails.js';
import { planner, reflect, analyst, debater, chiefRiskOfficer } from './roles.js';

const summarize = (step, r) => {
  if (step === '关联图谱') return { risk_flags: r.risk_flags, rings: r.suspicious_rings.length, guarantee_cycles: r.guarantee_cycles, fund_cycles: r.fund_cycles, hidden_controllers: r.hidden_controllers };
  if (step === '制度检索') return r.map((d) => ({ title: d.title, score: d.score }));
  if (step === '财务') return { ...r, history: undefined };
  if (step === '司法') return { ...r, records: `${r.records.length} 条` };
  return r;
};

export async function runDueDiligence({ company: companyRef, onEvent }) {
  const company = await findCompany(companyRef);
  if (!company) throw Object.assign(new Error(`未找到企业：${companyRef}`), { status: 404 });

  const goal = `评估 ${company.name} 的授信风险（申请额度 ${company.requested_limit} 万元）`;
  const rec = await new RunRecorder({ agent: 'due_diligence', target: company.name, companyId: company.id, goal, onEvent }).start();

  try {
    // ① 感知 + 护栏：外部文本视为数据，检测提示注入
    const injection = detectInjection(company.description);
    const safeProfile = quarantine(company.description);
    await rec.log('guardrail', '输入护栏：提示注入检测', { detected: injection.detected, patterns: injection.patterns, action: injection.detected ? '已隔离疑似指令片段，仅作为数据使用' : '通过' });

    // ② 规划 → 行动 → 反思 循环
    const evidence = {};
    const planHistory = [];
    let missing = [];
    for (let iteration = 1; iteration <= config.risk.maxAgentIterations; iteration += 1) {
      const p = await rec.timed('planner', `第 ${iteration} 轮规划`, () => planner({ goal, company, safeProfile, iteration, missing }),
        (r) => ({ steps: r.steps, rationale: r.rationale, mode: r.mode, fallback_reason: r.fallback_reason }));
      const v = validatePlan(iteration === 1 ? p.steps : [...Object.keys(evidence), ...p.steps]);
      await rec.log('guardrail', '规划校验：权限最小化', { accepted: v.steps, rejected: v.rejected, auto_added: v.added });
      planHistory.push({ iteration, steps: v.steps, rationale: p.rationale, mode: p.mode });

      for (const step of v.steps) {
        if (evidence[step] !== undefined) continue;
        evidence[step] = await rec.timed('tool', `调用工具「${step}」(${TOOLS[step].name})`,
          () => TOOLS[step].run({ company, query: `${company.industry} 授信 人工复核 ${step === '制度检索' ? '担保圈 团伙 失信' : ''}` }),
          (r) => summarize(step, r));
      }

      const g = evidence['关联图谱']?.risk_flags || {};
      const r = reflect({ evidence, signals: g });
      await rec.log('planner', `第 ${iteration} 轮反思：证据是否充分`, r);
      if (r.sufficient) break;
      missing = r.missing;
    }

    // ③ 代码计算 PD（不让大模型心算）
    const scoring = await rec.timed('calculator', '评分卡计算 PD / 分数 / 原因码', () => scorePd({
      financials: evidence['财务'], legal: evidence['司法'], credit: evidence['征信'],
    }), (r) => ({ pd: r.pd, score: r.score, risk_level: r.risk_level, reason_codes: r.reason_codes, rule_pd: r.rule_pd }));

    // ④ 专项分析师（并行）
    const dims = [['财务', evidence['财务']], ['司法', evidence['司法']], ['关联', evidence['关联图谱']]].filter(([, e]) => e);
    const analyses = await Promise.all(dims.map(([d, e]) => rec.timed('llm', `${d}分析师`, () => analyst({ dimension: d, evidence: summarize(d === '关联' ? '关联图谱' : d, e) }),
      (r) => ({ text: r.text, mode: r.mode }))));
    const analysisMap = Object.fromEntries(dims.map(([d], i) => [d, analyses[i].text]));

    // ⑤ 多空辩论（并行）
    const slimEvidence = Object.fromEntries(Object.entries(evidence).filter(([k]) => k !== '制度检索').map(([k, v]) => [k, summarize(k, v)]));
    const [pro, con] = await Promise.all([
      rec.timed('llm', '多空辩论：支持方', () => debater({ side: 'pro', evidence: slimEvidence, scoring }), (r) => ({ text: r.text, mode: r.mode })),
      rec.timed('llm', '多空辩论：质疑方', () => debater({ side: 'con', evidence: slimEvidence, scoring }), (r) => ({ text: r.text, mode: r.mode })),
    ]);

    // ⑥ 人在回路判定（规则由代码决定，不由大模型决定）
    const graphFlags = evidence['关联图谱']?.risk_flags || {};
    const humanReasons = [];
    if (scoring.pd > config.risk.humanReviewPd) humanReasons.push(`PD ${scoring.pd} 超过阈值 ${config.risk.humanReviewPd}`);
    if (evidence['司法']?.dishonest_executor) humanReasons.push('存在失信被执行记录');
    if (graphFlags.guarantee_circle) humanReasons.push('涉及循环担保圈');
    if (graphFlags.fund_loop) humanReasons.push('存在资金闭环');
    if (graphFlags.fraud_ring) humanReasons.push('关联账户存在团伙线索');
    if (injection.detected) humanReasons.push('外部资料存在提示注入');
    const needHuman = humanReasons.length > 0;

    // ⑦ 首席风险官裁决 + 报告（流式）
    rec.emit('report_started', {});
    const report = await rec.timed('llm', '首席风险官：裁决并撰写报告', () => chiefRiskOfficer({
      company, evidence: slimEvidence, scoring, debate: { pro: pro.text, con: con.text }, injection, needHuman, humanReasons,
      stream: (t) => rec.emit('report_token', { token: t }),
    }), (r) => ({ length: r.text.length, mode: r.mode, fallback_reason: r.fallback_reason }));

    // ⑧ 输出护栏：数字核验
    const check = verifyNumbers(report.text, { evidence: slimEvidence, scoring, humanReasons, company: { requested_limit: company.requested_limit } },
      [config.risk.humanReviewPd * 100, 70, 1.5, 0.05, 5, 100]);
    await rec.log('guardrail', '输出护栏：报告数字核验', check);
    if (!check.passed) humanReasons.push(`报告中有 ${check.unverified.length} 个数字无法在证据中核实`);
    const finalNeedHuman = humanReasons.length > 0;

    const result = {
      company: { id: company.id, name: company.name, industry: company.industry, region: company.region, requested_limit: company.requested_limit },
      pd: scoring.pd,
      score: scoring.score,
      risk_level: scoring.risk_level,
      scoring,
      evidence: Object.fromEntries(Object.entries(evidence).map(([k, v]) => [k, k === '财务' ? v : summarize(k, v)])),
      knowledge: evidence['制度检索'] || [],
      analyses: analysisMap,
      debate: { pro: pro.text, con: con.text },
      report: report.text,
      injection,
      number_check: check,
      need_human: finalNeedHuman,
      human_reasons: humanReasons,
      plan: planHistory,
      llm_mode: report.mode,
    };

    // ⑨ 人在回路：创建复核任务；高风险同步生成预警
    if (finalNeedHuman) {
      const task = await one(
        'INSERT INTO review_tasks (run_id, company_id, pd, reasons) VALUES ($1,$2,$3,$4) RETURNING id',
        [rec.id, company.id, scoring.pd, JSON.stringify(humanReasons)],
      );
      result.review_task_id = task.id;
      await rec.log('system', '转人工复核', { review_task_id: task.id, reasons: humanReasons });
    }
    if (scoring.pd >= 0.1 || evidence['司法']?.dishonest_executor) {
      await one(
        `INSERT INTO alerts (run_id, company_id, level, signal_type, title, detail) VALUES ($1,$2,'高','信用评分',$3,$4) RETURNING id`,
        [rec.id, company.id, `${company.name} 尽调 PD ${scoring.pd}，风险等级${scoring.risk_level}`, JSON.stringify({ reason_codes: scoring.reason_codes })],
      );
    }

    await rec.finish({
      status: finalNeedHuman ? 'pending_review' : 'completed',
      plan: planHistory, result, pd: scoring.pd, score: scoring.score, riskLevel: scoring.risk_level, needHuman: finalNeedHuman,
    });
    return { run_id: rec.id, ...result };
  } catch (e) {
    await rec.fail(e);
    throw e;
  }
}
