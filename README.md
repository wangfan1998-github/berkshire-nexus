# BerkshireNexus 🎯

> **拒绝废话与两头讨好**：融合 **Serenity 产业链物理瓶颈** + **Berkshire 价值四大师** + **Qlib 微软多因子量化** 的硬核 AI 投研决策框架。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)
[![Zero Dependency](https://img.shields.io/badge/Dependencies-Zero%20External-orange.svg)](pyproject.toml)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-black)](SKILL.md)
[![中文优先](https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E4%BC%98%E5%85%88-red)](README.md)
[![English](https://img.shields.io/badge/English-README__EN.md-lightgrey)](README_EN.md)

---

## 💡 为什么写这个项目？

如果你直接问 ChatGPT 或 Claude：“某某股票值不值得买？”，99% 的情况下你会得到这样一段“合格但毫无用处”的废话：

> *“一方面，该公司在 AI 领域有增长潜力，市场空间广阔；但另一方面，宏观环境存在不确定性，且竞争激烈……投资者需结合自身风险承受能力自行决定。”*

**这种分析看似全面客观，但在真金白银的交易决策中价值为零。**

在真实世界里，投资是一门**关于取舍、反偏见、概率与赔率**的残酷博弈。你需要的不是两头下注的套话，而是：
1. **有没有物理级不可替代的供应链瓶颈（Chokepoint）？** （不要听管理层讲故事，看谁卡死了产能）
2. **商业模式能否通过段永平的 5 句话镜子测试？** （5句话说不清楚商业模式赚什么钱，直接不买）
3. **查理·芒格的逆向致死检验（Inversion）**：在什么极端情况下这家公司会死？
4. **格雷厄姆与巴菲特所有者收益（Owner Earnings DCF）**：扣掉虚高的估值泡沫，真实的自由现金流安全边际有多少？
5. **对冲基金风控纪律**：如果买，单一个股仓位上限是多少？什么时候必须止损一票否决？

`BerkshireNexus` 就是为了解决这个问题而诞生的。它吸收并提炼了 GitHub 上最顶尖的投研项目之精髓（`serenity-skill`、`ai-berkshire`、`qlib`、`ai-hedge-fund`、`Value-Investing-Agent`），构建出一套**强制输出明确结论、多视角激烈对抗、量化数据交叉印证**的现代化投研决策体系。

---

## 🏛️ 决策漏斗与工作机制

```
                                【候选股票池 / Tickers】
                                           │
    ┌──────────────────────────────────────┼──────────────────────────────────────┐
    ▼                                      ▼                                      ▼
【1. Serenity 物理瓶颈检验】          【2. Berkshire 大师对抗辩论】          【3. Qlib 多因子量化评分】
• 物理不可替代度 (0-10)               • 巴菲特 (所有者收益/高ROE)            • Quality 质量 (ROE/利润率/负债)
• 扩产周期与 CapEx 壁垒 (0-10)        • 芒格 (逆向思维: 什么会让它死?)       • Value 价值 (前瞻收益率/FCF Yield)
• 5 级瓶颈定级 (Level 1~5)           • 段永平 (商业模式/5句话镜子测试)      • Growth 成长 (营收/EPS 加速度)
• 定价权与供应链利润截留比例         • 李录 / 阿克曼 / 木头姐 对抗裁决     • Momentum 动量 & Low-Beta 风险
    │                                      │                                      │
    └──────────────────────────────────────┼──────────────────────────────────────┘
                                           │
                                           ▼
                      【4. Value-Investing 深度内在价值测算】
                      • 两阶段自由现金流折现模型 (Two-Stage Owner Earnings DCF)
                      • 格雷厄姆防御与成长公式
                      • 真实安全边际 (Margin of Safety %) 测算
                                           │
                                           ▼
                      【5. 对冲基金风控与仓位裁决 (Risk Manager)】
                      • 组合角色定性 (核心基石 / 物理收费站 / 进攻奇兵 / 一票否决)
                      • 动态持仓上限建议 (Max Allocation Cap %)
                      • 离场触发红线 (Redline Inversion Triggers)
                                           │
                                           ▼
                    【📊 最终决策备忘录 (Executive Investment Memo)】
```

---

## 🚀 极速上手 (Quick Start)

本项目采用 **零外部依赖（Zero Dependency）** 设计，无需繁琐的 `pip install` 环境配置，克隆后在 Python 3.9+ 终端即可运行。

### 0. 自动学习模拟交易 Agent（推荐从这里开始）

新版在原有 BerkshireNexus 投研框架之上增加了一个可审计闭环：

```text
BerkshireNexus 分析 → 有界特征 → 自适应收益模型 → Champion/Challenger
       → 目标仓位规划 → 确定性风控 → 持久化模拟成交 → 延迟收益标签
```

运行一次模拟盘周期：

```bash
python3 -m src.cli paper AAPL MSFT NVDA --cash 100000
```

默认状态写入 `.berkshire-nexus/`：

- `paper_portfolio.json`：现金、持仓、当日权益与换手；
- `paper_executions.jsonl`：仅追加的模拟成交日志；
- `learning.json`：分析快照和到期后的前瞻收益标签；
- `model_registry.json`：Champion / Challenger 模型；
- `audits/cycle-*.json`：每轮分析、意图、风控和成交的完整审计记录。

每个分析快照默认等待 20 个日历日再用新价格结算标签，达到 30 个样本后才训练 Challenger。训练集与验证集按时间顺序切分，不随机打乱。模型是透明、带 L2 约束的线性收益模型，只学习各投研因子与未来收益的历史关系，不会修改风控规则。

自动晋升默认关闭。查看并人工晋升模型：

```bash
python3 -m src.cli model-status
python3 -m src.cli model-promote
```

只在模拟盘中允许通过验证门槛的模型自动晋升：

```bash
python3 -m src.cli paper AAPL MSFT NVDA --auto-promote-paper
```

也可导入已经按时间点构造、带前瞻收益标签的数据。字段和值域参见 [`examples/learning_observations_template.csv`](examples/learning_observations_template.csv)，特征为 `0~1`，`forward_return` 使用小数收益率（`0.05` 表示 `+5%`）：

```bash
python3 -m src.cli learn examples/learning_observations_template.csv
```

示例只有两行，用于说明格式，不足以训练模型。生产数据必须确保每个特征只使用该行 `timestamp` 当时已知的信息，避免未来数据泄漏。

### Binance 美股接入边界

代码通过 Binance Stocks `/sapi/v1/equity/*` 原生 SAPI 适配，不依赖 CCXT。先做只读连通性和标的检查：

```bash
export BINANCE_API_KEY='your-read-only-key'
python3 -m src.cli binance-preflight AAPL MSFT
```

当前版本**没有暴露一键实盘 CLI**。原因是自动实盘前还必须实现并验证 Binance 权威持仓/现金快照、订单状态回补和重启对账；用本地模拟持仓替代真实账户状态是不安全的。底层 `BinanceStocksClient.place_order()` 已实现，但需要同时满足构造参数 `allow_live_orders=True` 和进程确认变量 `BERKSHIRE_NEXUS_LIVE_TRADING=I_ACKNOWLEDGE_REAL_MONEY`，且固定发送 `tokenize=false`。

所有订单都必须经过与模型隔离的确定性风控。默认规则包括：

- 单一标的持仓不超过组合的 10%；
- 每日总换手不超过组合的 25%；
- 当日亏损达到 1% 后停止新增风险；
- 实盘默认禁用市价单；
- 含预置、回退或推断数据的分析不能触发实盘买入；
- 风险开关触发后仍允许合法的减仓卖出。

Binance Stocks 的账户资格、地区限制、PDT、交易时段和免责声明要求仍由 Binance 与当地法规决定。官方没有文档化的 Stocks 测试网，因此本项目把本地模拟盘作为上线前必经阶段。

### 1. 多股票横截面横向 PK 排序 (`compare`)

输入任意多只股票代码，框架会自动调用多因子模型与大师委员会进行综合打分与排序：

```bash
python3 -m src.cli compare TSM UBER APP ADBE SOFI
```

**运行结果输出**：
```text
╔════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                         🏆 BerkshireNexus Cross-Sectional Ranking & Comparison Board                       ║
╚════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝

Rank  Ticker   Company Name             Price (P/E)      Chokepoint      Masters      MoS (DCF)    Qlib Alpha   Total      Recommendation     
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
🥇 #1 UBER     Uber Technologies, Inc   $79.29 (17.4x)   L4 (8.50)       4.62/5.0     +16.9%       64.6         79.3       STRONG BUY        
🥈 #2 APP      AppLovin Corporation     $298.59 (22.9x)  L3 (6.97)       3.80/5.0     +48.7%       74.4         78.8       BUY (Satellite)   
🥉 #3 TSM      Taiwan Semiconductor     $205.00 (24.2x)  L5 (9.63)       4.52/5.0     -12.4%       74.2         77.8       BUY (Core Infra)  
   #4 ADBE     Adobe Inc.               $276.27 (15.8x)  L3 (7.61)       3.43/5.0     +15.1%       65.8         70.8       HOLD (Watchlist)  
   #5 SOFI     SoFi Technologies Inc    $18.24 (38.4x)   L1 (4.23)       2.45/5.0     -86.3%       37.8         34.8       AVOID / EXIT      
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
```

---

### 2. 单股票全维度透视决策备忘录 (`analyze`)

```bash
python3 -m src.cli analyze UBER
```

**输出示例**：
```text
╔══════════════════════════════════════════════════════════════════════════════════════════════╗
║                  🎯 BerkshireNexus Executive Investment Memo: Uber Technologies, Inc.        ║
╚══════════════════════════════════════════════════════════════════════════════════════════════╝
Ticker: UBER | Price: $79.29 | P/E: 17.4x | EPS: $4.56 | Beta: 1.16 | Sector: Internet / Mobility

┌── 📊 Multi-Framework Synthesis Scorecard ──────────────────────────────────────────────────┐
│ 1. Serenity Chokepoint (瓶颈) : Level 4/5 (8.5/10) - Global Mobility & Dispatch Network    │
│ 2. Berkshire 4 Masters (大师) : 4.62/5.0 - STRONG BUY                                      │
│ 3. Graham / DCF Valuation (估值) : MoS +16.9% (Intrinsic: $95.37) - Fairly Valued           │
│ 4. Qlib Multi-Factor Alpha (量化): 64.6/100 (Q:64.6 V:76.8 G:51.4 M:67.4)                  │
│ 5. Final BerkshireNexus Score: 79.3 / 100 ──► BUY / ACCUMULATE (Positive Asymmetry)        │
│ 6. Risk & Position Sizing    : Max Allocation 25.0% (Core Fortress Pillar)                 │
└────────────────────────────────────────────────────────────────────────────────────────────┘

🔍 段永平 5 句话镜子测试 (5-Sentence Mirror Test):
  • 1. Uber is the dominant global platform for moving people and food.
  • 2. Millions of drivers and riders create an insurmountable 2-sided network moat.
  • 3. The business has flipped into a $6B+ annual free cash flow machine.
  • 4. Autonomous vehicles need Uber's dispatch network to find paying riders.
  • 5. Trading at an attractive P/E (<18x) relative to its 15-20% compounding growth rate.

💀 查理·芒格 逆向思考 (Munger Inversion - 什么情况会让它死?):
  Tesla or Waymo successfully building an independent consumer ride-hailing app with zero commission...

🏛️ Investor Masters Boardroom Debate (6 大师视角对抗):
─────────────────────────────────────────────────────────────────────────────────────────────
  Warren Buffett     [Durable Moat & Owner Earnings  ] Score: 4.6 | Verdict: BUY
    Thesis: Uber operates the quintessential asset-light platform network. Dominant market share, pricing power, and FCF inflection ($6B+) at P/E under 18x.
    Concern: Potential platform transition risks if autonomous driving fleets bypass third-party dispatchers.
  Bill Ackman        [Activist Value & Compounder   ] Score: 4.9 | Verdict: STRONG BUY
    Thesis: Classic Ackman compounder: Dominant market share, high barriers to entry, pricing power, expanding advertising margin, and massive share buybacks.
    Concern: Wage inflation and local municipal regulations.
─────────────────────────────────────────────────────────────────────────────────────────────

🛑 Risk Manager Execution Mandate (风控执行红线):
  • 建议持仓上限: 25.0% | 动态止损线: -20.0%
  • 一票否决/离场触发条件:
    - Tesla Robotaxi vertical integration risk if Tesla scales standalone app successfully
    - Regulatory gig-worker classification and wage pressures
    - Quarterly Gross Margin dropping by >300 bps consecutively
```

---

## 📂 深度实战案例库 (Examples)

我们使用真实市场数据，对 5 大代表性风格资产进行了深度解剖，报告已完整归档在 `examples/` 目录下：

| 案例报告文件 | 核心标的 | 资产类型与定位 | 核心逻辑亮点 |
| :--- | :--- | :--- | :--- |
| [**01. 台积电深度研报**](examples/01_tsm_chokepoint_analysis.md) | `TSM` | **Level 5 唯一物理制造收费站** | 3nm/2nm >90% 绝对垄断，宁买 24x 代工也不追 45x 芯片设计 |
| [**02. 优步深度研报**](examples/02_uber_network_moat_analysis.md) | `UBER` | **双边网络垄断与 $60亿现金流** | 从烧钱到高盈利质变，自动驾驶时代不可替代的分发调度平台 |
| [**03. AppLovin 深度研报**](examples/03_applovin_high_beta_satellite.md) | `APP` | **AI 广告算法印钞机 (5%卫星仓)** | AXON 2.0 变现效率极高，但上游受制于苹果/谷歌，严格限仓 5% |
| [**04. Adobe 深度研报**](examples/04_adobe_value_trap_or_deep_value.md) | `ADBE` | **15.8x 深度价值 vs AI 颠覆** | 88% 极高毛利遭遇生成式 AI 冲击，价值陷阱与反转拐点的真实两难 |
| [**05. SoFi 深度研报**](examples/05_sofi_redline_disqualification.md) | `SOFI` | **伪科技概念一票否决出清** | 穿透包装故事，揭露 38x 估值买 7% 低 ROE 消费贷银行的巨大陷阱 |
| [**06. 全资产横截面配置指南**](examples/06_cross_sectional_benchmark.md) | `ALL` | **全天候投资组合构建策略** | 如何将大盘底座、物理收费站、现金流防线与高弹性奇兵科学组合 |

---

## 🛠️ 项目目录与模块划分

```text
berkshire-nexus/
├── SKILL.md                 # Claude Code / Codex / Cursor Agent Skill 协议定义
├── README.md                # 中文完整文档
├── README_EN.md             # 英文文档
├── pyproject.toml           # 现代 Python 封装配置
├── requirements.txt         # 无第三方运行时依赖
├── LICENSE                  # MIT 开源许可证
├── examples/                # 预置 6 篇机构级实战分析案例与资产看板
│   ├── 01_tsm_chokepoint_analysis.md
│   ├── 02_uber_network_moat_analysis.md
│   ├── 03_applovin_high_beta_satellite.md
│   ├── 04_adobe_value_trap_or_deep_value.md
│   ├── 05_sofi_redline_disqualification.md
│   ├── 06_cross_sectional_benchmark.md
│   └── learning_observations_template.csv # 外部学习数据格式示例
└── src/
    ├── __init__.py
    ├── cli.py               # analyze / compare / paper / learn / model / preflight
    ├── agent/
    │   └── cycle.py         # 一轮研究→学习→规划→风控→模拟执行
    ├── learning/
    │   ├── features.py      # 固定值域、可复现的特征抽取
    │   ├── model.py         # 线性收益模型与时间顺序验证
    │   ├── registry.py      # Champion / Challenger 模型注册表
    │   └── store.py         # 延迟标签和训练观察持久化
    ├── trading/
    │   ├── planner.py       # 目标仓位与再平衡意图
    │   ├── risk.py          # 与模型隔离的确定性风控
    │   ├── paper.py         # 持久化模拟券商
    │   ├── binance_stocks.py # Binance Stocks 原生 SAPI 适配
    │   └── types.py         # 订单、组合、成交契约
    ├── data/
    │   └── fetcher.py       # 零鉴权实时行情与财务数据抓取器
    └── core/
        ├── chokepoint.py    # Serenity 供应链 5 级物理瓶颈与替代壁垒评分器
        ├── masters.py       # Berkshire 4 大师 + 对冲基金 6 视角对抗辩论系统
        ├── valuation.py     # Value-Investing-Agent 深度 DCF 与格雷厄姆内生价值
        ├── quant_factors.py # Qlib 微软多因子量化 Alpha 评分模型
        ├── risk_manager.py  # 仓位上限、波动率折价与逆向致死风控红线
        └── orchestrator.py  # 多智能体编排与决议备忘录生成器
```

---

## 💡 作为 Claude Code / Cursor / Codex Skill 安装

将本仓库作为 Agent Skill 直接引入你的开发环境中，随时在终端呼叫智能投研大脑：

```bash
# 复制到 Claude skills 目录
mkdir -p ~/.claude/skills/berkshire-nexus
cp SKILL.md ~/.claude/skills/berkshire-nexus/

# 在 Claude Code 中即可直接唤起
/berkshire-nexus analyze UBER
/berkshire-nexus compare TSM UBER APP ADBE SOFI
```

---

## 📜 免责声明 (Disclaimer)

*本项目（BerkshireNexus）仅供学术研究、AI 投资方法论探索及量化代码交流使用。本系统输出的任何分数、估值结果、大师辩论意见和持仓上限建议均不构成任何实质性的投资建议或证券买卖要约。模拟结果不代表未来表现；自动学习也不能消除模型风险、数据偏差、滑点、流动性或监管风险。金融市场有风险，投资需独立思考与严谨决策。*
