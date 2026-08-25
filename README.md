# BerkshireNexus 🎯

> **集大成者**：融合 **Serenity 产业链物理瓶颈** + **Berkshire 价值四大师** + **Qlib 微软多因子量化** + **AI Hedge Fund 多智能体辩论** 的机构级 AI 投研决策框架。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)
[![Zero Dependency](https://img.shields.io/badge/Dependencies-Zero%20External-orange.svg)](pyproject.toml)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-black)](SKILL.md)
[![中文优先](https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E4%BC%98%E5%85%88-red)](README.md)
[![English](https://img.shields.io/badge/English-README__EN.md-lightgrey)](README_EN.md)

---

## 🌟 为什么需要 BerkshireNexus？

直接问普通的通用 AI（ChatGPT / Claude）：“某某股票值不值得买？”，你通常只会得到一份**“一方面……另一方面……投资有风险，请自行判断”**的两头讨好套话。

**这种分析看似全面，但在真实真金白银的交易中没有任何决策价值。**

`BerkshireNexus` 汲取并提炼了当前 GitHub 社区最前沿的四大投研开源项目之精华：
1. **`serenity-skill`**：拆解产业链，寻找**不可替代、难以扩产的物理收费站（Chokepoint）**，拒绝纯讲故事的伪概念。
2. **`ai-berkshire`**：践行**巴菲特、芒格、段永平、李录**四大师视角，执行**“5句话镜子测试”**与**“芒格逆向致死检验”**。
3. **`danielchu97/Value-Investing-Agent`**：严谨计算**格雷厄姆数、两阶段所有者自由现金流（Owner Earnings DCF）与 5 维护城河评分**。
4. **`microsoft/qlib`**：注入**质量（Quality）、价值（Value）、成长（Growth）、动量（Momentum）、风险（Risk）**五维量化 Alpha 因子。
5. **`virattt/ai-hedge-fund`**：构建**多大师 Agent 董事会辩论**与**风控经理一票否决/仓位上限机制**。

---

## 🏛️ 框架全景架构

```
                               【候选股票池 / Tickers】
                                          │
    ┌─────────────────────────────────────┼─────────────────────────────────────┐
    ▼                                     ▼                                     ▼
【1. Serenity 物理瓶颈】            【2. Berkshire 大师董事会】           【3. Qlib 多因子量化】
• 物理不可替代度 (0-10)             • 巴菲特 (所有者收益/自由现金流)       • Quality 质量因子 (ROE/负债)
• 扩产周期与 CapEx 壁垒             • 芒格 (逆向思维: 什么会让它死?)      • Value 价值因子 (1/PE, FCF Yield)
• 5 级瓶颈定级 (Level 1~5)          • 段永平 (商业模式/5句话镜子测试)     • Growth 成长因子 (营收增速)
• 定价权与价值捕获比例              • 李录 / 阿克曼 / 木头姐 对抗辩论    • Momentum & Low-Volatility 风险
    │                                     │                                     │
    └─────────────────────────────────────┼─────────────────────────────────────┘
                                          │
                                          ▼
                      【4. Value-Investing-Agent 深度估值】
                      • 格雷厄姆成长与防御公式
                      • 两阶段自由现金流折现 (Two-Stage DCF)
                      • 安全边际测算 (Margin of Safety %)
                                          │
                                          ▼
                      【5. 对冲基金风控与仓位裁决 (Risk Manager)】
                      • 组合角色定性 (核心基石 / 物理收费站 / 进攻奇兵 / 一票否决)
                      • 动态持仓上限建议 (Max Allocation %)
                      • 离场触发红线 (Redline Inversion Triggers)
                                          │
                                          ▼
                    【📊 最终决策备忘录 (Executive Investment Memo)】
```

---

## 🚀 极速上手 (Quick Start)

本项目设计为 **零外部依赖（Zero Dependency）**，无需复杂的 `pip install`，拉取代码即可在任何安装了 Python 3.7+ 的终端中直接运行！

### 1. 单股全维度深度扫描 (`analyze`)

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
```

---

### 2. 多股票横截面横向 PK 排序 (`compare`)

输入任意多只股票代码，自动调用量化因子与大师委员会进行综合打分排序：

```bash
python3 -m src.cli compare TSM UBER APP ADBE SOFI
```

**输出示例**：
```text
╔════════════════════════════════════════════════════════════════════════════════════════════════════════════════╗
║                         🏆 BerkshireNexus Cross-Sectional Ranking & Comparison Board                       ║
╚════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝

Rank  Ticker   Company Name             Price (P/E)      Chokepoint      Masters      MoS (DCF)    Qlib Alpha   Total      Recommendation     
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
🥇 #1 UBER     Uber Technologies, Inc   $79.29 (17.4x)   L4 (8.50)       4.62/5.0     +16.9%       64.6         79.3       BUY               
🥈 #2 APP      AppLovin Corporation     $298.59 (22.9x)  L3 (6.97)       3.80/5.0     +48.7%       74.4         78.8       BUY               
🥉 #3 TSM      Taiwan Semiconductor     $205.00 (24.2x)  L5 (9.63)       4.52/5.0     -12.4%       74.2         77.8       BUY               
   #4 ADBE     Adobe Inc.               $276.27 (15.8x)  L3 (7.61)       3.43/5.0     +15.1%       65.8         70.8       BUY               
   #5 SOFI     SoFi Technologies Inc    $18.24 (38.4x)   L1 (4.23)       2.45/5.0     -86.3%       37.8         34.8       AVOID             
────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
```

---

## 🛠️ 项目目录结构

```text
berkshire-nexus/
├── SKILL.md                 # Claude Code / Codex / Cursor Agent Skill 协议定义
├── README.md                # 中文完整文档
├── README_EN.md             # 英文文档
├── pyproject.toml           # 现代 Python 封装配置
├── requirements.txt         # 依赖声明（零外部依赖）
├── LICENSE                  # MIT 开源许可证
└── src/
    ├── __init__.py
    ├── cli.py               # 终端彩色交互 CLI
    ├── data/
    │   ├── __init__.py
    │   └── fetcher.py       # 零鉴权实时行情与财务数据抓取器
    └── core/
        ├── __init__.py
        ├── chokepoint.py    # Serenity 产业链物理瓶颈与替代壁垒评分器
        ├── masters.py       # Berkshire 4 大师 + 对冲基金多智能体辩论引擎
        ├── valuation.py     # Value-Investing-Agent 深度 DCF 与格雷厄姆内生价值
        ├── quant_factors.py # Qlib 微软多因子量化 Alpha 评分模型
        ├── risk_manager.py  # 仓位上限、波动率折价与逆向否决风控
        └── orchestrator.py  # 多智能体编排与决议备忘录生成器
```

---

## 💡 作为 Claude Code / Cursor / Codex Skill 安装

将本仓库作为 Agent Skill 安装到你的开发环境中：

```bash
# 复制到 Claude skills 目录
mkdir -p ~/.claude/skills/berkshire-nexus
cp SKILL.md ~/.claude/skills/berkshire-nexus/

# 在 Claude 中即可直接唤起
/berkshire-nexus analyze UBER
```

---

## 📜 免责声明 (Disclaimer)

*本项目（BerkshireNexus）仅供学术研究、AI 投资方法论探索及代码学习交流使用。本项目生成的任何分数、分析报告、大师辩论结果及仓位建议均不构成任何实质性的投资建议、买卖要约或财务推荐。金融市场有风险，投资需独立思考与谨慎决策。*
