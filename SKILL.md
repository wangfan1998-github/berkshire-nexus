---
name: berkshire-nexus
description: Auditable US-equity research and paper-trading agent with adaptive learning, deterministic risk controls, and a gated Binance Stocks adapter.
---

# BerkshireNexus Agent Skill

An institutional-grade investment research skill for Claude Code and Codex that synthesizes:
1. **Serenity Chokepoint Framework**: Physical unreplaceability, expansion barrier, and supply chain value capture.
2. **Berkshire 4 Masters + AI Hedge Fund**: Warren Buffett, Charlie Munger, Duan Yongping, Li Lu, Bill Ackman, and Cathie Wood adversarial debate.
3. **Value-Investing-Agent**: Graham Number, 2-stage Owner Earnings DCF, 5-dimension economic moat scorer, and margin of safety formulas.
4. **Microsoft Qlib Multi-Factor Model**: Quality, Value, Growth, Momentum, and Low-Volatility quantitative scoring.
5. **Hedge Fund Risk Manager**: Position sizing limits, volatility weighting, and failure inversion redlines.
6. **Adaptive Paper Agent**: Delayed return labels, chronological model validation, champion/challenger governance, target-weight planning, deterministic controls, and persistent audit logs.

## How to Run

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
- Keep `tokenize=false`; this integration targets direct equities only.
- Do not claim a Binance Stocks testnet exists.
- Live order construction requires both the explicit client flag and the real-money acknowledgement environment variable.
- This release does not expose live autonomous execution because authoritative account reconciliation is not implemented.
- Model auto-promotion is paper-only and opt-in; otherwise require explicit operator promotion.

## Supported Universe
- Any US stock ticker (e.g. `TSM`, `UBER`, `APP`, `ADBE`, `SOFI`, `GOOGL`, `AVGO`, `NVDA`, `AAPL`, `MSFT`)
- Automatically fetches quotes and metrics with local fallback interpolation.
- Local fallback/interpolated fundamentals are marked and are unsuitable for unattended live buys.
