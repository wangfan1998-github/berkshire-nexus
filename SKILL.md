---
name: omni-alpha
description: Institutional-grade Multi-Agent & Quantitative Investment Research Framework combining Berkshire Value Masters, Serenity Supply-Chain Chokepoints, and Qlib Multi-Factor Alpha.
---

# OmniAlpha Agent Skill

An institutional-grade investment research skill for Claude Code and Codex that synthesizes:
1. **Serenity Chokepoint Framework**: Physical unreplaceability, expansion barrier, and supply chain value capture.
2. **Berkshire 4 Masters + AI Hedge Fund**: Warren Buffett, Charlie Munger, Duan Yongping, Li Lu, Bill Ackman, and Cathie Wood adversarial debate.
3. **Value-Investing-Agent**: Graham Number, 2-stage Owner Earnings DCF, 5-dimension economic moat scorer, and margin of safety formulas.
4. **Microsoft Qlib Multi-Factor Model**: Quality, Value, Growth, Momentum, and Low-Volatility quantitative scoring.
5. **Hedge Fund Risk Manager**: Position sizing limits, volatility weighting, and failure inversion redlines.

## How to Run

```bash
# Analyze a single stock ticker
python3 -m src.cli analyze <TICKER>

# Compare and rank multiple tickers
python3 -m src.cli compare <TICKER_1> <TICKER_2> <TICKER_3> ...
```

## Supported Universe
- Any US stock ticker (e.g. `TSM`, `UBER`, `APP`, `ADBE`, `SOFI`, `GOOGL`, `AVGO`, `NVDA`, `AAPL`, `MSFT`)
- Automatically fetches quotes and metrics with local fallback interpolation.
