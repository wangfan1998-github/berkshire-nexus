"""A complete research → learn → plan → risk → paper execution cycle."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

from ..core.orchestrator import ComprehensiveAnalysisReport
from ..learning.model import TrainingRun, train_candidate
from ..learning.registry import ChampionChallengerRegistry, PromotionDecision
from ..learning.store import LearningStore
from ..trading.paper import PaperBroker
from ..trading.planner import AllocationPlanner, PlanningPolicy
from ..trading.risk import DeterministicRiskEngine, RiskPolicy
from ..trading.types import ExecutionReport, OrderIntent, PortfolioSnapshot, RiskDecision


@dataclass
class AgentCycleResult:
    generated_at_utc: str
    portfolio_before: PortfolioSnapshot
    portfolio_after: PortfolioSnapshot
    orders: List[OrderIntent]
    risk_decisions: List[RiskDecision]
    executions: List[ExecutionReport]
    settled_observations: int
    total_observations: int
    promotion: Optional[PromotionDecision]
    champion_version: Optional[str]
    snapshots_recorded: int
    audit_path: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "portfolio_before": self.portfolio_before.to_dict(),
            "portfolio_after": self.portfolio_after.to_dict(),
            "orders": [value.to_dict() for value in self.orders],
            "risk_decisions": [asdict(value) for value in self.risk_decisions],
            "executions": [value.to_dict() for value in self.executions],
            "settled_observations": self.settled_observations,
            "total_observations": self.total_observations,
            "promotion": asdict(self.promotion) if self.promotion else None,
            "champion_version": self.champion_version,
            "snapshots_recorded": self.snapshots_recorded,
            "audit_path": self.audit_path,
        }


class PaperTradingAgent:
    """Runs an autonomous cycle, but only against the local paper broker."""

    def __init__(
        self,
        state_directory: Union[Path, str],
        *,
        initial_cash: float = 100_000.0,
        planning_policy: Optional[PlanningPolicy] = None,
        risk_policy: Optional[RiskPolicy] = None,
        learning_horizon_days: int = 20,
        minimum_training_samples: int = 30,
        allow_automatic_paper_promotion: bool = False,
    ):
        self.state_directory = Path(state_directory)
        self.broker = PaperBroker(self.state_directory, initial_cash=initial_cash)
        self.planner = AllocationPlanner(planning_policy)
        self.risk_engine = DeterministicRiskEngine(risk_policy or RiskPolicy())
        self.learning_store = LearningStore(self.state_directory / "learning.json")
        self.registry = ChampionChallengerRegistry(self.state_directory / "model_registry.json")
        self.learning_horizon_days = learning_horizon_days
        self.minimum_training_samples = minimum_training_samples
        self.allow_automatic_paper_promotion = allow_automatic_paper_promotion

    def run(self, reports: Sequence[ComprehensiveAnalysisReport]) -> AgentCycleResult:
        generated_at = datetime.now(timezone.utc).isoformat()
        prices = {report.financials.ticker: report.financials.price for report in reports}
        portfolio = self.broker.snapshot(prices)
        portfolio_before = PortfolioSnapshot(**portfolio.to_dict())

        settled = self.learning_store.settle_ready(
            prices,
            horizon_days=self.learning_horizon_days,
        )
        observations = self.learning_store.observations()
        champion_artifact = self.registry.champion()
        run: Optional[TrainingRun] = train_candidate(
            observations,
            champion_artifact.model if champion_artifact else None,
            minimum_samples=self.minimum_training_samples,
        )
        promotion: Optional[PromotionDecision] = None
        if run is not None:
            promotion = self.registry.consider(
                run,
                allow_automatic_paper_promotion=self.allow_automatic_paper_promotion,
            )
            champion_artifact = self.registry.champion()

        orders = self.planner.plan(
            reports,
            portfolio,
            champion_artifact.model if champion_artifact else None,
        )
        decisions: List[RiskDecision] = []
        executions: List[ExecutionReport] = []
        for order in orders:
            decision = self.risk_engine.evaluate(order, portfolio, mode="paper")
            decisions.append(decision)
            executions.append(self.broker.execute(decision, portfolio))

        snapshots_recorded = self.learning_store.record_reports(reports)
        portfolio_after = self.broker.snapshot(prices)
        audit_path = self._write_audit(
            generated_at=generated_at,
            reports=reports,
            portfolio_before=portfolio_before,
            portfolio_after=portfolio_after,
            orders=orders,
            decisions=decisions,
            executions=executions,
            promotion=promotion,
            champion_version=champion_artifact.version if champion_artifact else None,
        )
        return AgentCycleResult(
            generated_at_utc=generated_at,
            portfolio_before=portfolio_before,
            portfolio_after=portfolio_after,
            orders=orders,
            risk_decisions=decisions,
            executions=executions,
            settled_observations=len(settled),
            total_observations=len(observations),
            promotion=promotion,
            champion_version=champion_artifact.version if champion_artifact else None,
            snapshots_recorded=snapshots_recorded,
            audit_path=str(audit_path),
        )

    def _write_audit(
        self,
        *,
        generated_at: str,
        reports: Sequence[ComprehensiveAnalysisReport],
        portfolio_before: PortfolioSnapshot,
        portfolio_after: PortfolioSnapshot,
        orders: Sequence[OrderIntent],
        decisions: Sequence[RiskDecision],
        executions: Sequence[ExecutionReport],
        promotion: Optional[PromotionDecision],
        champion_version: Optional[str],
    ) -> Path:
        audit_directory = self.state_directory / "audits"
        audit_directory.mkdir(parents=True, exist_ok=True)
        path = audit_directory / f"cycle-{generated_at.replace(':', '').replace('+', '_')}.json"
        payload = {
            "generated_at_utc": generated_at,
            "analyses": [{
                "analysis_id": report.analysis_id,
                "ticker": report.financials.ticker,
                "score": report.final_composite_score,
                "recommendation": report.overall_recommendation,
                "data_source": report.financials.data_source,
                "uses_fallback_data": report.financials.uses_fallback_data,
                "as_of_utc": report.financials.as_of_utc,
                "verification_level": report.financials.verification_level,
                "is_authoritative": report.financials.is_authoritative,
                "fallback_fields": report.financials.fallback_fields,
                "source_trace": report.financials.source_trace,
                "news": asdict(report.news),
                "ai_research": asdict(report.ai_research),
            } for report in reports],
            "portfolio_before": portfolio_before.to_dict(),
            "portfolio_after": portfolio_after.to_dict(),
            "orders": [value.to_dict() for value in orders],
            "risk_decisions": [asdict(value) for value in decisions],
            "executions": [value.to_dict() for value in executions],
            "promotion": asdict(promotion) if promotion else None,
            "champion_version": champion_version,
        }
        temporary = path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, path)
        return path
