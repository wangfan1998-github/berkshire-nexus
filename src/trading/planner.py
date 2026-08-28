"""Turn research reports and an optional champion model into target orders."""

from __future__ import annotations

import math
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
    # Below the entry line a name is not worth *adding to*, which is not the same
    # as being worth liquidating. Scores between `exit_score` and `minimum_score`
    # are trimmed toward `soft_trim_retain` of the current position; only a score
    # under `exit_score` is fully exited. Previously any sub-threshold score set
    # the target weight to zero, so a 3.12%-weight position well inside its cap
    # was sold in full purely for scoring 51.
    exit_score: float = 40.0
    soft_trim_retain: float = 0.5
    # Cap how much of the book one cycle may turn over, so a broad scoring shift
    # cannot trigger a wholesale reshuffle in a single run.
    max_cycle_turnover_pct: float = 15.0
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

        # Held names that failed the entry test still need a target: keep part of
        # the position unless the score has genuinely broken down.
        soft_targets: Dict[str, float] = {}
        equity_for_soft = portfolio.equity
        for report in reports:
            ticker = report.financials.ticker
            held_value = portfolio.position_value(ticker)
            if held_value <= 0.0 or equity_for_soft <= 0.0:
                continue
            score = report.final_composite_score
            if score >= self.policy.minimum_score:
                continue
            current_weight = held_value / equity_for_soft
            if score < self.policy.exit_score:
                continue  # full exit: leave the target at zero
            soft_targets[ticker] = current_weight * self.policy.soft_trim_retain

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
            # Entry-eligible names take their bounded weight; held names that
            # merely lost conviction take a partial target; only a broken-down
            # score falls through to zero.
            target_weight = target_weights.get(ticker, soft_targets.get(ticker, 0.0))
            target_value = equity * target_weight
            current_value = portfolio.position_value(ticker)
            difference = target_value - current_value
            if abs(difference) < self.policy.minimum_rebalance_notional:
                continue
            side = "BUY" if difference > 0.0 else "SELL"
            notional = abs(difference)
            quantity = round(notional / price, 6)
            if side == "SELL":
                # Rounding to 6dp can land above the real holding, which has more
                # precision (held 1.0718605 -> planned 1.071861, i.e. 5e-7 too
                # many shares). That exceeded the risk engine's 1e-9 tolerance and
                # rejected a legitimate full exit. Never plan to sell more than is
                # actually held; truncate rather than round.
                held = float(portfolio.quantities.get(ticker, 0.0))
                if quantity > held:
                    quantity = math.floor(held * 1e6) / 1e6
                if quantity <= 0.0:
                    continue
                notional = quantity * price
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
        ordered = sorted(intents, key=lambda item: 0 if item.side == "SELL" else 1)
        return self._cap_turnover(ordered, portfolio)

    def _cap_turnover(
        self,
        intents: List[OrderIntent],
        portfolio: PortfolioSnapshot,
    ) -> List[OrderIntent]:
        """Drop the least-conviction orders once the cycle turnover cap is hit.

        A single scoring shift should not be able to reshape the whole book in one
        run; without this, a batch of sub-threshold scores produced ~28% turnover.
        """

        equity = portfolio.equity
        if equity <= 0.0 or self.policy.max_cycle_turnover_pct <= 0.0:
            return intents
        budget = equity * self.policy.max_cycle_turnover_pct / 100.0
        kept: List[OrderIntent] = []
        spent = 0.0
        # Sells first (they fund buys), then by conviction within each side.
        for intent in sorted(
            intents,
            key=lambda item: (0 if item.side == "SELL" else 1, -item.combined_score),
        ):
            if spent + intent.notional > budget:
                continue
            kept.append(intent)
            spent += intent.notional
        return sorted(kept, key=lambda item: 0 if item.side == "SELL" else 1)

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
