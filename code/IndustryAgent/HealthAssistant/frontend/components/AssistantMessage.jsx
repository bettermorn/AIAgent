import { useState } from "react";

const TRIAGE_INFO = {
  green: { label: "低风险", cls: "triage-green" },
  yellow: { label: "中风险", cls: "triage-yellow" },
  red: { label: "高风险 · 建议就医", cls: "triage-red" },
};

function TriageBadge({ level }) {
  const info = TRIAGE_INFO[level] || { label: level, cls: "triage-grey" };
  return <span className={`triage-badge ${info.cls}`}>{info.label}</span>;
}

function Citations({ citations }) {
  const [open, setOpen] = useState(false);
  if (!citations?.length) return null;

  return (
    <div className="citations">
      <button className="cite-toggle" onClick={() => setOpen(!open)}>
        📚 引用来源（{citations.length} 条）{open ? "▲" : "▼"}
      </button>
      {open && (
        <div className="cite-list">
          {citations.map((c, i) => (
            <div className="cite-card" key={`${c.doc_id}-${i}`}>
              <div className="cite-head">
                <span className="cite-idx">[{i + 1}]</span>
                <span className="cite-title">{c.title}</span>
                <span className="cite-score">{(c.score * 100).toFixed(0)}%</span>
              </div>
              <p className="cite-chunk">{c.chunk}</p>
              <span className="cite-source">来源：{c.source}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AssistantMessage({ data, error }) {
  if (error) {
    return (
      <div className="msg assistant">
        <div className="msg-body error-box">
          <strong>⚠️ 请求出错</strong>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const policy = data?.policy;
  const blocked = policy?.blocked;

  return (
    <div className="msg assistant">
      <div className="msg-head">
        <span className="avatar">🩺</span>
        <span className="assistant-name">健康助手</span>
        {policy && <TriageBadge level={policy.triage_level} />}
        {blocked && <span className="blocked-tag">已触发安全拦截</span>}
      </div>
      <div className={`msg-body ${blocked ? "blocked" : ""}`}>
        <p className="answer-text">{data.answer}</p>
        {data.disclaimer && <p className="disclaimer">⚠️ {data.disclaimer}</p>}
      </div>
      <Citations citations={data.citations} />
    </div>
  );
}
