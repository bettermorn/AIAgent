import React from 'react';

const GRADES = ['高一', '高二', '高三'];
const EXPERIENCES = ['没有', '学习过少量编程', '学习过一门编程课程', '经常使用编程解决问题'];
const LANGUAGES = ['Scratch', 'Python', 'C/C++', 'Java', '其他', '没有接触过'];
const CHARTS = ['从不', '很少', '有时', '经常', '总是'];

function OptionGroup({ label, options, value, onChange, multi = false }) {
  return (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <div className="options">
        {options.map((opt) => {
          const selected = multi ? value.includes(opt) : value === opt;
          return (
            <button
              key={opt}
              type="button"
              className={`option ${selected ? 'selected' : ''}`}
              onClick={() => {
                if (multi) {
                  onChange(selected ? value.filter((v) => v !== opt) : [...value, opt]);
                } else {
                  onChange(opt);
                }
              }}
            >
              {opt}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function BasicInfoStep({ studentName, setStudentName, basicInfo, setBasicInfo, onNext }) {
  const valid = studentName.trim() && basicInfo.grade && basicInfo.programmingExp && basicInfo.chartsUsage;

  return (
    <div className="panel">
      <h2 className="panel-title">第一部分 · 基本信息</h2>
      <p className="panel-desc">本部分没有对错，请根据真实情况作答。</p>

      <div className="form-group">
        <label className="form-label">姓名 / 昵称</label>
        <input
          className="input"
          placeholder="请输入你的姓名或昵称"
          value={studentName}
          onChange={(e) => setStudentName(e.target.value)}
        />
      </div>

      <OptionGroup label="1. 年级" options={GRADES} value={basicInfo.grade} onChange={(v) => setBasicInfo({ ...basicInfo, grade: v })} />
      <OptionGroup label="2. 是否学习过编程" options={EXPERIENCES} value={basicInfo.programmingExp} onChange={(v) => setBasicInfo({ ...basicInfo, programmingExp: v })} />
      <OptionGroup label="3. 接触过的编程语言（可多选）" options={LANGUAGES} value={basicInfo.languages} multi onChange={(v) => setBasicInfo({ ...basicInfo, languages: v })} />
      <OptionGroup label="4. 平时是否喜欢用表格、图示、流程图或思维导图整理问题？" options={CHARTS} value={basicInfo.chartsUsage} onChange={(v) => setBasicInfo({ ...basicInfo, chartsUsage: v })} />

      <div className="step-actions">
        <span />
        <button className="btn-primary" disabled={!valid} onClick={onNext}>下一步：自评量表 →</button>
      </div>
    </div>
  );
}
