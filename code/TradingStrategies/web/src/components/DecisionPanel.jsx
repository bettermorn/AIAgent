import React, { useState } from "react";
import { getDecision } from "../api.js";

const fmt = (v, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "-"
    : Number(v).toFixed(digits);

const DEMO_PRICES = [
  95.2, 95.8, 94.6, 95.1, 96.0, 96.4, 95.7, 94.9, 94.2, 93.5,
  92.8, 92.1, 92.6, 93.4, 94.1, 93.8, 94.5, 95.3, 96.2, 96.8,
  97.1, 96.5, 97.4, 98.0, 97.6, 98.3, 98.8, 98.4, 99.1, 99.6,
];

export default function DecisionPanel() {
  const [pricesText, setPricesText] = useState(DEMO_PRICES.join(", "));
  const [shares, setShares] = useState(0);
  const [short, setShort] = useState(5);
  const [long, setLong] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const prices = pricesText
        .split(/[,，\s]+/)
        .filter((s) => s !== "")
        .map(Number);
      if (prices.some((p) => Number.isNaN(p))) throw new Error("价格列表包含非数字内容");
      if (prices.length < 20) throw new Error(`仅输入了 ${prices.length} 个价格，请至少输入 20 个，否则长期均线和 RSI 无法计算`);
      const data = await getDecision({ prices, shares: Number(shares), short: Number(short), long: Number(long) });
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const ind = result?.indicators;

  return (
    <section>
      <div className="card form">
        <div className="field wide">
          <label>最近价格序列（逗号分隔，至少 20 个价格才能计算长期均线，至少 15 个才能计算 RSI）</label>
          <textarea
            rows={4}
            value={pricesText}
            onChange={(e) => setPricesText(e.target.value)}
            placeholder="例如: 95.2, 95.8, 94.6, …（建议粘贴近 30 个交易日的收盘价）"
          />
        </div>
        <div className="field">
          <label>当前持仓股数</label>
          <input type="number" min="0" value={shares} onChange={(e) => setShares(e.target.value)} />
        </div>
        <div className="field">
          <label>短期均线</label>
          <input type="number" min="2" max="50" value={short} onChange={(e) => setShort(e.target.value)} />
        </div>
        <div className="field">
          <label>长期均线</label>
          <input type="number" min="3" max="200" value={long} onChange={(e) => setLong(e.target.value)} />
        </div>
        <button className="primary" type="submit" onClick={handleSubmit} disabled={loading}>
          {loading ? (
            <>
              <span className="spinner" aria-hidden="true"></span>
              DeepSeek 分析中…
            </>
          ) : (
            "调用 DeepSeek 决策"
          )}
        </button>
      </div>

      {error && <div className="alert error">{error}</div>}

      {loading && (
        <div className="card loading-card">
          <span className="spinner large" aria-hidden="true"></span>
          <span>DeepSeek 正在分析行情数据，请稍候…</span>
        </div>
      )}

      {result && (
        <div className="card decision-card">
          <div className="decision-head">
            <span className={`decision ${result.decision.toLowerCase()}`}>{result.decision}</span>
            <span className="model-tag">模型: {result.model}</span>
          </div>
          <p className="reason">{result.reason || "（模型未给出说明）"}</p>
          {ind && (
            <div className="indicators">
              <div>
                <span className="label">当前价格</span>
                <span>{fmt(ind.price)}</span>
              </div>
              <div>
                <span className="label">短期均线</span>
                <span>{fmt(ind.short_ma)}</span>
              </div>
              <div>
                <span className="label">长期均线</span>
                <span>{fmt(ind.long_ma)}</span>
              </div>
              <div>
                <span className="label">RSI(14)</span>
                <span>{fmt(ind.rsi)}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
