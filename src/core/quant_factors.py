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
    # Business-quality only: quality/growth/risk, with value and momentum
    # removed. The orchestrator scores valuation and timing as their own layers,
    # so folding them in here too would count the same evidence twice.
    business_quality_score: float = 0.0
    factor_strengths: List[str] = field(default_factory=list)
    factor_weaknesses: List[str] = field(default_factory=list)
    # Why momentum scored what it did (52-week position, chase penalty, ...).
    momentum_notes: List[str] = field(default_factory=list)


class QuantFactorModel:
    """Computes cross-sectional multi-factor quantitative scores based on Qlib methodologies."""

    # Above this single-day move, a buy is chasing rather than accumulating.
    CHASE_THRESHOLD_PCT = 4.0

    @classmethod
    def _momentum(cls, d: CompanyFinancials) -> tuple:
        """Momentum from observed price, with an explicit chase penalty.

        Returns ``(score, notes)``. Notes explain the score in the report so a
        low momentum reading is attributable rather than opaque.
        """

        notes: List[str] = []
        components: List[float] = []
        weights: List[float] = []

        # 52-week position: mid-range trends score best. Near the low is broken;
        # at the very top, most of the move is already in the price.
        low = float(d.fifty_two_week_low or 0.0)
        high = float(d.fifty_two_week_high or 0.0)
        price = float(d.price or 0.0)
        if price > 0.0 and high > low > 0.0:
            position = min(max((price - low) / (high - low), 0.0), 1.0)
            # Peak reward around 60-75% of the range; taper toward both extremes.
            if position <= 0.75:
                range_score = 30.0 + (position / 0.75) * 65.0
            else:
                range_score = 95.0 - ((position - 0.75) / 0.25) * 45.0
            components.append(range_score)
            weights.append(0.60)
            notes.append(f"52周分位 {position * 100:.0f}%")
            if position >= 0.95:
                notes.append("接近52周高点，上行空间已被大量定价")
        else:
            notes.append("缺少52周区间，动量改用基本面近似")

        # Today's move: a large single-day gain is chase risk, not momentum.
        change = float(d.price_change_pct or 0.0)
        if change != 0.0:
            if change >= cls.CHASE_THRESHOLD_PCT:
                # Penalise proportionally; a +8% day scores far below a calm one.
                chase_score = max(50.0 - (change - cls.CHASE_THRESHOLD_PCT) * 6.0, 5.0)
                notes.append(f"今日已涨 {change:+.1f}%，追高扣分")
            elif change <= -cls.CHASE_THRESHOLD_PCT:
                # A sharp drop is opportunity but also risk; keep it neutral.
                chase_score = 45.0
                notes.append(f"今日大跌 {change:+.1f}%，动量转弱")
            else:
                chase_score = 70.0 + change * 3.0
                notes.append(f"今日 {change:+.1f}%")
            components.append(min(max(chase_score, 5.0), 95.0))
            weights.append(0.25)

        # Fundamental growth as a tie-breaker only.
        growth_proxy = min(max(50.0 + d.revenue_growth_yoy * 100.0, 15.0), 95.0)
        components.append(growth_proxy)
        weights.append(0.15 if components[:-1] else 1.0)

        total_weight = sum(weights)
        score = sum(c * w for c, w in zip(components, weights)) / total_weight
        return round(min(max(score, 5.0), 95.0), 1), notes

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

        # 4. Momentum Factor (0 - 100) — real price action, not a growth proxy.
        #
        # The original formula used only revenue growth and beta, so a stock that
        # had already run hard still scored ~95. That cannot answer "it is up a
        # lot, is it still buyable?", which is exactly what sizing needs to know.
        #
        # Inputs, in order of preference:
        #  - position within the 52-week range (trend, and how much is priced in)
        #  - change versus the previous close (today's chase risk)
        #  - fundamental growth, retained as a smaller tie-breaker
        momentum, momentum_notes = self._momentum(d)

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

        # Business quality in isolation, for the orchestrator's layered score.
        # Value belongs to the valuation layer and momentum to the timing layer,
        # so both are excluded here and the remaining weights (.25/.25/.10) are
        # renormalised to sum to 1. Without this the composite drags valuation
        # and momentum into the quality layer and double-counts them.
        business_quality = round(
            (quality * 0.25 + growth * 0.25 + risk_score * 0.10) / 0.60,
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
            momentum_notes=momentum_notes,
            risk_adjusted_score=risk_score,
            composite_alpha_score=composite,
            business_quality_score=business_quality,
            factor_strengths=strengths,
            factor_weaknesses=weaknesses
        )
