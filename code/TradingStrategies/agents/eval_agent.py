import numpy as np

from agents.strategy_agent_llm import compute_rsi


def compute_indicators(prices, short=5, long=20):
    """计算短期均线、长期均线和 RSI 指标。"""
    short_ma = float(np.mean(prices[-short:])) if len(prices) >= short else None
    long_ma = float(np.mean(prices[-long:])) if len(prices) >= long else None
    rsi = compute_rsi(prices)
    return short_ma, long_ma, rsi


def eval_agent(data, mode, rule_agent=None, llm_agent=None, budget=100000, prev_state=None, short=5, long=20):
    dates = data["dates"]
    prices = data["prices"]
    state = prev_state or {"cash": budget, "shares": 0, "portfolio": budget, "history": []}

    today_price = prices[-1]
    action = "HOLD"

    if mode == "rule" and rule_agent:
        action = rule_agent(prices, state)
    elif mode == "llm" and llm_agent:
        action = llm_agent(prices, state)

    if action == "BUY" and state["cash"] >= today_price:
        shares_to_buy = int(state["cash"] // today_price)
        state["cash"] -= shares_to_buy * today_price
        state["shares"] += shares_to_buy
    elif action == "SELL" and state["shares"] > 0:
        state["cash"] += state["shares"] * today_price
        state["shares"] = 0

    state["portfolio"] = state["cash"] + state["shares"] * today_price

    # 记录技术指标：短期均线 / 长期均线 / RSI
    short_ma, long_ma, rsi = compute_indicators(prices, short=short, long=long)

    state["history"].append({"date": dates[-1], "price": today_price, "cash": state["cash"],
                             "shares": state["shares"], "portfolio": state["portfolio"], "action": action,
                             "short_ma": short_ma, "long_ma": long_ma, "rsi": rsi})
    return state
