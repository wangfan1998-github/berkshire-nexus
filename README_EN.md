# BerkshireNexus 🎯

> **No More Non-Committal Wishy-Washy Advice**: An institutional-grade AI investment research framework combining **Serenity Supply-Chain Chokepoints**, **Berkshire 4 Value Masters**, and **Microsoft Qlib Multi-Factor Quant Alpha**.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)
[![Zero Dependency](https://img.shields.io/badge/Dependencies-Zero%20External-orange.svg)](pyproject.toml)
[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-SKILL.md-black)](SKILL.md)
[![中文优先](https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E4%BC%98%E5%85%88-red)](README.md)
[![English](https://img.shields.io/badge/English-README__EN.md-lightgrey)](README_EN.md)

---

## 💡 Why BerkshireNexus?

Asking standard LLMs (ChatGPT / Claude) "Should I buy stock X?" almost always results in balanced, useless fluff:

> *"On one hand, Company X has massive growth opportunities in AI; on the other hand, macroeconomic uncertainties and intense competition remain... Investors should decide based on their personal risk tolerance."*

**This provides exactly ZERO decision value for managing real capital.**

In the real world, investing is a high-stakes game of trade-offs, anti-bias verification, probability, and asymmetric payoffs. You need answers to hard questions:
1. **Does the company own a physical, unreplaceability bottleneck (Chokepoint)?** (Ignore executive storytelling; look at who controls the physical capacity).
2. **Does it pass Duan Yongping's 5-Sentence Mirror Test?** (If you can't explain how it prints cash in 5 sentences, pass).
3. **Charlie Munger's Inversion Test**: In what exact catastrophic scenario does this business die?
4. **Graham & Buffett Owner Earnings (2-Stage DCF)**: Stripping away narrative hype, what is the true margin of safety based on free cash flows?
5. **Hedge Fund Risk Sizing**: What is the maximum portfolio allocation cap? When is the stop-loss triggered?

`BerkshireNexus` synthesizes the best ideas from top open-source projects (`serenity-skill`, `ai-berkshire`, `qlib`, `ai-hedge-fund`, `Value-Investing-Agent`) into an uncompromising, multi-perspective decision framework that outputs definitive conclusions.

---

## 🚀 Quick Start (Zero External Dependencies)

Run with standard Python 3.9+ (no `pip install` required):

### Audited adaptive paper-trading agent

The original research engine now feeds a bounded, testable trading loop:

```text
research → bounded features → adaptive return model → champion/challenger gate
         → target weights → deterministic risk → persistent paper broker
```

Run one cycle:

```bash
python3 -m src.cli paper AAPL MSFT NVDA --cash 100000
```

State is persisted under `.berkshire-nexus/`, including the portfolio, append-only executions, delayed learning labels, model registry, and a full JSON audit for every cycle. Snapshots use a 20-calendar-day label horizon by default. A challenger is not trained until 30 observations exist, and automatic promotion is off unless `--auto-promote-paper` is explicitly supplied.

```bash
python3 -m src.cli model-status
python3 -m src.cli model-promote
python3 -m src.cli learn examples/learning_observations_template.csv
```

The CSV template contains normalized `0..1` features and decimal forward returns. Its two example rows document the format only; they are not enough to train a model. Imported features must be point-in-time correct.

### Binance Stocks boundary

The project uses Binance's native `/sapi/v1/equity/*` API rather than CCXT. A read-only symbol/quote preflight is available:

```bash
export BINANCE_API_KEY='your-read-only-key'
python3 -m src.cli binance-preflight AAPL MSFT
```

There is intentionally no one-click live CLI yet. Safe autonomous execution still requires authoritative Binance cash/holding snapshots, order reconciliation, and restart recovery. The isolated `BinanceStocksClient` can build signed orders, but `place_order()` requires both `allow_live_orders=True` and `BERKSHIRE_NEXUS_LIVE_TRADING=I_ACKNOWLEDGE_REAL_MONEY`. It always submits direct equities with `tokenize=false`.

Every order must pass deterministic controls outside the learned model: a 10% position cap, 25% daily turnover cap, 1% daily-loss kill switch, no live market orders by default, and no live buys from fallback/inferred research data. Valid risk-reducing sells remain possible after a kill switch. Binance eligibility, regional, PDT, session, and disclaimer requirements still apply. No documented Stocks testnet is assumed, so local paper trading is the mandatory first stage.

### 1. Cross-Sectional Comparison (`compare`)

```bash
python3 -m src.cli compare TSM UBER APP ADBE SOFI
```

### 2. Single-Ticker Deep Dive Memo (`analyze`)

```bash
python3 -m src.cli analyze UBER
```

---

## 📂 Deep Case Studies (in `examples/`)

- [**01. TSMC (TSM)**](examples/01_tsm_chokepoint_analysis.md): The Ultimate Level 5 Physical Tollbooth of the AI Gold Rush.
- [**02. Uber (UBER)**](examples/02_uber_network_moat_analysis.md): Two-Sided Network Moat & $6B Annual Free Cash Flow Machine.
- [**03. AppLovin (APP)**](examples/03_applovin_high_beta_satellite.md): AI Ad Arbitrage Engine & 5% Sizing Discipline.
- [**04. Adobe (ADBE)**](examples/04_adobe_value_trap_or_deep_value.md): 15.8x Deep Value vs Generative AI Disruption Dilemma.
- [**05. SoFi (SOFI)**](examples/05_sofi_redline_disqualification.md): Disqualifying a 38x P/E Commodity Lending Business.
- [**06. Portfolio Allocation Guide**](examples/06_cross_sectional_benchmark.md): All-Weather Portfolio Construction.

---

## 📜 Disclaimer

*This project is for educational, research, and coding exploration purposes only. It does not constitute financial, investment, or legal advice. Paper results do not predict future performance, and adaptive learning does not remove data, model, execution, liquidity, or regulatory risk.*
