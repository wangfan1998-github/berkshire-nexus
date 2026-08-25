# OmniAlpha Agent 🎯

> **The Ultimate Synthesis**: An institutional-grade AI investment research framework combining **Serenity Supply-Chain Chokepoints**, **Berkshire 4 Value Masters**, **Microsoft Qlib Multi-Factor Quant Alpha**, and **Multi-Agent Hedge Fund Boardroom Debate**.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)
[![Zero Dependency](https://img.shields.io/badge/Dependencies-Zero%20External-orange.svg)](pyproject.toml)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-black)](SKILL.md)
[![中文优先](https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E4%BC%98%E5%85%88-red)](README.md)
[![English](https://img.shields.io/badge/English-README__EN.md-lightgrey)](README_EN.md)

---

## 🌟 Why OmniAlpha?

Asking general LLMs "Should I buy stock X?" typically yields balanced, wishy-washy non-answers ending in "Invest at your own risk." **This provides zero actionable decision value for real capital.**

`OmniAlpha` synthesizes and elevates the essence of the top open-source quantitative and value investing frameworks:
1. **`serenity-skill`**: Physical supply chain bottlenecks (**Chokepoints**) and expansion barriers.
2. **`ai-berkshire`**: 4 Masters (**Buffett, Munger, Duan Yongping, Li Lu**) with **5-Sentence Mirror Tests** and **Munger Inversion**.
3. **`danielchu97/Value-Investing-Agent`**: Graham Numbers, **Two-Stage Owner Earnings DCF**, and 5-Dimension Moat Scoring.
4. **`microsoft/qlib`**: Cross-sectional quantitative alpha models (**Quality, Value, Growth, Momentum, Low-Volatility Risk**).
5. **`virattt/ai-hedge-fund`**: Multi-master boardroom debate & strict **Risk Manager position sizing / failure redlines**.

---

## 🏛️ Architecture

```
                                 【 Candidate Tickers 】
                                          │
    ┌─────────────────────────────────────┼─────────────────────────────────────┐
    ▼                                     ▼                                     ▼
【1. Serenity Chokepoint】         【2. Berkshire Masters Board】         【3. Qlib Multi-Factor Quant】
• Physical Unreplaceability (0-10)  • Warren Buffett (Owner Earnings/ROE) • Quality (ROE, Margins, Debt)
• CapEx & Expansion Barriers        • Charlie Munger (Inversion to Death) • Value (1/PE, FCF Yield)
• 5-Tier Bottleneck Rating          • Duan Yongping (5-Sentence Mirror)   • Growth (YoY Top-Line Velocity)
• Pricing Power & Value Capture     • Li Lu / Ackman / Wood Debate        • Momentum & Low-Volatility Risk
    │                                     │                                     │
    └─────────────────────────────────────┼─────────────────────────────────────┘
                                          │
                                          ▼
                      【4. Value-Investing Intrinsic DCF】
                      • Graham Growth & Defensive Formulas
                      • Two-Stage Free Cash Flow Discounting
                      • Margin of Safety (MoS %)
                                          │
                                          ▼
                      【5. Hedge Fund Risk Manager】
                      • Portfolio Role Categorization
                      • Maximum Allocation Cap (%)
                      • Inversion Failure Redlines
                                          │
                                          ▼
                    【 📊 Executive Investment Memo Output 】
```

---

## 🚀 Quick Start

**Zero external dependencies required.** Run instantly with standard Python 3.7+:

### 1. Single Ticker Deep Analysis (`analyze`)

```bash
python3 -m src.cli analyze UBER
```

### 2. Multi-Ticker Cross-Sectional Ranking (`compare`)

```bash
python3 -m src.cli compare TSM UBER APP ADBE SOFI
```

---

## 📜 Disclaimer

*This project is for educational, research, and coding exploration purposes only. It does not constitute investment advice, financial planning, or a solicitation to buy or sell securities.*
