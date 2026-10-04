import React, { useMemo, useState } from 'react';

export default function QuestionnaireForm({ questionnaire, onSubmit }) {
  const steps = useMemo(
    () => [
      { key: 'basic', title: '基本信息' },
      ...questionnaire.dimensions.map((d) => ({ key: d.key, title: d.name, dimension: d })),
      { key: 'overall', title: '综合评价' }
    ],
    [questionnaire]
  );

  const [step, setStep] = useState(0);
  const [basicInfo, setBasicInfo] = useState({
    evaluateeName: '', department: '', position: '',
    evaluatorName: '', relationship: '', workDuration: '', period: ''
  });
  const [answers, setAnswers] = useState({});           // {questionId: 1-5 | 'N/A'}
  const [openAnswers, setOpenAnswers] = useState({});   // {dimKey: [string]}
  const [overall, setOverall] = useState({
    ratings: {}, topStrengths: ['', '', ''], topImprovements: ['', '', ''],
    keyCase: '', developmentAreas: [], advice: ''
  });

  const current = steps[step];
  const answeredCount = Object.values(answers).filter((v) => v !== undefined).length;
  const totalQ = questionnaire.totalQuestions;

  const setAnswer = (id, value) => {
    setAnswers((prev) => (value === null ? (() => { const n = { ...prev }; delete n[id]; return n; })() : { ...prev, [id]: value }));
  };

  const setOpenAnswer = (dimKey, index, value) => {
    setOpenAnswers((prev) => {
      const arr = [...(prev[dimKey] || [])];
      arr[index] = value;
      return { ...prev, [dimKey]: arr };
    });
  };

  const toggleArea = (area) => {
    setOverall((prev) => ({
      ...prev,
      developmentAreas: prev.developmentAreas.includes(area)
        ? prev.developmentAreas.filter((a) => a !== area)
        : [...prev.developmentAreas, area]
    }));
  };

  const handleSubmit = () => {
    onSubmit({
      basicInfo,
      answers,
      openAnswers,
      overall: {
        ...overall,
        topStrengths: overall.topStrengths.filter(Boolean),
        topImprovements: overall.topImprovements.filter(Boolean)
      }
    });
  };

  return (
    <div className="form-wrap">
      {/* 步骤条 */}
      <div className="stepper card">
        {steps.map((s, i) => (
          <button
            key={s.key}
            className={`step ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`}
            onClick={() => i <= step && setStep(i)}
          >
            <span className="step-num">{i < step ? '✓' : i + 1}</span>
            <span className="step-title">{s.title}</span>
          </button>
        ))}
        <div className="progress-info">
          已答 <strong>{answeredCount}</strong>/{totalQ} 题
        </div>
      </div>

      {/* 基本信息 */}
      {current.key === 'basic' && (
        <section className="card">
          <h2>基本信息</h2>
          <div className="grid-2">
            <Field label="被评价人姓名 *">
              <input value={basicInfo.evaluateeName} onChange={(e) => setBasicInfo({ ...basicInfo, evaluateeName: e.target.value })} placeholder="如：张三" />
            </Field>
            <Field label="所在部门/团队">
              <input value={basicInfo.department} onChange={(e) => setBasicInfo({ ...basicInfo, department: e.target.value })} placeholder="如：平台技术部" />
            </Field>
            <Field label="当前职位/职级">
              <input value={basicInfo.position} onChange={(e) => setBasicInfo({ ...basicInfo, position: e.target.value })} placeholder="如：技术专家 T4" />
            </Field>
            <Field label="评价人姓名">
              <input value={basicInfo.evaluatorName} onChange={(e) => setBasicInfo({ ...basicInfo, evaluatorName: e.target.value })} placeholder="如：李四" />
            </Field>
            <Field label="评价人与被评价人的关系 *">
              <select value={basicInfo.relationship} onChange={(e) => setBasicInfo({ ...basicInfo, relationship: e.target.value })}>
                <option value="">请选择</option>
                {questionnaire.relationships.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
            <Field label="共事时间">
              <select value={basicInfo.workDuration} onChange={(e) => setBasicInfo({ ...basicInfo, workDuration: e.target.value })}>
                <option value="">请选择</option>
                {questionnaire.workDurations.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
            <Field label="评价周期">
              <input value={basicInfo.period} onChange={(e) => setBasicInfo({ ...basicInfo, period: e.target.value })} placeholder="如：2025 年度 / 2025H2" />
            </Field>
          </div>

          <div className="scale-guide">
            <h3>评分标准</h3>
            <table>
              <tbody>
                {questionnaire.scaleGuide.map((g) => (
                  <tr key={g.value}>
                    <td className="scale-val">{g.value}</td>
                    <td>{g.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted">建议评价者在选择 4 分或 5 分时补充具体事实、数据或案例。本问卷评价的是被评价人过去 12 个月内的实际表现。</p>
          </div>
        </section>
      )}

      {/* 维度问卷 */}
      {current.dimension && (
        <DimensionSection
          dimension={current.dimension}
          answers={answers}
          setAnswer={setAnswer}
          openAnswers={openAnswers[current.dimension.key] || []}
          setOpenAnswer={(i, v) => setOpenAnswer(current.dimension.key, i, v)}
        />
      )}

      {/* 综合评价 */}
      {current.key === 'overall' && (
        <section className="card">
          <h2>综合评价</h2>
          <h3>1. 综合评分</h3>
          <p className="muted">请对被评价人在各维度的整体表现进行评分。</p>
          <div className="rating-table">
            {questionnaire.overallRatingItems.map((item) => (
              <div className="rating-row" key={item.key}>
                <div className="rating-label">{item.label}</div>
                <ScoreOptions
                  value={overall.ratings[item.key]}
                  onChange={(v) => setOverall((p) => ({ ...p, ratings: { ...p.ratings, [item.key]: v } }))}
                />
              </div>
            ))}
          </div>

          <h3>2. 最突出的三项能力</h3>
          {[0, 1, 2].map((i) => (
            <input key={i} className="inline-input" placeholder={`第 ${i + 1} 项`} value={overall.topStrengths[i]}
              onChange={(e) => setOverall((p) => { const a = [...p.topStrengths]; a[i] = e.target.value; return { ...p, topStrengths: a }; })} />
          ))}

          <h3>3. 最需要改进的三项能力</h3>
          {[0, 1, 2].map((i) => (
            <input key={i} className="inline-input" placeholder={`第 ${i + 1} 项`} value={overall.topImprovements[i]}
              onChange={(e) => setOverall((p) => { const a = [...p.topImprovements]; a[i] = e.target.value; return { ...p, topImprovements: a }; })} />
          ))}

          <h3>4. 关键事实与案例</h3>
          <p className="muted">请描述一个最能体现其技术领导力的案例（建议涵盖：{questionnaire.casePrompts.join('；')}）。</p>
          <textarea rows={5} value={overall.keyCase} onChange={(e) => setOverall((p) => ({ ...p, keyCase: e.target.value }))} />

          <h3>5. 下一阶段发展建议</h3>
          <p className="muted">建议被评价人在未来 6 至 12 个月重点提升：</p>
          <div className="checkbox-grid">
            {questionnaire.developmentAreas.map((a) => (
              <label key={a} className={`checkbox ${overall.developmentAreas.includes(a) ? 'checked' : ''}`}>
                <input type="checkbox" checked={overall.developmentAreas.includes(a)} onChange={() => toggleArea(a)} />
                {a}
              </label>
            ))}
          </div>
          <Field label="具体发展建议">
            <textarea rows={4} value={overall.advice} onChange={(e) => setOverall((p) => ({ ...p, advice: e.target.value }))} placeholder="可留空，智能体会结合 AI 分析自动生成学习建议" />
          </Field>
        </section>
      )}

      {/* 底部导航 */}
      <div className="form-nav">
        <button className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>上一步</button>
        <div className="form-nav-right">
          {step < steps.length - 1 ? (
            <button className="btn primary" onClick={() => setStep(step + 1)} disabled={current.key === 'basic' && (!basicInfo.evaluateeName || !basicInfo.relationship)}>
              下一步：{steps[step + 1]?.title}
            </button>
          ) : (
            <button className="btn primary lg" onClick={handleSubmit}>提交评测，生成报告</button>
          )}
        </div>
      </div>
    </div>
  );
}

function DimensionSection({ dimension, answers, setAnswer, openAnswers, setOpenAnswer }) {
  return (
    <section>
      <div className="card dim-header">
        <h2>{dimension.name}</h2>
        <p className="muted">维度权重：{Math.round(dimension.weight * 100)}% · 共 {dimension.sections.reduce((s, x) => s + x.questions.length, 0)} 道评分题</p>
      </div>
      {dimension.sections.map((sec) => (
        <div className="card section" key={sec.key}>
          <h3>{sec.name}</h3>
          {sec.description && <p className="muted">{sec.description}</p>}
          <div className="questions">
            {sec.questions.map((q) => (
              <div className="question-row" key={q.id}>
                <div className="question-text">
                  <span className="qnum">{q.id}</span> {q.text}
                </div>
                <ScoreOptions value={answers[q.id]} onChange={(v) => setAnswer(q.id, v)} />
              </div>
            ))}
          </div>
        </div>
      ))}
      <div className="card section">
        <h3>开放题（选填，但会显著提升报告质量）</h3>
        {dimension.openQuestions.map((oq, i) => (
          <Field key={i} label={oq}>
            <textarea rows={2} value={openAnswers[i] || ''} onChange={(e) => setOpenAnswer(i, e.target.value)} />
          </Field>
        ))}
      </div>
    </section>
  );
}

function ScoreOptions({ value, onChange }) {
  return (
    <div className="score-options">
      {[1, 2, 3, 4, 5, 'N/A'].map((v) => (
        <button
          key={String(v)}
          className={`score-btn ${value === v ? 'selected' : ''} ${v === 'N/A' ? 'na' : ''}`}
          onClick={() => onChange(value === v ? null : v)}
          title={v === 'N/A' ? '不适用或缺乏足够信息判断' : `${v} 分`}
        >
          {v}
        </button>
      ))}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}
