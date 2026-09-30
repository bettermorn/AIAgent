"""生成示例价格数据：确保 RSI 超卖(<25)、RSI 超买(>75)、金叉、死叉等所有买卖规则均可触发。

用法:
    python data/generate_data.py
"""
import numpy as np
import pandas as pd

SEED = 42


def main():
    rng = np.random.default_rng(SEED)

    # 分段设计行情：
    # 1) 持续下跌 → RSI 超卖(<25)，触发 RSI 买入规则
    # 2) 强势上涨 → 金叉买入，且 RSI 超买(>75)，触发 RSI 卖出规则
    # 3) 明显回调 → 死叉卖出
    # 4) 再次上涨 → 再次金叉买入，随后温和回落形成死叉
    phases = [
        ("down", 18, 100.0, 76.0),    # 强下跌: 100 -> 76
        ("up", 32, 76.0, 112.0),      # 强上涨: 76 -> 112 (金叉 + RSI>75)
        ("down", 22, 112.0, 88.0),    # 回调: 112 -> 88 (死叉)
        ("up", 26, 88.0, 106.0),      # 再上涨: 88 -> 106 (再次金叉)
        ("down", 14, 106.0, 96.0),    # 温和回落: 106 -> 96 (再次死叉)
    ]

    prices = []
    for kind, n, start, end in phases:
        t = np.linspace(0, 1, n + 1)
        base = start + (end - start) * t
        noise = rng.normal(0, 0.35, size=n + 1) if kind == "up" else rng.normal(0, 0.5, size=n + 1)
        # 保证趋势方向不被噪声反转过多
        prices.extend((base + noise)[1:] if prices else base + noise)

    dates = pd.bdate_range("2025-01-02", periods=len(prices))
    df = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "price": np.round(prices, 2)})
    df.to_csv("sample_prices.csv", index=False)
    print(f"已生成 {len(df)} 条数据 -> sample_prices.csv")
    print(f"价格范围: {df['price'].min():.2f} ~ {df['price'].max():.2f}")


if __name__ == "__main__":
    main()
