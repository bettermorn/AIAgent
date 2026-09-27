"""Web 后端：为 React 前端提供交易回测与 DeepSeek 决策 API。

启动方式:
    python server.py
默认监听 http://127.0.0.1:5000
"""
import numpy as np
from flask import Flask, jsonify, request
from flask_cors import CORS

from agents.data_agent import load_data, data_agent_stream
from agents.strategy_agent_rule import strategy_agent_rule
from agents.strategy_agent_llm import strategy_agent_llm, compute_rsi
from agents.strategy_agent_hybrid import strategy_agent_hybrid
from agents.eval_agent import eval_agent
from agents import deepseek_client
from agents.deepseek_client import chat, is_configured

app = Flask(__name__)
CORS(app)


# ---------- 工具函数 ----------
def compute_metrics(portfolio_series, init_budget):
    import pandas as pd
    s = pd.Series(portfolio_series, dtype=float)
    returns = s.pct_change().dropna()
    cagr = (s.iloc[-1] / init_budget) ** (252 / len(s)) - 1 if len(s) > 0 else 0
    sharpe = float(np.sqrt(252) * returns.mean() / returns.std()) if returns.std() != 0 else 0.0
    mdd = float(((s.cummax() - s) / s.cummax()).max()) if len(s) > 0 else 0.0
    return {"final_value": float(s.iloc[-1]), "total_return": float(s.iloc[-1] / init_budget - 1),
            "cagr": float(cagr), "sharpe": sharpe, "mdd": mdd}


# ---------- API 接口 ----------
@app.get("/api/config")
def api_config():
    """返回 DeepSeek 配置信息（不返回 Key 明文）。"""
    return jsonify({
        "configured": is_configured(),
        "model": deepseek_client.DEEPSEEK_MODEL,
        "base_url": deepseek_client.DEEPSEEK_BASE_URL,
    })


@app.post("/api/backtest")
def api_backtest():
    """运行流式回测，返回逐日记录与绩效指标。"""
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "rule")
    budget = float(payload.get("budget", 100000))
    short = int(payload.get("short", 5))
    long = int(payload.get("long", 20))

    if mode not in ("rule", "llm", "hybrid"):
        return jsonify({"error": "mode 必须是 rule / llm / hybrid"}), 400
    if mode in ("llm", "hybrid") and not is_configured():
        return jsonify({"error": "DEEPSEEK_API_KEY 未配置，请编辑根目录 config.env"}), 500

    df = load_data()
    state = {"cash": budget, "shares": 0, "portfolio": budget, "history": []}

    for i in range(len(df)):
        data = data_agent_stream(df, i)
        if mode == "rule":
            decision_func = lambda hist, s: strategy_agent_rule(hist, s, short, long)
            state = eval_agent(data, mode="rule", rule_agent=decision_func, budget=budget, prev_state=state, short=short, long=long)
        else:
            agent = strategy_agent_llm if mode == "llm" else strategy_agent_hybrid
            decision_func = lambda hist, s, a=agent: a(hist, s, short, long)
            state = eval_agent(data, mode="llm", llm_agent=decision_func, budget=budget, prev_state=state, short=short, long=long)

    metrics = compute_metrics([h["portfolio"] for h in state["history"]], budget)
    return jsonify({"mode": mode, "budget": budget, "history": state["history"], "metrics": metrics})


@app.post("/api/decision")
def api_decision():
    """输入最近价格序列与持仓，调用 DeepSeek 给出 BUY/SELL/HOLD 建议。"""
    payload = request.get_json(silent=True) or {}
    raw_prices = payload.get("prices", [])
    shares = int(payload.get("shares", 0))

    try:
        prices = [float(p) for p in raw_prices if str(p).strip() != ""]
    except (TypeError, ValueError):
        return jsonify({"error": "价格列表格式错误，请输入逗号分隔的数字"}), 400
    if len(prices) < 2:
        return jsonify({"error": "请至少输入 2 个价格"}), 400
    if not is_configured():
        return jsonify({"error": "DEEPSEEK_API_KEY 未配置，请编辑根目录 config.env"}), 500

    short = int(payload.get("short", 5))
    long = int(payload.get("long", 20))
    rsi = compute_rsi(prices)
    short_ma = float(np.mean(prices[-short:])) if len(prices) >= short else None
    long_ma = float(np.mean(prices[-long:])) if len(prices) >= long else None

    recent_str = ", ".join(f"{p:.2f}" for p in prices[-7:])
    prompt = f"""你是一个交易策略助手。请基于以下信息严格输出 BUY / SELL / HOLD：

- 最近价格: {recent_str}
- 当前价格: {prices[-1]}
- 短期均线({short}日): {short_ma}
- 长期均线({long}日): {long_ma}
- RSI(14): {rsi if rsi is not None else 'None'}
- 当前持仓股数: {shares}

规则：
- RSI < 30 且未持仓: BUY
- RSI > 70 且已持仓: SELL
- 短均线上穿长均线: BUY
- 短均线下穿长均线: SELL
- 其余情况: HOLD

第一行只输出一个词：BUY / SELL / HOLD，第二行用一句话说明理由。"""

    try:
        result = chat(
            messages=[{"role": "system", "content": "你是一个交易策略助手。"},
                      {"role": "user", "content": prompt}],
            temperature=0.0,
        )
    except Exception as e:
        return jsonify({"error": f"调用 DeepSeek 失败: {e}"}), 500

    lines = [l.strip() for l in result.splitlines() if l.strip()]
    decision = lines[0].upper().replace(".", "").replace("。", "")
    if decision not in ("BUY", "SELL", "HOLD"):
        decision = "HOLD"
    reason = lines[1] if len(lines) > 1 else ""

    return jsonify({
        "decision": decision,
        "reason": reason,
        "model": deepseek_client.DEEPSEEK_MODEL,
        "indicators": {"price": prices[-1], "short_ma": short_ma, "long_ma": long_ma, "rsi": rsi},
    })


if __name__ == "__main__":
    print("Trading Strategies API Server: http://127.0.0.1:5000")
    if not is_configured():
        print("警告: 请先在 config.env 中配置 DEEPSEEK_API_KEY")
    app.run(host="127.0.0.1", port=5000, debug=True)
