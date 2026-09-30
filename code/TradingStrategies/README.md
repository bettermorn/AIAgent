# Trading Agents Package (Teaching Demo)

本项目演示了一个教学用的交易代理系统，包含 **三种策略 Agent** 与一个 **React Web 应用**：

- **Rule**: 纯规则策略，基于均线交叉生成 BUY / SELL 信号。
- **LLM**: 大模型策略，输入 RSI 和均线指标，让 **DeepSeek** 模型决策 BUY / SELL / HOLD。
- **Hybrid**: 混合策略，结合规则、风险控制与 LLM 辅助，避免明显亏损并提升稳定性。

> LLM 能力统一通过 `DEEPSEEK_API_KEY` 调用 DeepSeek 模型（OpenAI 兼容接口），配置文件为项目根目录的 `config.env`。

---


## 参考代码

https://github.com/yh-yao/super_agent_book/tree/main/%E5%AE%9E%E6%97%B6%E5%A4%9A%E6%99%BA%E8%83%BD%E4%BD%93_%E9%87%91%E8%9E%8D%E5%86%B3%E7%AD%96

## 快速开始

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 DeepSeek API Key

编辑项目根目录的 `config.env`，填入你的 DeepSeek API Key（获取地址：https://platform.deepseek.com ）：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

| 配置项 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（必填） |
| `DEEPSEEK_BASE_URL` | API 地址，默认 `https://api.deepseek.com`，一般无需修改 |
| `DEEPSEEK_MODEL` | 模型名：`deepseek-chat`（V3）或 `deepseek-reasoner`（R1） |

> `config.env` 已加入 `.gitignore`，请勿提交到版本库。

---

## 运行方式

### 方式一：命令行流式回测

进入项目目录后，可以选择不同策略模式：

```bash
# Rule 策略
python streaming_main.py --mode rule --budget 100000 --short 5 --long 20

# LLM 策略（DeepSeek）
python streaming_main.py --mode llm --budget 100000 --short 5 --long 20

# Hybrid 策略（推荐）
python streaming_main.py --mode hybrid --budget 100000 --short 5 --long 20
```

#### 参数说明
- `--mode`: 运行模式，可选 `rule` / `llm` / `hybrid`  
- `--budget`: 初始资金 (默认 100000)  
- `--short`: 短期均线窗口 (默认 5)  
- `--long`: 长期均线窗口 (默认 20)  

#### 结果输出
运行后会：
- 打印每日价格、短期/长期均线、RSI 值  
- 输出决策说明（规则解释或 DeepSeek 辅助信号）  
- 在结束时输出最终的投资组合报告，包括资金余额、持仓股数、组合总价值等  

#### 示例数据说明
`data/sample_prices.csv` 由 `data/generate_data.py` 生成，行情分段设计为确保 **所有买卖规则均可触发**：

| 行情阶段 | 触发的规则 |
| --- | --- |
| 持续强下跌（RSI < 25） | RSI 超卖买入（LLM / Hybrid 硬约束） |
| 强势上涨（短期均线上穿长期均线） | 金叉买入（Rule 及各策略） |
| 强势上涨后期（RSI > 75） | RSI 超买卖出（LLM / Hybrid 硬约束） |
| 明显回调（短期均线下穿长期均线） | 死叉卖出（Rule 及各策略） |

如需重新生成数据：`python data/generate_data.py`

### 方式二：React Web 应用（推荐）

Web 应用由 **Flask 后端 API**（`server.py`）+ **React 前端**（`web/`）组成，DeepSeek 的调用发生在后端，API Key 不会暴露给浏览器。

**1. 启动后端（项目根目录）：**

```bash
python server.py
```

后端监听 `http://127.0.0.1:5000`。

**2. 启动前端（新开终端）：**

```bash
cd web
npm install
npm run dev
```

浏览器打开 `http://localhost:5173` 即可使用。

**3. Web 功能：**
- **策略回测**：选择 rule / llm / hybrid 模式，设置初始资金与均线窗口，运行回测后查看组合价值曲线、价格与短期/长期均线图、RSI 图（含 25/75 超卖超买参考线）、绩效指标（总收益率、CAGR、Sharpe、最大回撤）与完整交易明细（含每日短期均线、长期均线、RSI）。
- **DeepSeek 实时决策**：输入最近价格序列与当前持仓，由 DeepSeek 模型给出 BUY / SELL / HOLD 建议及理由，并展示实时计算的技术指标。

**4. 生产构建（可选）：**

```bash
cd web
npm run build
```

构建产物在 `web/dist/`，可将后端 `server.py` 中的静态目录指向该目录进行部署。

---

## API 接口（server.py）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/config` | 返回 DeepSeek 配置状态（不含 Key 明文） |
| POST | `/api/backtest` | 运行回测，入参 `{mode, budget, short, long}`，返回逐日记录与绩效指标 |
| POST | `/api/decision` | 调用 DeepSeek 决策，入参 `{prices, shares, short, long}`，返回决策、理由与指标 |

---

## 文件结构
```
TradingStrategies/
├─ agents/
│  ├─ strategy_agent_rule.py      # 规则策略
│  ├─ strategy_agent_llm.py       # 大模型策略（DeepSeek）
│  ├─ strategy_agent_hybrid.py    # 混合策略（DeepSeek 辅助）
│  ├─ deepseek_client.py          # DeepSeek 客户端公共模块（读取 config.env）
│  ├─ data_agent.py               # 数据加载
│  ├─ eval_agent.py               # 回测执行
│  ├─ report_agent.py             # 报告输出
├─ data/
│  └─ sample_prices.csv           # 示例价格数据
├─ web/                           # React 前端（Vite）
│  ├─ src/
│  │  ├─ App.jsx                  # 应用入口（Tab 切换）
│  │  ├─ api.js                   # API 请求封装
│  │  ├─ components/
│  │  │  ├─ BacktestPanel.jsx     # 策略回测面板
│  │  │  └─ DecisionPanel.jsx     # DeepSeek 实时决策面板
│  │  └─ index.css                # 全局样式
│  ├─ index.html
│  ├─ vite.config.js              # 开发代理到 Flask 后端
│  └─ package.json
├─ streaming_main.py              # 命令行主程序
├─ server.py                      # Flask 后端 API
├─ config.env                     # DeepSeek API 配置（不入库）
├─ requirements.txt               # Python 依赖列表
└─ README.md                      # 项目说明
```

---

## 推荐使用方式
建议优先使用 **Hybrid 策略**：
- 在强信号时由规则直接决策（避免 LLM 出错）  
- 在模糊区间时引入 DeepSeek 提供辅助意见  
- 内置止损/止盈逻辑，提高资金曲线稳定性  

> 本项目仅用于教学演示，请勿用于真实交易。
