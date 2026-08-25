"""Qlib-Style Multi-Factor Quantitative Alpha Scoring Model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List
from ..data.fetcher import CompanyFinancials


@dataclass
class QuantFactorBreakdown:
    quality_score: float  # 0 to 100 (ROE, margins, balance sheet health)
    value_score: float    # 0 to 100 (Earnings yield, FCF yield, P/E relative)
    growth_score: float   # 0 to 100 (Revenue growth, earnings momentum)
    momentum_score: float # 0 to 100 (Trend strength, price action)
    risk_adjusted_score: float # 0 to 100 (Beta penalty, stability)
    composite_alpha_score: float # 0 to 100 Final Multi-Factor Score
    factor_strengths: List[str] = field(default_factory=list)
    factor_weaknesses: List[str] = field(default_factory=list)


class QuantFactorModel:
    """Computes cross-sectional multi-factor quantitative scores based on Qlib methodologies."""

    def evaluate(self, d: CompanyFinancials) -> QuantFactorBreakdown:
        # 1. Quality Factor (0 - 100)
        # Higher ROE, higher Operating Margin, lower Debt/Equity
        roe_comp = min(max(d.roe / 0.30, 0.0), 1.0) * 40
        op_comp = min(max(d.operating_margin / 0.40, 0.0), 1.0) * 35
        debt_comp = max(1.0 - min(d.debt_to_equity / 2.0, 1.0), 0.0) * 25
        quality = round(roe_comp + op_comp + debt_comp, 1)

        # 2. Value Factor (0 - 100)
        # Lower P/E, higher FCF yield
        pe_val = min(max((45.0 - d.pe) / 35.0, 0.0), 1.0) * 55
        fcf_val = min(max(d.fcf_yield / 0.07, 0.0), 1.0) * 45
        value = round(pe_val + fcf_val, 1)

        # 3. Growth Factor (0 - 100)
        # Higher Revenue growth
        growth = round(min(max(d.revenue_growth_yoy / 0.35, 0.0), 1.0) * 100, 1)

        # 4. Momentum Factor (0 - 100)
        # Growth * Beta adjusted trend
        base_mom = 50.0 + (d.revenue_growth_yoy * 100) - (abs(d.beta - 1.2) * 15)
        momentum = round(min(max(base_mom, 15.0), 95.0), 1)

        # 5. Risk / Low Volatility Factor (0 - 100)
        # Lower Beta gets higher score
        risk_score = round(max(100.0 - (d.beta * 32.0), 10.0), 1)

        # Composite Alpha Score: Quality (25%), Value (25%), Growth (25%), Momentum (15%), Risk (10%)
        composite = round(
            quality * 0.25 +
            value * 0.25 +
            growth * 0.25 +
            momentum * 0.15 +
            risk_score * 0.10,
            1
        )

        strengths = []
        weaknesses = []

        if quality >= 75:
            strengths.append(f"Outstanding Balance Sheet & Margin Quality ({quality}/100)")
        elif quality <= 45:
            weaknesses.append(f"Low Return on Equity / High Debt Burden ({quality}/100)")

        if value >= 70:
            strengths.append(f"Attractive Valuation Multiples & FCF Yield ({value}/100)")
        elif value <= 40:
            weaknesses.append(f"Rich Valuation Multiple / Low Yield ({value}/100)")

        if growth >= 75:
            strengths.append(f"High-Decibel Growth Velocity ({growth}/100)")
        elif growth <= 40:
            weaknesses.append(f"Maturing or Subdued Top-Line Growth ({growth}/100)")

        if risk_score <= 35:
            weaknesses.append(f"Elevated Beta / High Volatility Profile (Beta: {d.beta})")
        elif risk_score >= 65:
            strengths.append(f"Defensive Low-Beta Price Stability (Beta: {d.beta})")

        return QuantFactorBreakdown(
            quality_score=quality,
            value_score=value,
            growth_score=growth,
            momentum_score=momentum,
            risk_adjusted_score=risk_score,
            composite_alpha_score=composite,
            factor_strengths=strengths,
            factor_weaknesses=weaknesses
        )
