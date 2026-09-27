import argparse
import numpy as np
from agents.data_agent import load_data, data_agent_stream
from agents.strategy_agent_rule import strategy_agent_rule
from agents.strategy_agent_llm import strategy_agent_llm, compute_rsi
from agents.strategy_agent_hybrid import strategy_agent_hybrid   
from agents.eval_agent import eval_agent
from agents.report_agent import report_agent


def run_streaming(mode="rule", budget=100000, short=5, long=20):
    df = load_data()
    state = {"cash": budget, "shares": 0, "portfolio": budget, "history": []}

    for i in range(len(df)):
        data = data_agent_stream(df, i)
        prices = data["prices"]

        short_ma = np.mean(prices[-short:]) if len(prices) >= short else None
        long_ma = np.mean(prices[-long:]) if len(prices) >= long else None
        rsi = compute_rsi(prices)

        short_ma_str = f"{short_ma:.2f}" if short_ma is not None else "None"
        long_ma_str = f"{long_ma:.2f}" if long_ma is not None else "None"
        rsi_str = f"{rsi:.2f}" if rsi is not None else "None"
        print(f"[{data['dates'][-1]}] Price={prices[-1]:.2f}, ShortMA={short_ma_str}, LongMA={long_ma_str}, RSI={rsi_str}")

        if mode == "rule":
            print(f"📏 规则策略正在基于 RSI/均线分析决策…")
            decision_func = lambda hist, s: strategy_agent_rule(hist, s, short, long)
            state = eval_agent(data, mode="rule", rule_agent=decision_func, budget=budget, prev_state=state, short=short, long=long)

        elif mode == "llm":
            print(f"🤖 LLM 正在基于 RSI/均线分析决策…")
            decision_func = lambda hist, s: strategy_agent_llm(hist, s, short, long)
            state = eval_agent(data, mode="llm", llm_agent=decision_func, budget=budget, prev_state=state, short=short, long=long)

        elif mode == "hybrid":
            print(f"⚖️ Hybrid 策略：规则 + 风险控制 + LLM 辅助决策…")
            decision_func = lambda hist, s: strategy_agent_hybrid(hist, s, short, long)
            state = eval_agent(data, mode="llm", llm_agent=decision_func, budget=budget, prev_state=state, short=short, long=long)
        else:
            raise ValueError("Invalid mode. Choose from 'rule', 'llm', 'hybrid'.")
        
        print(f"策略决策: {state['history'][-1]['action']}")
        print(f"当前持仓: {state['shares']} 股, 现金: {state['cash']:.2f}, 组合价值: {state['portfolio']:.2f}\n")


    final = report_agent(state, init_budget=budget, mode=mode)
    print(final["report"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["rule", "llm", "hybrid"], default="rule")
    parser.add_argument("--budget", type=float, default=100000.0)
    parser.add_argument("--short", type=int, default=5)
    parser.add_argument("--long", type=int, default=20)
    args = parser.parse_args()

    print(f"🚀 Streaming Mode: {args.mode}, budget={args.budget}")
    run_streaming(mode=args.mode, budget=args.budget, short=args.short, long=args.long)
