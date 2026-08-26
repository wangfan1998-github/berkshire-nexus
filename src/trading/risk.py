"""Non-LLM risk controls which every broker request must pass."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import FrozenSet, List

from .types import OrderIntent, PortfolioSnapshot, RiskDecision


@dataclass(frozen=True)
class RiskPolicy:
    minimum_analysis_score: float = 60.0
    max_position_pct: float = 10.0
    max_single_order_notional: float = 10_000.0
    max_daily_turnover_pct: float = 25.0
    max_daily_loss_pct: float = 1.0
    minimum_order_notional: float = 25.0
    allow_market_orders_live: bool = False
    require_verified_data_live: bool = True
    allowed_symbols: FrozenSet[str] = field(default_factory=frozenset)


class DeterministicRiskEngine:
    """Pure rule engine. It has no network, model, or credential access."""

    def __init__(self, policy: RiskPolicy):
        self.policy = policy

    def evaluate(
        self,
        order: OrderIntent,
        portfolio: PortfolioSnapshot,
        *,
        mode: str = "paper",
    ) -> RiskDecision:
        reasons: List[str] = []
        symbol = order.ticker.upper()
        equity = portfolio.equity
        price = order.limit_price or order.reference_price
        calculated_notional = order.notional or (order.quantity * price)

        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", symbol):
            reasons.append("invalid US-equity ticker format")
        if self.policy.allowed_symbols and symbol not in self.policy.allowed_symbols:
            reasons.append("symbol is not present in the configured allowlist")
        reducing_risk = order.side == "SELL"
        if not reducing_risk and order.combined_score < self.policy.minimum_analysis_score:
            reasons.append("combined conviction score is below the execution threshold")
        if calculated_notional < self.policy.minimum_order_notional:
            reasons.append("order notional is below the minimum")
        if not reducing_risk and calculated_notional > self.policy.max_single_order_notional:
            reasons.append("order notional exceeds the per-order limit")
        if equity <= 0.0:
            reasons.append("portfolio equity must be positive")

        if mode == "live":
            if not reducing_risk and self.policy.require_verified_data_live and order.uses_fallback_data:
                reasons.append("fallback or inferred analysis data cannot trigger a live order")
            if not self.policy.allow_market_orders_live and order.order_type == "MARKET":
                reasons.append("market orders are disabled for live execution")
            if order.tokenize:
                reasons.append("tokenized stock settlement is disabled by policy")

        projected_value = portfolio.position_value(symbol)
        held_quantity = float(portfolio.quantities.get(symbol, 0.0))
        if order.side == "BUY":
            projected_value += calculated_notional
            if calculated_notional > portfolio.cash:
                reasons.append("insufficient cash for buy order")
        elif order.side == "SELL":
            if order.quantity > held_quantity + 1e-9:
                reasons.append("sell quantity exceeds current holdings")
            projected_value = max(0.0, projected_value - calculated_notional)
        else:
            reasons.append("order side must be BUY or SELL")

        projected_position_pct = (projected_value / equity * 100.0) if equity > 0.0 else 100.0
        # A small percentage-point tolerance prevents commissions from making
        # an exactly-at-cap target fail after an earlier fill reduces equity.
        effective_position_cap = min(
            self.policy.max_position_pct,
            max(order.analysis_position_cap_pct, 0.0),
        )
        if not reducing_risk and projected_position_pct > effective_position_cap + 0.05:
            reasons.append("projected position exceeds the effective analysis/global cap")

        daily_loss_pct = 0.0
        if portfolio.start_of_day_equity > 0.0:
            daily_loss_pct = (portfolio.equity / portfolio.start_of_day_equity - 1.0) * 100.0
        if not reducing_risk and daily_loss_pct <= -self.policy.max_daily_loss_pct:
            reasons.append("daily loss kill switch is active")

        projected_turnover = portfolio.daily_traded_notional + calculated_notional
        max_turnover = equity * self.policy.max_daily_turnover_pct / 100.0
        if not reducing_risk and equity > 0.0 and projected_turnover > max_turnover + 1e-9:
            reasons.append("projected daily turnover exceeds the configured cap")

        return RiskDecision(
            approved=not reasons,
            reasons=reasons,
            order=order,
            calculated_notional=round(calculated_notional, 6),
            projected_position_pct=round(projected_position_pct, 4),
        )
