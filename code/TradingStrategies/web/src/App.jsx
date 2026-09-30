import React, { useEffect, useState } from "react";
import { fetchConfig } from "./api.js";
import BacktestPanel from "./components/BacktestPanel.jsx";
import DecisionPanel from "./components/DecisionPanel.jsx";

export default function App() {
  const [config, setConfig] = useState(null);
  const [tab, setTab] = useState("backtest");

  useEffect(() => {
    fetchConfig()
      .then(setConfig)
      .catch(() => setConfig({ configured: false, model: "unknown" }));
  }, []);

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Trading Strategies</h1>
          <p className="subtitle">交易策略教学系统 · Rule / LLM(DeepSeek) / Hybrid</p>
        </div>
        {config && (
          <div className="config-badge" title="配置来自项目根目录 config.env">
            <span className={`dot ${config.configured ? "ok" : "bad"}`} />
            DeepSeek · {config.model}
            {config.configured ? "" : "（未配置 Key）"}
          </div>
        )}
      </header>

      <nav className="tabs">
        <button
          className={tab === "backtest" ? "active" : ""}
          onClick={() => setTab("backtest")}
        >
          策略回测
        </button>
        <button
          className={tab === "decision" ? "active" : ""}
          onClick={() => setTab("decision")}
        >
          DeepSeek 实时决策
        </button>
      </nav>

      <main>
        {tab === "backtest" ? <BacktestPanel /> : <DecisionPanel />}
      </main>

      <footer className="footer">
        教学演示项目 · 请勿用于真实交易 · LLM 策略依赖根目录 config.env 中的 DEEPSEEK_API_KEY
      </footer>
    </div>
  );
}
