"""Turn research reports and an optional champion model into target orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from ..core.orchestrator import ComprehensiveAnalysisReport
from ..learning.features import extract_report_features
from ..learning.model import AdaptiveLinearModel
from .types import OrderIntent, PortfolioSnapshot


@dataclass(frozen=True)
class PlanningPolicy:
    minimum_score: float = 60.0
    max_portfolio_invested_pct: float = 80.0
    global_position_cap_pct: float = 10.0
    minimum_rebalance_notional: float = 25.0
    analysis_weight: float = 0.70
    learned_weight: float = 0.30
    limit_buffer_bps: float = 10.0


class AllocationPlanner:
    def __init__(self, policy: Optional[PlanningPolicy] = None):
        self.policy = policy or PlanningPolicy()

    def plan(
        self,
        reports: Sequence[ComprehensiveAnalysisReport],
        portfolio: PortfolioSnapshot,
        champion: Optional[AdaptiveLinearModel] = None,
    ) -> List[OrderIntent]:
        scored: List[Tuple[ComprehensiveAnalysisReport, float, Optional[float]]] = []
        for report in reports:
            learned_score = champion.predict_score(extract_report_features(report)) if champion else None
            combined = report.final_composite_score
            if learned_score is not None:
                combined = (
                    report.final_composite_score * self.policy.analysis_weight
                    + learned_score * self.policy.learned_weight
                )
            if combined < self.policy.minimum_score:
                continue
            if report.risk_assessment.recommended_max_allocation_pct <= 0.0:
                continue
            scored.append((report, round(combined, 4), learned_score))

        target_weights = self._bounded_weights(scored)
        equity = portfolio.equity
        intents: List[OrderIntent] = []
        score_by_ticker = {
            report.financials.ticker: (combined_score, learned_score)
            for report, combined_score, learned_score in scored
        }
        for report in reports:
            combined_score, learned_score = score_by_ticker.get(
                report.financials.ticker,
                (report.final_composite_score, None),
            )
            ticker = report.financials.ticker
            price = report.financials.price
            if price <= 0.0:
                continue
            # Reports which fail the entry threshold get a zero target. Existing
            # positions are therefore reduced instead of being silently ignored.
            target_weight = target_weights.get(ticker, 0.0)
            target_value = equity * target_weight
            current_value = portfolio.position_value(ticker)
            difference = target_value - current_value
            if abs(difference) < self.policy.minimum_rebalance_notional:
                continue
            side = "BUY" if difference > 0.0 else "SELL"
            notional = abs(difference)
            quantity = round(notional / price, 6)
            buffer = self.policy.limit_buffer_bps / 10_000.0
            limit_price = round(price * (1.0 + buffer if side == "BUY" else 1.0 - buffer), 2)
            intents.append(OrderIntent(
                client_order_id=f"bn{uuid4().hex}",
                ticker=ticker,
                side=side,
                order_type="LIMIT",
                quantity=quantity,
                notional=round(notional, 6),
                reference_price=price,
                limit_price=limit_price,
                trading_session="RTH",
                time_in_force="DAY",
                target_weight=round(target_weight, 6),
                analysis_position_cap_pct=report.risk_assessment.recommended_max_allocation_pct,
                analysis_score=report.final_composite_score,
                learned_score=learned_score,
                combined_score=combined_score,
                analysis_id=report.analysis_id,
                data_source=report.financials.data_source,
                uses_fallback_data=report.financials.uses_fallback_data,
                data_is_authoritative=getattr(
                    report.financials, "is_authoritative", False
                ),
                tokenize=False,
                rationale=(
                    f"target {target_weight * 100:.2f}% from BerkshireNexus score "
                    f"{report.final_composite_score:.1f}"
                ),
            ))

        # Release cash from reductions before submitting buys.
        return sorted(intents, key=lambda item: 0 if item.side == "SELL" else 1)

    def _bounded_weights(
        self,
        scored: Sequence[Tuple[ComprehensiveAnalysisReport, float, Optional[float]]],
    ) -> Dict[str, float]:
        if not scored:
            return {}
        remaining = self.policy.max_portfolio_invested_pct / 100.0
        weights = {report.financials.ticker: 0.0 for report, _, _ in scored}
        active = list(scored)

        while active and remaining > 1e-12:
            conviction_sum = sum(max(score - self.policy.minimum_score, 0.01) for _, score, _ in active)
            capped_any = False
            next_active: List[Tuple[ComprehensiveAnalysisReport, float, Optional[float]]] = []
            for report, score, learned_score in active:
                ticker = report.financials.ticker
                share = remaining * max(score - self.policy.minimum_score, 0.01) / conviction_sum
                cap = min(
                    self.policy.global_position_cap_pct,
                    report.risk_assessment.recommended_max_allocation_pct,
                ) / 100.0
                capacity = max(cap - weights[ticker], 0.0)
                if share >= capacity - 1e-12:
                    weights[ticker] += capacity
                    remaining -= capacity
                    capped_any = True
                else:
                    next_active.append((report, score, learned_score))

            if not next_active:
                break
            if not capped_any:
                for report, score, _ in next_active:
                    ticker = report.financials.ticker
                    weights[ticker] += remaining * max(score - self.policy.minimum_score, 0.01) / conviction_sum
                remaining = 0.0
                break
            active = next_active
        return weights
