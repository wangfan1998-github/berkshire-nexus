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
            reasons.append("标的代码格式不合法")
        if self.policy.allowed_symbols and symbol not in self.policy.allowed_symbols:
            reasons.append("标的不在允许清单内")
        reducing_risk = order.side == "SELL"
        if not reducing_risk and order.combined_score < self.policy.minimum_analysis_score:
            reasons.append(f"综合评分 {order.combined_score:.1f} 低于执行门槛 {self.policy.minimum_analysis_score:.0f}")
        if calculated_notional < self.policy.minimum_order_notional:
            reasons.append(f"订单金额 {calculated_notional:.2f} 低于最小下单额 {self.policy.minimum_order_notional:.0f}")
        if not reducing_risk and calculated_notional > self.policy.max_single_order_notional:
            reasons.append(f"订单金额 {calculated_notional:.2f} 超过单笔上限 {self.policy.max_single_order_notional:.0f}（可在设置页调整）")
        if equity <= 0.0:
            reasons.append("组合权益必须为正，无法计算仓位")

        if mode == "live":
            if not reducing_risk and self.policy.require_verified_data_live and order.uses_fallback_data:
                reasons.append("分析数据来自回退/推断值，不能触发实盘下单")
            if (
                not reducing_risk
                and self.policy.require_verified_data_live
                and not order.data_is_authoritative
            ):
                reasons.append("价格非券商权威来源，实盘拒绝执行")
            if not self.policy.allow_market_orders_live and order.order_type == "MARKET":
                reasons.append("实盘禁用市价单")
            if order.tokenize:
                reasons.append("策略禁止代币化股票结算")

        projected_value = portfolio.position_value(symbol)
        held_quantity = float(portfolio.quantities.get(symbol, 0.0))
        if order.side == "BUY":
            projected_value += calculated_notional
            if calculated_notional > portfolio.cash:
                reasons.append(f"现金不足：需要 {calculated_notional:.2f}，可用 {portfolio.cash:.2f}")
        elif order.side == "SELL":
            if order.quantity > held_quantity + 1e-9:
                reasons.append(f"卖出数量 {order.quantity:.6f} 超过持仓 {held_quantity:.6f}")
            projected_value = max(0.0, projected_value - calculated_notional)
        else:
            reasons.append("订单方向必须是 BUY 或 SELL")

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
            reasons.append(f"当日亏损 {daily_loss_pct:.2f}% 触发熔断（阈值 -{self.policy.max_daily_loss_pct:.1f}%）")

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
