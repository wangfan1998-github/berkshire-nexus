"""Hedge Fund Risk Manager, Position Sizing, & Failure Redline Monitor."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, List
from ..data.fetcher import CompanyFinancials
from .chokepoint import ChokepointResult
from .valuation import ValuationResult
from .quant_factors import QuantFactorBreakdown


@dataclass
class RiskAssessment:
    ticker: str
    portfolio_role: str
    recommended_max_allocation_pct: float
    risk_level: str  # Low / Medium / High / Extreme
    stop_loss_trigger_pct: float
    redline_failure_criteria: List[str] = field(default_factory=list)
    position_sizing_rationale: str = ""


class RiskManager:
    """Calculates risk-adjusted allocation caps and defines strict stop-loss and redline rules."""

    def assess(
        self,
        d: CompanyFinancials,
        chokepoint: ChokepointResult,
        val: ValuationResult,
        quant: QuantFactorBreakdown
    ) -> RiskAssessment:
        sym = d.ticker.upper()

        # 1. Redline Check
        if chokepoint.chokepoint_level <= 1 and val.margin_of_safety_pct < 0:
            return RiskAssessment(
                ticker=sym,
                portfolio_role="DISQUALIFIED / DO NOT BUY",
                recommended_max_allocation_pct=0.0,
                risk_level="Extreme Risk",
                stop_loss_trigger_pct=-8.0,
                redline_failure_criteria=[
                    "Lack of durable economic moat and zero physical bottleneck protection",
                    "Negative margin of safety combined with commodity financial products"
                ],
                position_sizing_rationale="Failed core moat and margin of safety threshold. Capital preservation rule #1 applies."
            )

        # 2. Determine Role & Allocation
        if chokepoint.chokepoint_level >= 4 and val.moat_analysis.composite_moat_score >= 8.0:
            if d.beta <= 1.35 and val.margin_of_safety_pct >= 10.0:
                role = "Core Fortress Pillar (核心压舱石 / 顶级基石)"
                max_alloc = 25.0
                risk_lvl = "Low-to-Medium Risk"
                stop_loss = -20.0
            else:
                role = "Infrastructure Alpha (物理收费站 / 核心进攻)"
                max_alloc = 15.0
                risk_lvl = "Medium Risk"
                stop_loss = -15.0
        elif d.beta >= 2.0 or chokepoint.chokepoint_level <= 3:
            role = "High-Beta Satellite (高弹性进攻奇兵 / 卫星仓)"
            max_alloc = 6.0
            risk_lvl = "High Volatility"
            stop_loss = -12.0
        else:
            role = "Tactical Value / Defense (防御性价值 / 稳健配角)"
            max_alloc = 10.0
            risk_lvl = "Medium Risk"
            stop_loss = -12.0

        # Adjust for volatility penalty
        if d.beta > 2.0:
            max_alloc = min(max_alloc, 6.0)

        # Failure triggers
        redlines = []
        if chokepoint.threat_matrix:
            redlines.extend(chokepoint.threat_matrix)
        redlines.append("Quarterly Gross Margin dropping by >300 bps consecutively")
        redlines.append("Break of 200-day moving average combined with loss of core customer share")

        return RiskAssessment(
            ticker=sym,
            portfolio_role=role,
            recommended_max_allocation_pct=max_alloc,
            risk_level=risk_lvl,
            stop_loss_trigger_pct=stop_loss,
            redline_failure_criteria=redlines,
            position_sizing_rationale=f"Assigned {max_alloc:.1f}% max weight based on Moat Score ({val.moat_analysis.composite_moat_score}/10), Beta ({d.beta}), and Chokepoint Level ({chokepoint.chokepoint_level})."
        )
