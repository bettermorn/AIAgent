import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ACTOR_NAMES } from '../api.js';

export function PageHeader({ title, desc, children }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        {desc && <p className="muted">{desc}</p>}
      </div>
      <div className="header-actions">{children}</div>
    </div>
  );
}

export function Card({ title, extra, children, className = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || extra) && (
        <div className="card-head">
          <h3>{title}</h3>
          {extra}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, tone = '' }) {
  return (
    <div className={`stat ${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

const LEVEL_TONE = { 高: 'red', 中高: 'orange', 中: 'yellow', 低: 'green', 无: 'gray' };
export function LevelTag({ level }) {
  if (!level) return <span className="tag gray">未评估</span>;
  return <span className={`tag ${LEVEL_TONE[level] || 'gray'}`}>{level}</span>;
}

const STATUS_TONE = {
  completed: 'green', running: 'blue', failed: 'red', pending_review: 'orange',
  待处置: 'red', 处置中: 'orange', 已关闭: 'green', 待复核: 'orange', 同意: 'green', 否决: 'red', 补充材料: 'blue',
};
const STATUS_TEXT = { completed: '已完成', running: '运行中', failed: '失败', pending_review: '待人工复核' };
export function StatusTag({ status }) {
  return <span className={`tag ${STATUS_TONE[status] || 'gray'}`}>{STATUS_TEXT[status] || status}</span>;
}

export function Markdown({ children }) {
  return <div className="markdown"><ReactMarkdown remarkPlugins={[remarkGfm]}>{children || ''}</ReactMarkdown></div>;
}

export function Empty({ text = '暂无数据' }) {
  return <div className="empty">{text}</div>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <div className="error-box">{error}</div>;
}

export function Spinner({ text }) {
  return <span className="spinner-wrap"><span className="spinner" />{text}</span>;
}

/** 智能体执行轨迹（审计时间线） */
export function Timeline({ steps, running }) {
  if (!steps.length && !running) return <Empty text="尚未运行" />;
  return (
    <ol className="timeline">
      {steps.map((s, i) => (
        <li key={`${s.seq}-${i}`} className={`tl-item actor-${s.actor}`}>
          <div className="tl-dot" />
          <div className="tl-content">
            <div className="tl-head">
              <span className={`actor actor-${s.actor}`}>{ACTOR_NAMES[s.actor] || s.actor}</span>
              <span className="tl-step">{s.step}</span>
              {s.latency_ms !== null && s.latency_ms !== undefined && <span className="tl-latency">{s.latency_ms} ms</span>}
            </div>
            {s.detail && <StepDetail detail={s.detail} />}
          </div>
        </li>
      ))}
      {running && (
        <li className="tl-item running">
          <div className="tl-dot pulse" />
          <div className="tl-content"><Spinner text={running} /></div>
        </li>
      )}
    </ol>
  );
}

function StepDetail({ detail }) {
  if (detail.text) return <div className="tl-text"><Markdown>{detail.text}</Markdown></div>;
  return (
    <details className="tl-detail">
      <summary>查看输入/输出</summary>
      <pre>{JSON.stringify(detail, null, 2)}</pre>
    </details>
  );
}
