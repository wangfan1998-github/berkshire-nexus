"""OmniAlpha Orchestrator - Synthesizes Multi-Agent, Bottleneck, Valuation, & Quant Modules."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4
from ..data.fetcher import DataFetcher, CompanyFinancials
from .chokepoint import ChokepointAnalyzer, ChokepointResult
from .masters import MastersDebateEngine, MasterDebateResult
from .valuation import ValuationEngine, ValuationResult
from .quant_factors import QuantFactorModel, QuantFactorBreakdown
from .risk_manager import RiskManager, RiskAssessment
from ..research.ai import AIResearchResult, AIResearchService
from ..research.config import ResearchConfig
from ..research.news import NewsResult, NewsService


# Layer weights. Quality is the largest single block but no longer a majority,
# so a good business at a bad price cannot coast through on pedigree alone.
QUALITY_WEIGHT = 0.45
VALUATION_WEIGHT = 0.30
TIMING_WEIGHT = 0.25


def _valuation_score(margin_of_safety_pct: float, reliable: bool = True) -> float:
    """Map margin of safety onto 0-100 with usable resolution in the middle.

    The previous mapping was ``50 + mos * 1.5`` clamped to 10-95, which saturated
    almost immediately: on 12 live holdings, 8 pinned to a bound and the factor
    degenerated into a two-state switch. A DCF routinely produces margins beyond
    ±50%, so a linear ramp cannot also resolve the ±20% band where the actual
    decisions are made.

    tanh compresses the tails instead of clipping them, so ordering is preserved
    out at the edges. The scale is set from the observed distribution: measured
    across 10 AI-chain names the DCF spans -173% to +63%, and a /35 scale still
    pinned 4 of 10 against a bound. /60 pins none of the interior names while
    keeping the ±20% decision band ~29 points wide, which is enough resolution
    to rank two similarly-priced candidates.
    """

    if not reliable:
        # An unreliable valuation (typically an ETF, which has no issuer
        # fundamentals) must not read as attractively cheap.
        return 50.0
    scaled = math.tanh(margin_of_safety_pct / 60.0)
    return round(50.0 + scaled * 45.0, 2)


def _timing_score(momentum_score: float, news_sentiment: float) -> float:
    """Blend price momentum with news sentiment into the fast-moving layer.

    News previously carried zero weight — it was fetched, displayed, and ignored
    by the score. It is the only input that changes intraday on a day with no
    price move, so it belongs here.
    """

    sentiment_scaled = 50.0 + max(-1.0, min(1.0, news_sentiment)) * 40.0
    return momentum_score * 0.6 + sentiment_scaled * 0.4


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
    analysis_id: str
    generated_at_utc: str
    news: NewsResult
    ai_research: AIResearchResult


class OmniAlphaOrchestrator:
    """End-to-end orchestration pipeline for investment research."""

    def __init__(
        self,
        research_config: Optional[ResearchConfig] = None,
        ai_api_key: str = "",
        venue_prices: Optional[Dict[str, float]] = None,
        news_sentiment: Optional[Dict[str, float]] = None,
    ):
        self.research_config = research_config or ResearchConfig()
        self.fetcher = DataFetcher()
        # Prices from the venue the orders route to. Valuation must use the
        # price an order will actually fill at: Binance's tokenized-equity quote
        # has diverged from the third-party close by ~8% intraday, which would
        # otherwise make margin-of-safety describe a price nobody can trade.
        # Per-ticker news sentiment in -1..1, supplied by the caller because it
        # is batched across the whole shortlist in one model call.
        self.news_sentiment = {
            str(k).upper(): float(v) for k, v in (news_sentiment or {}).items()
        }
        self.venue_prices = {
            str(k).upper(): float(v) for k, v in (venue_prices or {}).items() if float(v) > 0.0
        }
        self.news_service = NewsService(self.research_config)
        self.ai_service = AIResearchService(self.research_config, ai_api_key)
        self.chokepoint_analyzer = ChokepointAnalyzer()
        self.masters_engine = MastersDebateEngine()
        self.valuation_engine = ValuationEngine()
        self.quant_model = QuantFactorModel()
        self.risk_manager = RiskManager()

    def analyze_single(self, ticker: str) -> ComprehensiveAnalysisReport:
        # 1. Fetch data
        fin = self.fetcher.fetch_quote(ticker)

        # 1b. Override with the execution venue's price before ANY scoring, so
        # valuation, quant factors and risk all reason about the tradable price.
        venue_price = self.venue_prices.get(fin.ticker.upper(), 0.0)
        if venue_price > 0.0:
            reference_close = fin.previous_close or fin.price
            fin.price = venue_price
            fin.is_authoritative = True
            if fin.eps and fin.eps > 0.0:
                fin.pe = venue_price / fin.eps
            if reference_close > 0.0:
                fin.price_change_pct = (venue_price / reference_close - 1.0) * 100.0
            fin.data_source = f"binance-equity-quote+{fin.data_source}"
            fin.source_trace = list(fin.source_trace) + [{
                "provider": "binance-equity-quote",
                "kind": "venue-price-override",
                "status": "ok",
                "as_of_utc": datetime.now(timezone.utc).isoformat(),
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "latency_ms": 0,
                "fields": ["price", "pe", "price_change_pct"],
                "message": "execution-venue price used for valuation and sizing",
            }]

        # 2. Run modules in parallel pipeline
        chokepoint = self.chokepoint_analyzer.analyze(fin)
        debate = self.masters_engine.debate(fin)
        val = self.valuation_engine.evaluate(fin)
        quant = self.quant_model.evaluate(fin)
        risk = self.risk_manager.assess(fin, chokepoint, val, quant)
        news_sentiment = self.news_sentiment.get(fin.ticker.upper(), 0.0)

        # 3. Final composite score, in three layers rather than four equal parts.
        #
        # Measured across 10 AI-chain names, the engines are not independent:
        #   masters vs qlib       +0.97
        #   chokepoint vs qlib    +0.72
        #   chokepoint vs masters +0.70
        #   valuation vs masters  +0.04
        # The first three all answer "is this a good business" from the same
        # margin/ROE inputs, so equal weights gave quality an effective 75% while
        # valuation — the only uncorrelated signal — got 25%. Grouping them into
        # one QUALITY layer stops the same evidence being counted three times.
        #
        # The layers also separate slow from fast: quality moves quarterly with
        # filings, while valuation and timing move daily. Under the old weights
        # only momentum varied day to day, at 15% of 25% = 3.75%, which is why
        # the briefing barely changed between runs.
        choke_scaled = chokepoint.overall_score * 10.0
        masters_scaled = debate.consensus_score * 20.0
        # Business quality only. The full composite bundles value and momentum,
        # which are scored as their own layers below; using it here would count
        # valuation twice and momentum twice.
        quant_scaled = quant.business_quality_score
        val_scaled = _valuation_score(val.margin_of_safety_pct, val.is_reliable)

        # masters and qlib correlate at +0.97 — they are effectively one signal,
        # so they share a single third rather than taking a third each. Otherwise
        # the same margin/ROE reading lands in the score twice under two names.
        quality_layer = (
            choke_scaled * 0.50
            + masters_scaled * 0.25
            + quant_scaled * 0.25
        )
        timing_layer = _timing_score(quant.momentum_score, news_sentiment)

        final_score = round(
            quality_layer * QUALITY_WEIGHT
            + val_scaled * VALUATION_WEIGHT
            + timing_layer * TIMING_WEIGHT,
            1,
        )

        if final_score >= 80.0:
            rec = "STRONG BUY (Top Tier Conviction)"
        elif final_score >= 68.0:
            rec = "BUY / ACCUMULATE (Positive Asymmetry)"
        elif final_score >= 55.0:
            rec = "HOLD / WATCHLIST (Neutral Risk/Reward)"
        else:
            rec = "AVOID / DISQUALIFIED (Unfavorable Profile)"

        news = self.news_service.fetch(fin.ticker, fin.name)
        ai_research = self.ai_service.synthesize(
            fin.ticker,
            {
                "company": {
                    "ticker": fin.ticker,
                    "name": fin.name,
                    "sector": fin.sector,
                    "description": fin.description,
                },
                "market_data": {
                    "price": fin.price,
                    "currency": fin.currency,
                    "previous_close": fin.previous_close,
                    "price_change_pct": fin.price_change_pct,
                    "market_status": fin.market_status,
                    "quote_as_of_utc": fin.quote_as_of_utc,
                    "fundamentals_as_of": fin.fundamentals_as_of,
                    "verification_level": fin.verification_level,
                    "fallback_fields": fin.fallback_fields,
                },
                "fundamentals": {
                    "pe": fin.pe,
                    "forward_pe": fin.forward_pe,
                    "eps": fin.eps,
                    "beta": fin.beta,
                    "market_cap": fin.market_cap,
                    "revenue_growth_yoy": fin.revenue_growth_yoy,
                    "gross_margin": fin.gross_margin,
                    "operating_margin": fin.operating_margin,
                    "fcf_yield": fin.fcf_yield,
                    "roe": fin.roe,
                    "debt_to_equity": fin.debt_to_equity,
                },
                "deterministic_analysis": {
                    "score": final_score,
                    "recommendation": rec,
                    "chokepoint": asdict(chokepoint),
                    "masters": asdict(debate),
                    "valuation": asdict(val),
                    "quant": asdict(quant),
                    "risk": asdict(risk),
                },
            },
            news.items,
        )

        return ComprehensiveAnalysisReport(
            financials=fin,
            chokepoint=chokepoint,
            masters_debate=debate,
            valuation=val,
            quant_factors=quant,
            risk_assessment=risk,
            final_composite_score=final_score,
            overall_recommendation=rec,
            analysis_id=uuid4().hex,
            generated_at_utc=datetime.now(timezone.utc).isoformat(),
            news=news,
            ai_research=ai_research,
        )

    def compare_multiple(self, tickers: List[str]) -> List[ComprehensiveAnalysisReport]:
        # Network providers dominate latency. Independent tickers are fetched
        # concurrently while all scoring/risk functions remain deterministic.
        workers = min(max(len(tickers), 1), 4)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            reports = list(executor.map(self.analyze_single, tickers))
        # Sort descending by final composite score
        reports.sort(key=lambda r: r.final_composite_score, reverse=True)
        return reports
