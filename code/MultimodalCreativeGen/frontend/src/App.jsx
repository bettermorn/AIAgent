import { useState } from "react";

const STEPS = [
  { key: "copywriter", label: "文案 Agent", desc: "生成广告初稿" },
  { key: "reviewer", label: "校对 Agent", desc: "润色并优化文案" },
  { key: "designer", label: "设计 Agent", desc: "绘制 SVG 海报" },
];

async function postJSON(url, body) {
  let res;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw new Error("无法连接后端服务，请确认 server 已启动 (npm run dev)");
  }
  let data = {};
  try {
    data = await res.json();
  } catch {
    // 非 JSON 响应（如代理/网关错误）
  }
  if (!res.ok) throw new Error(data.error || `请求失败 (${res.status})`);
  return data;
}

export default function App() {
  const [product, setProduct] = useState("");
  const [audience, setAudience] = useState("");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [stepIndex, setStepIndex] = useState(-1);
  const [draft, setDraft] = useState("");
  const [finalText, setFinalText] = useState("");
  const [svg, setSvg] = useState("");

  const canRun = product.trim() && audience.trim() && !running;

  async function handleRun(e) {
    e.preventDefault();
    setRunning(true);
    setError("");
    setDraft("");
    setFinalText("");
    setSvg("");

    try {
      // Step 1: 文案 Agent 生成初稿
      setStepIndex(0);
      const { draft: d } = await postJSON("/api/copywriter", {
        product: product.trim(),
        audience: audience.trim(),
      });
      setDraft(d);

      // Step 2: 校对 Agent 润色
      setStepIndex(1);
      const { final: f } = await postJSON("/api/reviewer", { text: d });
      setFinalText(f);

      // Step 3: 设计 Agent 生成海报
      setStepIndex(2);
      const { svg: s } = await postJSON("/api/designer", { text: f });
      setSvg(s);

      setStepIndex(3);
    } catch (err) {
      setError(err.message);
      setStepIndex(-1);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="page">
      <header className="hero">
        <h1>✨ AI 多模态创意工坊</h1>
        <p>DeepSeek 多 Agent 协作 · 文案 → 校对 → 海报设计</p>
      </header>

      <main className="container">
        <section className="card form-card">
          <h2>创意brief</h2>
          <form onSubmit={handleRun} className="form">
            <label>
              产品名称
              <input
                value={product}
                onChange={(e) => setProduct(e.target.value)}
                placeholder="例如：夏日柠檬饮料"
                disabled={running}
              />
            </label>
            <label>
              目标受众
              <input
                value={audience}
                onChange={(e) => setAudience(e.target.value)}
                placeholder="例如：年轻人"
                disabled={running}
              />
            </label>
            <button type="submit" disabled={!canRun}>
              {running ? "生成中…" : "🚀 开始创作"}
            </button>
          </form>
        </section>

        <section className="card steps-card">
          <h2>Agent 工作流</h2>
          <ol className="steps">
            {STEPS.map((step, i) => {
              const state =
                stepIndex > i || stepIndex === 3
                  ? "done"
                  : stepIndex === i
                    ? "running"
                    : "pending";
              return (
                <li key={step.key} className={`step ${state}`}>
                  <span className="step-icon">
                    {state === "done" ? "✓" : state === "running" ? "◌" : i + 1}
                  </span>
                  <div>
                    <div className="step-label">{step.label}</div>
                    <div className="step-desc">{step.desc}</div>
                  </div>
                </li>
              );
            })}
          </ol>

          {error && <div className="error">⚠️ {error}</div>}
        </section>

        {draft && (
          <section className="card result-card">
            <h2>📝 文案初稿</h2>
            <blockquote className="copy draft">{draft}</blockquote>
          </section>
        )}

        {finalText && (
          <section className="card result-card highlight">
            <h2>✅ 最终文案</h2>
            <blockquote className="copy final">{finalText}</blockquote>
          </section>
        )}

        {svg && (
          <section className="card poster-card">
            <h2>🎨 AI 生成海报</h2>
            <div
              className="poster"
              dangerouslySetInnerHTML={{ __html: svg }}
            />
          </section>
        )}
      </main>

      <footer className="footer">
        Powered by DeepSeek · React + Express
      </footer>
    </div>
  );
}
