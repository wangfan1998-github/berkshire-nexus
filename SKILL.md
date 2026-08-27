---
name: berkshire-nexus
description: Current-data US-equity research and paper-trading agent with cited news, configurable AI synthesis, adaptive learning, deterministic risk, and gated Binance Stocks.
---

# BerkshireNexus Agent Skill

An institutional-grade investment research skill for Claude Code and Codex that synthesizes:
1. **Serenity Chokepoint Framework**: Physical unreplaceability, expansion barrier, and supply chain value capture.
2. **Berkshire 4 Masters + AI Hedge Fund**: Warren Buffett, Charlie Munger, Duan Yongping, Li Lu, Bill Ackman, and Cathie Wood adversarial debate.
3. **Value-Investing-Agent**: Graham Number, 2-stage Owner Earnings DCF, 5-dimension economic moat scorer, and margin of safety formulas.
4. **Microsoft Qlib Multi-Factor Model**: Quality, Value, Growth, Momentum, and Low-Volatility quantitative scoring.
5. **Hedge Fund Risk Manager**: Position sizing limits, volatility weighting, and failure inversion redlines.
6. **Adaptive Paper Agent**: Delayed return labels, chronological model validation, champion/challenger governance, target-weight planning, deterministic controls, and persistent audit logs.
7. **Current Evidence Layer**: Yahoo quote/history, Nasdaq fundamentals, cited Yahoo/Google news plus official SEC EDGAR filings, freshness/provenance, and explicit degradation.
8. **Optional AI Synthesis**: OpenAI-compatible, Ollama, or local Codex CLI with constrained citations and provider/model/usage audit.

## How to Run

### Desktop application

```bash
cd desktop
npm install
npm run desktop:dev

# Production bundle
npm run desktop:build
```

The desktop shell requires Node.js 20+, Rust/Cargo, and Python 3.9+. It stores Binance and AI Provider keys in separate operating-system credential entries and exposes only configured status to the webview. The browser-only `npm run dev` path uses labeled demonstration data and cannot access Keychain or manage the persistent Python Agent. Configure current-data/news behavior and optional OpenAI-compatible, Ollama, or Codex CLI synthesis under **AI 投研**.

### Python CLI

```bash
# Analyze a single stock ticker
python3 -m src.cli analyze <TICKER>

# Compare and rank multiple tickers
python3 -m src.cli compare <TICKER_1> <TICKER_2> <TICKER_3> ...

# Run one persistent, audited paper-trading cycle
python3 -m src.cli paper <TICKER_1> <TICKER_2> ...

# Inspect or explicitly promote the learned model
python3 -m src.cli model-status
python3 -m src.cli model-promote

# Import point-in-time labeled observations
python3 -m src.cli learn examples/learning_observations_template.csv

# Read-only Binance Stocks symbol/quote preflight (requires BINANCE_API_KEY)
python3 -m src.cli binance-preflight <TICKER_1> <TICKER_2> ...
```

## Trading Safety Contract

- Default to `paper`; never infer permission to place a live order.
- Do not expose broker credentials to an LLM or strategy component.
- Never bypass `DeterministicRiskEngine`.
- Do not use fallback or inferred research fields for live buys.
- Do not treat complete Yahoo/Nasdaq research data as broker-authoritative; `is_authoritative=false` must block live buys.
- AI summaries cannot change deterministic scores, risk rules, or order intents, and current-news claims must cite retrieved evidence IDs.
- Keep `tokenize=false`; this integration targets direct equities only.
- Do not claim a Binance Stocks testnet exists.
- Live order construction requires both the explicit client flag and the real-money acknowledgement environment variable.
- This release does not expose live autonomous execution because authoritative account reconciliation is not implemented.
- Model auto-promotion is paper-only and opt-in; otherwise require explicit operator promotion.
- The desktop Live selector must remain locked until authoritative Binance cash/holdings, restart recovery, and order reconciliation are implemented and tested.

## Supported Universe
- Any US stock ticker (e.g. `TSM`, `UBER`, `APP`, `ADBE`, `SOFI`, `GOOGL`, `AVGO`, `NVDA`, `AAPL`, `MSFT`)
- Fetches latest-available Yahoo quote/history plus Nasdaq statements, EPS, and company profiles.
- Retrieves current Yahoo Finance news and official SEC EDGAR filings with optional Google News RSS fallback; every item carries an evidence ID and source URL.
- Network and local fallback fields are marked separately. Neither third-party complete nor fallback research data is authoritative for live buys.
