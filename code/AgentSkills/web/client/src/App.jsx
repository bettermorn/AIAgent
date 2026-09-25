import { useState } from 'react';

const SUGGESTIONS = ['新的智能家居助手', '人工智能在教育中的应用', '新能源汽车行业分析', '敏捷开发实践分享'];

export default function App() {
  const [topic, setTopic] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [keyConfigured, setKeyConfigured] = useState(null);

  async function checkHealth() {
    try {
      const res = await fetch('/api/health');
      const data = await res.json();
      setKeyConfigured(data.apiKeyConfigured);
    } catch {
      setKeyConfigured(false);
    }
  }

  async function generate(e) {
    e.preventDefault();
    const t = topic.trim();
    if (!t || loading) return;

    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: t }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '生成失败');
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app" onLoad={checkHealth}>
      <header className="header">
        <div className="badge">Agent Skills · DeepSeek</div>
        <h1>PPT 结构生成器</h1>
        <p>输入一个主题，由 DeepSeek 模型生成结构化的 PPT 大纲（标题 + 幻灯片内容）</p>
      </header>

      <form className="input-card" onSubmit={generate}>
        <div className="input-row">
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="例如：新的智能家居助手"
            disabled={loading}
          />
          <button type="submit" disabled={loading || !topic.trim()}>
            {loading ? <span className="spinner" /> : '生成'}
          </button>
        </div>
        <div className="suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="chip" onClick={() => setTopic(s)} disabled={loading}>
              {s}
            </button>
          ))}
        </div>
        {keyConfigured === false && (
          <div className="hint warn">
            未检测到有效的 DEEPSEEK_API_KEY，请在 <code>web/config.env</code> 中填写后重启服务。
          </div>
        )}
      </form>

      {error && <div className="error-card">⚠️ {error}</div>}

      {loading && <div className="loading-card">DeepSeek 正在思考，请稍候…</div>}

      {result && (
        <main className="result">
          <div className="result-header">
            <h2>{result.title}</h2>
            <span className="meta">模型：{result.model} · 共 {result.slides.length} 页</span>
          </div>
          <div className="slides-grid">
            {result.slides.map((slide, i) => (
              <section className="slide-card" key={i}>
                <div className="slide-no">{String(i + 1).padStart(2, '0')}</div>
                <h3>{slide.title}</h3>
                <ul>
                  {slide.content.map((line, j) => (
                    <li key={j}>{line}</li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </main>
      )}

      <footer className="footer">React + Express · DeepSeek API · 配置文件：config.env</footer>
    </div>
  );
}
