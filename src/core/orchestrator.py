"""OmniAlpha Orchestrator - Synthesizes Multi-Agent, Bottleneck, Valuation, & Quant Modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any
from ..data.fetcher import DataFetcher, CompanyFinancials
from .chokepoint import ChokepointAnalyzer, ChokepointResult
from .masters import MastersDebateEngine, MasterDebateResult
from .valuation import ValuationEngine, ValuationResult
from .quant_factors import QuantFactorModel, QuantFactorBreakdown
from .risk_manager import RiskManager, RiskAssessment


@dataclass
class ComprehensiveAnalysisReport:
    financials: CompanyFinancials
    chokepoint: ChokepointResult
    masters_debate: MasterDebateResult
    valuation: ValuationResult
    quant_factors: QuantFactorBreakdown
    risk_assessment: RiskAssessment
    final_composite_score: float  # 0 to 100
    overall_recommendation: str    # STRONG BUY / BUY / HOLD / AVOID


class OmniAlphaOrchestrator:
    """End-to-end orchestration pipeline for investment research."""

    def __init__(self):
        self.fetcher = DataFetcher()
        self.chokepoint_analyzer = ChokepointAnalyzer()
        self.masters_engine = MastersDebateEngine()
        self.valuation_engine = ValuationEngine()
        self.quant_model = QuantFactorModel()
        self.risk_manager = RiskManager()

    def analyze_single(self, ticker: str) -> ComprehensiveAnalysisReport:
        # 1. Fetch data
        fin = self.fetcher.fetch_quote(ticker)

        # 2. Run modules in parallel pipeline
        chokepoint = self.chokepoint_analyzer.analyze(fin)
        debate = self.masters_engine.debate(fin)
        val = self.valuation_engine.evaluate(fin)
        quant = self.quant_model.evaluate(fin)
        risk = self.risk_manager.assess(fin, chokepoint, val, quant)

        # 3. Calculate Final Composite Score (0-100)
        # Weights:
        # - Chokepoint Level & Score: 25% (Serenity)
        # - Masters Consensus: 25% (Berkshire)
        # - Valuation Margin of Safety: 25% (Value-Investing-Agent)
        # - Quant Multi-Factor: 25% (Qlib)
        choke_scaled = chokepoint.overall_score * 10.0
        masters_scaled = debate.consensus_score * 20.0
        val_scaled = min(max(50.0 + (val.margin_of_safety_pct * 1.5), 10.0), 95.0)
        quant_scaled = quant.composite_alpha_score

        final_score = round(
            choke_scaled * 0.25 +
            masters_scaled * 0.25 +
            val_scaled * 0.25 +
            quant_scaled * 0.25,
            1
        )

        if final_score >= 80.0:
            rec = "STRONG BUY (Top Tier Conviction)"
        elif final_score >= 68.0:
            rec = "BUY / ACCUMULATE (Positive Asymmetry)"
        elif final_score >= 55.0:
            rec = "HOLD / WATCHLIST (Neutral Risk/Reward)"
        else:
            rec = "AVOID / DISQUALIFIED (Unfavorable Profile)"

        return ComprehensiveAnalysisReport(
            financials=fin,
            chokepoint=chokepoint,
            masters_debate=debate,
            valuation=val,
            quant_factors=quant,
            risk_assessment=risk,
            final_composite_score=final_score,
            overall_recommendation=rec
        )

    def compare_multiple(self, tickers: List[str]) -> List[ComprehensiveAnalysisReport]:
        reports = [self.analyze_single(t) for t in tickers]
        # Sort descending by final composite score
        reports.sort(key=lambda r: r.final_composite_score, reverse=True)
        return reports
