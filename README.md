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

本项目采用 **零外部依赖（Zero Dependency）** 设计，无需繁琐的 `pip install` 环境配置，克隆后在任何 Python 3.7+ 终端均可直接秒级运行！

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
├── requirements.txt         # 零外部依赖声明
├── LICENSE                  # MIT 开源许可证
├── examples/                # 预置 6 篇机构级实战分析案例与资产看板
│   ├── 01_tsm_chokepoint_analysis.md
│   ├── 02_uber_network_moat_analysis.md
│   ├── 03_applovin_high_beta_satellite.md
│   ├── 04_adobe_value_trap_or_deep_value.md
│   ├── 05_sofi_redline_disqualification.md
│   └── 06_cross_sectional_benchmark.md
└── src/
    ├── __init__.py
    ├── cli.py               # 终端彩色交互 CLI（支持 analyze / compare）
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

*本项目（BerkshireNexus）仅供学术研究、AI 投资方法论探索及量化代码交流使用。本系统输出的任何分数、估值结果、大师辩论意见和持仓上限建议均不构成任何实质性的投资建议或证券买卖要约。金融市场有风险，投资需独立思考与严谨决策。*
