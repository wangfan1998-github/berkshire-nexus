# BerkshireNexus 🎯

> **No More Non-Committal Wishy-Washy Advice**: An institutional-grade AI investment research framework combining **Serenity Supply-Chain Chokepoints**, **Berkshire 4 Value Masters**, and **Microsoft Qlib Multi-Factor Quant Alpha**.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://python.org)
[![Python Core](https://img.shields.io/badge/Python%20Core-Zero%20Dependencies-orange.svg)](pyproject.toml)
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

`BerkshireNexus` synthesizes the best ideas from top open-source projects into an uncompromising, multi-perspective decision framework. v1.3 also draws architectural lessons from [`daily_stock_analysis`](https://github.com/ZhuLinsen/daily_stock_analysis) for provider/news evidence and [`ValueCell`](https://github.com/ValueCell-ai/valuecell) for model-provider settings. The implementation is a small, original, auditable layer rather than an import of either project.

---

## 🚀 Quick Start

The Python core runs on standard Python 3.9+ with no `pip install`; the desktop shell uses npm and Cargo build dependencies.

### macOS desktop app (recommended)

The desktop application uses Tauri 2, React, and TypeScript while retaining the dependency-free Python research, learning, and risk engine. It includes current Yahoo Finance quotes/history, Nasdaq fundamentals, cited Yahoo/Google news plus official SEC EDGAR filings, configurable OpenAI-compatible/Ollama/local-Codex synthesis, the paper ledger, background agent, champion/challenger registry, deterministic risk, and separate macOS Keychain slots for Binance and AI credentials.

Live mode is intentionally visible but locked. This release cannot submit a real order.

Development requires Node.js 20+, Rust/Cargo, and Python 3.9+:

```bash
git clone git@github.com:wangfan1998-github/berkshire-nexus.git
cd berkshire-nexus/desktop
npm install
npm run desktop:dev
```

Browser-only visual preview (clearly labeled demo data, no Keychain or background process):

```bash
cd desktop
npm run dev
```

Build a distributable application:

```bash
cd desktop
npm run desktop:build
```

On macOS, the app bundle is written to `desktop/src-tauri/target/release/bundle/macos/BerkshireNexus.app`, with a disk image under the adjacent `dmg/` directory. See [`PRODUCT.md`](PRODUCT.md) and [`DESIGN.md`](DESIGN.md) for the product and visual contracts.

To configure Binance, create a read-only API Key in the official Binance website or app, then open **Settings** in BerkshireNexus and store it in macOS Keychain. Do not enable trading, futures, or withdrawal permissions, and never send the key through chat, screenshots, issues, or committed files. Account setup, identity verification, Stocks eligibility, key creation, and permissions still happen in Binance's official UI. The desktop app can store/delete the key and run a read-only preflight.

### Current data, news, and AI providers

Open **Research**, enter tickers such as `AAPL MSFT NVDA`, and run a study. Each memo separately displays the latest available price and timestamp, fundamentals period, provider trace, fallback fields, current news with evidence IDs and original URLs, and optional AI synthesis.

Open **AI Research** to choose one of three providers:

- **OpenAI-compatible**: configure a model and base URL, then save the provider key in macOS Keychain. This works with Chat Completions-compatible OpenAI, OpenRouter, DeepSeek, and similar services.
- **Ollama**: use a local endpoint such as `http://127.0.0.1:11434`; BerkshireNexus needs no key.
- **Codex CLI**: uses the machine's existing Codex login. Every ticker launches a separate ephemeral, read-only `codex exec` request and consumes the user's Codex allowance; it does not inherit this chat.

AI is optional. Quotes and news continue to work while AI is disabled. The model only receives retrieved evidence, must cite news evidence IDs, and cannot alter deterministic scores or execution controls. Provider, model, prompt version, latency, returned token usage, citations, and errors are persisted in cycle audits.

“Current” is not treated as “broker-authoritative.” Yahoo/Nasdaq records carry source timestamps and a `third-party-complete`, `third-party-degraded`, or `offline-fallback` level. Even complete third-party records have `is_authoritative=false`, so deterministic Live risk rejects them for a real buy. Binance holdings, cash, restart recovery, and order reconciliation are still required before Live mode can unlock.

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

Every order must pass deterministic controls outside the learned model: a 10% position cap, 25% daily turnover cap, 1% daily-loss kill switch, no live market orders by default, and no live buys from fallback, inferred, or non-authoritative third-party research data. Valid risk-reducing sells remain possible after a kill switch. Binance eligibility, regional, PDT, session, and disclaimer requirements still apply. No documented Stocks testnet is assumed, so local paper trading is the mandatory first stage.

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
