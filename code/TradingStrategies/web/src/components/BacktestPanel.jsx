import React, { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { runBacktest } from "../api.js";

const MODES = [
  { value: "rule", label: "Rule 规则策略" },
  { value: "llm", label: "LLM 策略 (DeepSeek)" },
  { value: "hybrid", label: "Hybrid 混合策略" },
];

const fmt = (v) =>
  v === null || v === undefined ? "-" : Number(v).toLocaleString("zh-CN", { maximumFractionDigits: 2 });

export default function BacktestPanel() {
  const [form, setForm] = useState({ mode: "rule", budget: 100000, short: 5, long: 20 });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const handleChange = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await runBacktest({
        mode: form.mode,
        budget: Number(form.budget),
        short: Number(form.short),
        long: Number(form.long),
      });
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section>
      <form className="card form" onSubmit={handleSubmit}>
        <div className="field">
          <label>策略模式</label>
          <select value={form.mode} onChange={handleChange("mode")}>
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>初始资金</label>
          <input type="number" min="1000" step="1000" value={form.budget} onChange={handleChange("budget")} />
        </div>
        <div className="field">
          <label>短期均线</label>
          <input type="number" min="2" max="50" value={form.short} onChange={handleChange("short")} />
        </div>
        <div className="field">
          <label>长期均线</label>
          <input type="number" min="3" max="200" value={form.long} onChange={handleChange("long")} />
        </div>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? (
            <>
              <span className="spinner" aria-hidden="true"></span>
              回测运行中…
            </>
          ) : (
            "开始回测"
          )}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}

      {loading && (
        <div className="card loading-card">
          <span className="spinner large" aria-hidden="true"></span>
          <span>回测运行中，请稍候…</span>
        </div>
      )}

      {result && (
        <>
          <div className="metrics-grid">
            <div className="metric">
              <span className="label">最终组合价值</span>
              <span className="value">{fmt(result.metrics.final_value)}</span>
            </div>
            <div className="metric">
              <span className="label">总收益率</span>
              <span className={`value ${(result.metrics.total_return * 100).toFixed(2) >= 0 ? "up" : "down"}`}>
                {(result.metrics.total_return * 100).toFixed(2)}%
              </span>
            </div>
            <div className="metric">
              <span className="label">CAGR 年化收益</span>
              <span className="value">{(result.metrics.cagr * 100).toFixed(2)}%</span>
            </div>
            <div className="metric">
              <span className="label">Sharpe 夏普比率</span>
              <span className="value">{result.metrics.sharpe.toFixed(2)}</span>
            </div>
            <div className="metric">
              <span className="label">MDD 最大回撤</span>
              <span className="value down">{(result.metrics.mdd * 100).toFixed(2)}%</span>
            </div>
          </div>

          <div className="card">
            <h3>组合价值曲线</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={result.history}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3142" />
                <XAxis dataKey="date" stroke="#8b93a7" fontSize={12} />
                <YAxis stroke="#8b93a7" fontSize={12} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: "#1c2230", border: "1px solid #333b4d", borderRadius: 8 }}
                  formatter={(v) => fmt(v)}
                />
                <Line type="monotone" dataKey="portfolio" stroke="#4f8cff" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h3>价格与均线（短期 {form.short} 日 / 长期 {form.long} 日）</h3>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={result.history}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3142" />
                <XAxis dataKey="date" stroke="#8b93a7" fontSize={12} />
                <YAxis stroke="#8b93a7" fontSize={12} domain={["auto", "auto"]} />
                <Tooltip
                  contentStyle={{ background: "#1c2230", border: "1px solid #333b4d", borderRadius: 8 }}
                  formatter={(v) => fmt(v)}
                />
                <Legend />
                <Line type="monotone" dataKey="price" name="价格" stroke="#e7eaf2" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="short_ma" name="短期均线" stroke="#4f8cff" strokeWidth={2} dot={false} connectNulls />
                <Line type="monotone" dataKey="long_ma" name="长期均线" stroke="#f5a623" strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h3>RSI（14 期，低于 25 超卖 / 高于 75 超买）</h3>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={result.history}>
                <CartesianGrid strokeDasharray="3 3" stroke="#2a3142" />
                <XAxis dataKey="date" stroke="#8b93a7" fontSize={12} />
                <YAxis stroke="#8b93a7" fontSize={12} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} />
                <Tooltip
                  contentStyle={{ background: "#1c2230", border: "1px solid #333b4d", borderRadius: 8 }}
                  formatter={(v) => fmt(v)}
                />
                <ReferenceLine y={75} stroke="#e5484d" strokeDasharray="6 4" label={{ value: "超买 75", fill: "#e5484d", fontSize: 11, position: "insideTopRight" }} />
                <ReferenceLine y={25} stroke="#2fbf71" strokeDasharray="6 4" label={{ value: "超卖 25", fill: "#2fbf71", fontSize: 11, position: "insideBottomRight" }} />
                <Line type="monotone" dataKey="rsi" name="RSI" stroke="#b56cff" strokeWidth={2} dot={false} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h3>交易明细（共 {result.history.length} 条）</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>日期</th>
                    <th>价格</th>
                    <th>短期均线</th>
                    <th>长期均线</th>
                    <th>RSI</th>
                    <th>决策</th>
                    <th>现金</th>
                    <th>持仓</th>
                    <th>组合价值</th>
                  </tr>
                </thead>
                <tbody>
                  {result.history.map((h, i) => (
                    <tr key={i}>
                      <td>{h.date}</td>
                      <td>{fmt(h.price)}</td>
                      <td>{fmt(h.short_ma)}</td>
                      <td>{fmt(h.long_ma)}</td>
                      <td className={h.rsi != null ? (h.rsi < 25 ? "rsi-low" : h.rsi > 75 ? "rsi-high" : "") : ""}>
                        {fmt(h.rsi)}
                      </td>
                      <td>
                        <span className={`tag ${h.action.toLowerCase()}`}>{h.action}</span>
                      </td>
                      <td>{fmt(h.cash)}</td>
                      <td>{h.shares}</td>
                      <td>{fmt(h.portfolio)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
