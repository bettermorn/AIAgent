import React from 'react';

export default function ReportView({ report, onBack }) {
  const scores = report.scores || {};
  const resources = report.learning_resources || [];

  return (
    <div className="report">
      <div className="report-header card">
        <div>
          <h2>技术领导力评测报告</h2>
          <p className="muted">
            被评价人：<strong>{report.evaluatee_name || '-'}</strong>
            {report.department && <>｜{report.department}</>}
            {report.position && <>｜{report.position}</>}
            {report.relationship && <>｜{report.relationship}评价</>}
            {report.period && <>｜{report.period}</>}
            ｜模型：{report.model || '-'}
          </p>
        </div>
        <button className="btn" onClick={onBack}>返回列表</button>
      </div>

      {/* 总分 + 等级 */}
      <div className="score-hero card">
        <div className="score-total">
          <div className="score-number">{scores.totalScore ?? '-'}</div>
          <div className="score-band">
            <span className="band-label">{scores.band?.label || '—'}</span>
            <span className="band-desc">{scores.band?.desc || ''}</span>
          </div>
        </div>
        <RadarChart dimensions={scores.dimensions || []} />
        <div className="score-legend">
          {(scores.dimensions || []).map((d) => (
            <div className="legend-item" key={d.key}>
              <span className="legend-name">{d.name}</span>
              <span className="legend-score">{d.score ?? 'N/A'}</span>
              <span className="legend-weight">权重 {Math.round(d.weight * 100)}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* 维度得分明细 */}
      <div className="dim-grid">
        {(scores.dimensions || []).map((d) => (
          <div className="card dim-card" key={d.key}>
            <div className="dim-card-head">
              <h3>{d.name}</h3>
              <span className="dim-score">{d.score ?? 'N/A'}</span>
            </div>
            <div className="dim-bar-row">
              <div className="dim-bar">
                <div className="dim-bar-fill" style={{ width: `${((d.score || 0) / 5) * 100}%` }} />
              </div>
            </div>
            {d.sections?.map((s) => (
              <div className="sub-score" key={s.key}>
                <span>{s.name}</span>
                <span className="sub-score-val">{s.score ?? 'N/A'}</span>
              </div>
            ))}
          </div>
        ))}
      </div>

      {/* AI 评价结论 */}
      <div className="card report-section">
        <h2>🤖 AI 评价结论</h2>
        <Markdown text={report.conclusion || '（暂无结论）'} />
      </div>

      {/* 学习建议 */}
      <div className="card report-section">
        <h2>📚 个性化学习建议</h2>
        <p className="muted">
          基于评测短板、技术领导力课程知识库（0-4 系列文件）与 CSDN 参考文章，结合 Bocha/SerpAPI 实时搜索的学习资源生成。
        </p>
        <Markdown text={report.learning_advice || '（暂无建议）'} />
      </div>

      {/* 学习资源 */}
      {resources.length > 0 && (
        <div className="card report-section">
          <h2>🔗 网络搜索学习资源</h2>
          <ul className="resource-list">
            {resources.map((r, i) => (
              <li key={i}>
                <a href={r.url} target="_blank" rel="noreferrer">{r.title || r.url}</a>
                <span className="resource-source">{r.source}{r.query ? ` · “${r.query}”` : ''}</span>
                {r.snippet && <p className="resource-snippet">{r.snippet}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// 简易 SVG 雷达图（4维度）
function RadarChart({ dimensions }) {
  const size = 260;
  const cx = size / 2;
  const cy = size / 2;
  const R = size / 2 - 40;
  const n = Math.max(dimensions.length, 3);
  const angle = (i) => (Math.PI * 2 * i) / n - Math.PI / 2;

  const point = (i, r) => [cx + r * Math.cos(angle(i)), cy + r * Math.sin(angle(i))];
  const rings = [1, 2, 3, 4, 5].map((v) =>
    dimensions.map((_, i) => point(i, (R * v) / 5).join(',')).join(' ')
  );
  const dataPoly = dimensions
    .map((d, i) => point(i, (R * (d.score || 0)) / 5).join(','))
    .join(' ');

  return (
    <svg width={size} height={size} className="radar">
      {rings.map((p, i) => (
        <polygon key={i} points={p} fill="none" stroke="#e2e8f0" strokeWidth="1" />
      ))}
      {dimensions.map((_, i) => {
        const [x, y] = point(i, R);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#e2e8f0" strokeWidth="1" />;
      })}
      <polygon points={dataPoly} fill="rgba(22,163,74,0.25)" stroke="#16a34a" strokeWidth="2" />
      {dimensions.map((d, i) => {
        const [x, y] = point(i, R + 22);
        return (
          <text key={d.key} x={x} y={y} textAnchor="middle" dominantBaseline="middle" className="radar-label">
            {shortName(d.name)}
          </text>
        );
      })}
    </svg>
  );
}

function shortName(name) {
  return name.length > 8 ? name.slice(0, 7) + '…' : name;
}

// 轻量 Markdown 渲染（标题/加粗/列表/引用/链接/分隔线）
function Markdown({ text }) {
  const blocks = (text || '').split(/\n{2,}/);
  return (
    <div className="markdown">
      {blocks.map((block, i) => {
        const lines = block.split('\n');
        if (lines.every((l) => /^\s*(-|\d+\.|\*)\s+/.test(l))) {
          const ordered = /^\s*\d+\./.test(lines[0]);
          const items = lines.map((l) => l.replace(/^\s*(-|\d+\.|\*)\s+/, ''));
          const Tag = ordered ? 'ol' : 'ul';
          return <Tag key={i}>{items.map((it, j) => <li key={j} dangerouslySetInnerHTML={{ __html: inline(it) }} />)}</Tag>;
        }
        return lines.map((line, j) => {
          const key = `${i}-${j}`;
          if (/^###\s/.test(line)) return <h4 key={key} dangerouslySetInnerHTML={{ __html: inline(line.slice(4)) }} />;
          if (/^##\s/.test(line)) return <h3 key={key} dangerouslySetInnerHTML={{ __html: inline(line.slice(3)) }} />;
          if (/^#\s/.test(line)) return <h2 key={key} dangerouslySetInnerHTML={{ __html: inline(line.slice(2)) }} />;
          if (/^>\s?/.test(line)) return <blockquote key={key} dangerouslySetInnerHTML={{ __html: inline(line.replace(/^>\s?/, '')) }} />;
          if (/^(-{3,}|_{3,})$/.test(line.trim())) return <hr key={key} />;
          if (!line.trim()) return null;
          return <p key={key} dangerouslySetInnerHTML={{ __html: inline(line) }} />;
        });
      })}
    </div>
  );
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function inline(s) {
  return escapeHtml(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\[(.+?)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}
