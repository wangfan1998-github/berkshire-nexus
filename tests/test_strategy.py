"""Regression tests for the strategy rewrite.

Each test pins a specific failure that made the daily briefing unusable:
identical output every day, no live news, and an execution preview that
contradicted the recommendations it came from.
"""

from __future__ import annotations

import unittest
from typing import Optional
from unittest.mock import MagicMock

from src.core.gates import (
    MIN_RANKED_UNIVERSE,
    entry_block_reason,
    qualifies_on_rank,
    technical_block_reason,
    valuation_block_reason,
)
from src.core.orchestrator import rank_reports
from src.core.technicals import TechnicalSignals
from src.core import technicals as ta
from src.core.valuation import ValuationEngine
from src.data.fetcher import CompanyFinancials
from src.research.briefing import classify_action
from src.research.news import NewsService
from src.research.config import ResearchConfig
from src.trading.planner import AllocationPlanner, PlanningPolicy
from src.trading.types import PortfolioSnapshot


def _financials(**overrides) -> CompanyFinancials:
    base = dict(
        ticker="TEST",
        price=100.0,
        eps=5.0,
        beta=1.0,
        market_cap=5e11,
        revenue=1e11,
        revenue_growth_yoy=0.15,
        gross_margin=0.55,
        operating_margin=0.30,
        roe=0.25,
        shares_outstanding=1e9,
        free_cash_flow=2e10,
        net_income=2.5e10,
        shareholders_equity=1e11,
        fifty_two_week_low=70.0,
        fifty_two_week_high=130.0,
        price_change_pct=0.5,
    )
    base.update(overrides)
    return CompanyFinancials(**base)


def _report(
    ticker: str = "TEST",
    score: float = 70.0,
    *,
    mos: float = 10.0,
    reliable: bool = True,
    momentum: float = 70.0,
    change_pct: float = 0.5,
    cap: float = 10.0,
    is_etf: bool = False,
    price: float = 100.0,
    technicals: Optional[TechnicalSignals] = None,
) -> MagicMock:
    report = MagicMock()
    fin = report.financials
    fin.ticker = ticker
    fin.price = price
    fin.price_change_pct = change_pct
    fin.fifty_two_week_low = 70.0
    fin.fifty_two_week_high = 130.0
    fin.is_etf = is_etf
    fin.name = ticker
    fin.data_source = "test"
    fin.uses_fallback_data = False
    fin.is_authoritative = False
    report.valuation.margin_of_safety_pct = mos
    report.valuation.is_reliable = reliable
    report.valuation.intrinsic_value_dcf = price * (1 + mos / 100.0)
    report.quant_factors.momentum_score = momentum
    report.quant_factors.momentum_notes = ["note"]
    report.risk_assessment.recommended_max_allocation_pct = cap
    report.final_composite_score = score
    report.universe_percentile = 0.0
    report.universe_size = 0
    report.valuation_percentile = -1.0
    report.analysis_id = "id"
    # A real dataclass, never a MagicMock: an auto-created attribute would make
    # every numeric comparison in the technical gate raise TypeError.
    report.technicals = technicals if technicals is not None else TechnicalSignals(
        ticker=ticker, bars=252, technical_score=None,
    )
    return report


class ValuationNormalisationTests(unittest.TestCase):
    """The DCF must survive a capex-heavy year without producing nonsense."""

    def test_cyclical_capex_year_does_not_collapse_intrinsic_value(self):
        # Micron FY2025 shape: operating cash flow nearly cancelled by capex.
        # Trailing FCF was $1.7B against $17.5B of operating cash flow, which
        # previously produced an intrinsic value of $69 against a $959 quote.
        data = _financials(
            ticker="CYC",
            price=959.0,
            shares_outstanding=1.129e9,
            operating_cash_flow_history=[17.5e9, 8.5e9, 1.6e9, 15.2e9],
            capex_history=[-15.9e9, -8.4e9, -7.7e9, -12.1e9],
            depreciation_history=[8.4e9, 7.8e9, 7.8e9, 7.1e9],
            net_income_history=[8.5e9, 0.8e9, -5.8e9, 8.7e9],
            revenue_history=[37.4e9, 25.1e9, 15.5e9, 30.8e9],
            revenue=37.4e9,
        )
        result = ValuationEngine().evaluate(data)
        self.assertEqual(result.basis, "normalized-owner-earnings")
        self.assertGreaterEqual(result.normalization_years, 2)
        # Owner earnings strip growth capex, so the base must exceed trailing FCF.
        self.assertGreater(result.normalized_owner_earnings, 1.7e9 / 1.129e9)

    def test_margin_of_safety_is_bounded_below(self):
        """Price-normalised MoS cannot run past -100%.

        Dividing by intrinsic value was unbounded: a near-zero intrinsic produced
        -1289%, which saturated the valuation layer for most of the universe.
        """

        data = _financials(
            price=1000.0,
            shares_outstanding=1e9,
            operating_cash_flow_history=[1e9, 1e9, 1e9],
            capex_history=[-0.9e9, -0.9e9, -0.9e9],
            depreciation_history=[0.2e9, 0.2e9, 0.2e9],
            revenue_history=[5e10, 5e10, 5e10],
            revenue=5e10,
        )
        result = ValuationEngine().evaluate(data)
        self.assertGreater(result.margin_of_safety_pct, -100.0)

    def test_etf_without_fundamentals_is_flagged_unreliable(self):
        data = _financials(
            ticker="ETF", eps=0.0, free_cash_flow=0.0, net_income=0.0,
            shareholders_equity=0.0, revenue=0.0, is_etf=True,
        )
        result = ValuationEngine().evaluate(data)
        self.assertFalse(result.is_reliable)
        self.assertEqual(result.basis, "unavailable")

    def test_discount_rate_tracks_beta(self):
        engine = ValuationEngine()
        low = engine._discount_rate(_financials(beta=0.4))
        high = engine._discount_rate(_financials(beta=2.8))
        self.assertLess(low, high)
        # The high-beta semiconductor cohort must stay ordered rather than all
        # pinning against the ceiling.
        mid = engine._discount_rate(_financials(beta=2.2))
        self.assertLess(mid, high)


class RankingTests(unittest.TestCase):
    def test_percentiles_span_the_universe(self):
        reports = [_report(f"T{i}", score=50.0 + i) for i in range(10)]
        rank_reports(reports)
        by_score = sorted(reports, key=lambda r: r.final_composite_score)
        self.assertEqual(by_score[0].universe_percentile, 0.0)
        self.assertEqual(by_score[-1].universe_percentile, 100.0)
        self.assertTrue(all(r.universe_size == 10 for r in reports))

    def test_rank_entry_requires_a_real_cross_section(self):
        """Top 30% of three names is an artefact of rounding, not a signal."""

        few = [_report(f"T{i}", score=50.0 + i) for i in range(3)]
        rank_reports(few)
        self.assertFalse(any(qualifies_on_rank(r) for r in few))

        many = [_report(f"T{i}", score=50.0 + i) for i in range(MIN_RANKED_UNIVERSE)]
        rank_reports(many)
        self.assertTrue(any(qualifies_on_rank(r) for r in many))

    def test_valuation_percentile_excludes_unreliable_names(self):
        reports = [
            _report("A", score=60.0, mos=-20.0),
            _report("B", score=61.0, mos=-40.0),
            _report("C", score=62.0, reliable=False),
        ]
        rank_reports(reports)
        self.assertEqual(reports[2].valuation_percentile, -1.0)
        self.assertGreater(reports[0].valuation_percentile, reports[1].valuation_percentile)


class EntryGateTests(unittest.TestCase):
    def test_chase_blocks_a_large_single_day_gain(self):
        self.assertIn("追高", entry_block_reason(_report(change_pct=8.0)))

    def test_valuation_gate_is_relative_not_absolute(self):
        """A fixed -10% line blocked all 17 live names once the DCF was fixed."""

        report = _report(mos=-40.0)
        report.valuation_percentile = 80.0
        self.assertEqual(valuation_block_reason(report), "")

        cheap_rank_miss = _report(mos=-40.0)
        cheap_rank_miss.valuation_percentile = 5.0
        self.assertIn("分位", valuation_block_reason(cheap_rank_miss))

    def test_absolute_floor_still_catches_a_broken_dcf(self):
        report = _report(mos=-400.0)
        report.valuation_percentile = 99.0
        self.assertIn("估值不支持买入", valuation_block_reason(report))

    def test_gates_do_not_apply_fundamentals_to_an_etf(self):
        etf = _report(is_etf=True, mos=-90.0, momentum=10.0)
        etf.valuation_percentile = 1.0
        self.assertEqual(entry_block_reason(etf), "")


class TechnicalIndicatorTests(unittest.TestCase):
    """Indicator maths, pinned against the reference implementation.

    Expected values were produced by `bukosabino/ta` (pandas) on the same inputs
    and verified to floating-point equality; see the module docstring in
    `src/core/technicals.py`. These are the numbers, not just relative checks,
    because an indicator that is subtly wrong still looks plausible on a chart.
    """

    # A deterministic ramp with pullbacks — enough bars to warm up EMA129.
    @staticmethod
    def _series(n: int = 300) -> list:
        out = []
        value = 100.0
        for i in range(n):
            value *= 1.004 if i % 5 != 4 else 0.994
            out.append(round(value, 4))
        return out

    def test_ema_matches_pandas_recursion(self):
        closes = [10, 11, 10.5, 12, 13, 12.5, 14, 15, 14.2, 16]
        # pandas: Series(closes).ewm(span=5, min_periods=5, adjust=False).mean()
        expected = [
            None, None, None, None,
            11.617284, 11.911523, 12.607682, 13.405121, 13.670081, 14.446721,
        ]
        actual = ta.ema_series(closes, 5)
        self.assertEqual(len(actual), len(expected))
        for got, want in zip(actual, expected):
            if want is None:
                self.assertIsNone(got)
            else:
                self.assertAlmostEqual(got, want, places=6)

    def test_ema_warmup_returns_none_not_a_partial_value(self):
        """A half-warmed EMA129 is a different number, not a worse EMA129."""

        short = ta.ema_series(list(range(1, 50)), 129)
        self.assertTrue(all(value is None for value in short))

    def test_macd_signal_is_an_ema_of_the_macd_line(self):
        closes = self._series(120)
        line, signal, histogram = ta.macd_series(closes)
        # The signal cannot exist before the line does.
        first_line = next(i for i, v in enumerate(line) if v is not None)
        first_signal = next(i for i, v in enumerate(signal) if v is not None)
        self.assertEqual(first_signal, first_line + ta.MACD_SIGNAL - 1)
        # Histogram is line minus signal, exactly.
        self.assertAlmostEqual(histogram[-1], line[-1] - signal[-1], places=9)

    def test_rsi_is_100_when_there_are_no_losses(self):
        rising = [100.0 + i for i in range(40)]
        self.assertAlmostEqual(ta.rsi_series(rising)[-1], 100.0, places=6)

    def test_rsi_stays_within_bounds(self):
        for closes in (self._series(200), [100.0 - i * 0.5 for i in range(80)]):
            values = [v for v in ta.rsi_series(closes) if v is not None]
            self.assertTrue(values)
            self.assertTrue(all(0.0 <= v <= 100.0 for v in values))

    def test_true_range_uses_the_widest_of_three_spans(self):
        highs = [10.0, 12.0]
        lows = [9.0, 11.5]
        closes = [9.5, 11.8]
        # max(12-11.5, |12-9.5|, |11.5-9.5|) = 2.5
        self.assertAlmostEqual(ta.true_range_series(highs, lows, closes)[1], 2.5)

    def test_short_history_reports_nothing_rather_than_a_guess(self):
        signals = ta.analyse([100.0, 101.0, 102.0], ticker="NEW")
        self.assertFalse(signals.available)
        self.assertIsNone(signals.technical_score)
        self.assertTrue(any("不足以计算" in note for note in signals.notes))

    def test_bullish_stack_scores_above_bearish(self):
        rising = self._series(300)
        falling = list(reversed(rising))
        up = ta.analyse(rising, ticker="UP")
        down = ta.analyse(falling, ticker="DOWN")
        self.assertEqual(up.trend_alignment, "bullish")
        self.assertEqual(down.trend_alignment, "bearish")
        self.assertGreater(up.technical_score, down.technical_score)

    def test_flat_noise_is_not_read_as_a_bullish_trend(self):
        """A series oscillating +-0.05% ordered the EMAs and scored 80/100.

        Ordering alone is not a trend: the lines were separated by 0.01% of price.
        Requiring real separation plus deadbands on the regime line and MACD sign
        pulls this back toward neutral without touching genuine trends, which run
        a 4-18% EMA5/EMA129 spread on live data.
        """

        flat = [100.0 + (1.0 if i % 2 else -1.0) * 0.05 for i in range(300)]
        signals = ta.analyse(flat, ticker="CHOP")
        self.assertEqual(signals.trend_alignment, "mixed")
        self.assertLess(signals.technical_score, 62.0)

    def test_ordered_but_unseparated_stack_is_mixed(self):
        spread = ta.MIN_STACK_SPREAD_PCT
        self.assertEqual(ta._alignment(100.5, 100.3, 100.0, 100.0), "mixed")
        # Same ordering, now genuinely separated.
        self.assertEqual(
            ta._alignment(100.0 + spread * 2, 100.0 + spread, 100.0, 100.0),
            "bullish",
        )


class TechnicalGateTests(unittest.TestCase):
    def _signals(self, **overrides) -> TechnicalSignals:
        signals = TechnicalSignals(ticker="X", bars=252, technical_score=50.0)
        for key, value in overrides.items():
            setattr(signals, key, value)
        return signals

    def test_fresh_death_cross_below_zero_blocks_entry(self):
        report = _report(technicals=self._signals(
            macd_cross="death", macd_cross_age=1, macd_above_zero=False,
        ))
        self.assertIn("死叉", technical_block_reason(report))

    def test_stale_death_cross_does_not_block(self):
        report = _report(technicals=self._signals(
            macd_cross="death", macd_cross_age=8, macd_above_zero=False,
        ))
        self.assertEqual(technical_block_reason(report), "")

    def test_death_cross_above_zero_does_not_block(self):
        report = _report(technicals=self._signals(
            macd_cross="death", macd_cross_age=1, macd_above_zero=True,
        ))
        self.assertEqual(technical_block_reason(report), "")

    def test_bearish_stack_blocks_only_when_the_trend_is_confirmed(self):
        trending = _report(technicals=self._signals(trend_alignment="bearish", adx=30.0))
        self.assertIn("空头排列", technical_block_reason(trending))
        chopping = _report(technicals=self._signals(trend_alignment="bearish", adx=12.0))
        self.assertEqual(technical_block_reason(chopping), "")

    def test_overbought_rsi_alone_never_blocks(self):
        """Overbought in a strong uptrend is the normal state of a leader."""

        report = _report(technicals=self._signals(
            rsi=88.0, rsi_zone="overbought", trend_alignment="bullish", adx=40.0,
        ))
        self.assertEqual(technical_block_reason(report), "")

    def test_missing_technicals_fail_open(self):
        self.assertEqual(technical_block_reason(_report()), "")

    def test_etf_still_gets_the_technical_gate(self):
        """An index has no DCF, but its chart is as readable as any stock's."""

        etf = _report(is_etf=True, technicals=self._signals(
            trend_alignment="bearish", adx=32.0,
        ))
        self.assertIn("空头排列", entry_block_reason(etf))


class BriefingDecisionTests(unittest.TestCase):
    def test_top_ranked_name_can_enter_below_the_absolute_line(self):
        reports = [_report(f"T{i}", score=40.0 + i, mos=5.0) for i in range(12)]
        rank_reports(reports)
        best = max(reports, key=lambda r: r.final_composite_score)
        action, reasons = classify_action(
            best, held_quantity=0.0, weight_pct=0.0, minimum_score=60.0
        )
        self.assertEqual(action, "ADD")
        # The call must say plainly that this is relative, not a bargain.
        self.assertTrue(any("矮子里拔将军" in reason for reason in reasons))

    def test_bottom_of_the_universe_is_still_avoided(self):
        reports = [_report(f"T{i}", score=40.0 + i, mos=5.0) for i in range(12)]
        rank_reports(reports)
        worst = min(reports, key=lambda r: r.final_composite_score)
        action, _ = classify_action(
            worst, held_quantity=0.0, weight_pct=0.0, minimum_score=60.0
        )
        self.assertEqual(action, "AVOID")


class BriefingExecutionParityTests(unittest.TestCase):
    """The preview must not contradict the briefing that produced it."""

    def _portfolio(self, held):
        prices = {ticker: 100.0 for ticker in held}
        return PortfolioSnapshot(cash=5000.0, quantities=dict(held), prices=prices)

    def test_planner_applies_the_same_chase_gate_as_the_briefing(self):
        chased = _report("HOT", score=75.0, change_pct=9.0)
        rank_reports([chased])
        briefing_action, _ = classify_action(
            chased, held_quantity=0.0, weight_pct=0.0, minimum_score=60.0
        )
        self.assertEqual(briefing_action, "AVOID")

        planner = AllocationPlanner(PlanningPolicy(minimum_rebalance_notional=6.0))
        orders = planner.plan([chased], self._portfolio({}), None)
        self.assertEqual([o for o in orders if o.side == "BUY"], [])

    def test_rank_qualified_holding_is_not_bought_and_trimmed_at_once(self):
        reports = [_report(f"T{i}", score=40.0 + i, mos=5.0) for i in range(12)]
        rank_reports(reports)
        best = max(reports, key=lambda r: r.final_composite_score)
        portfolio = self._portfolio({best.financials.ticker: 5.0})
        planner = AllocationPlanner(PlanningPolicy(minimum_rebalance_notional=6.0))
        orders = planner.plan(reports, portfolio, None)
        sides = {o.ticker: o.side for o in orders}
        # It qualified on rank, so it must not be soft-trimmed as a reject.
        self.assertNotEqual(sides.get(best.financials.ticker), "SELL")

    def test_conviction_preserves_ordering_below_the_entry_line(self):
        planner = AllocationPlanner(PlanningPolicy(minimum_score=60.0))
        # Two rank-qualified names that both sit under the line must not collapse
        # onto an identical weight.
        self.assertGreater(planner._conviction(58.0), planner._conviction(45.0))


class NewsRelevanceTests(unittest.TestCase):
    def test_generic_listicle_tagged_with_many_tickers_is_rejected(self):
        service = NewsService(ResearchConfig())
        self.assertFalse(service._is_relevant(
            "NVDA",
            "If You'd Invested $5,000 in the Vanguard S&P 500 ETF a Decade Ago",
            ["NVDA", "VOO", "^GSPC"],
        ))

    def test_company_specific_story_is_kept(self):
        service = NewsService(ResearchConfig())
        self.assertTrue(service._is_relevant(
            "NVDA",
            "Nvidia Just Paused Part of Its AI Financing Machine",
            ["NVDA"],
        ))

    def test_roundup_across_many_tickers_is_rejected(self):
        service = NewsService(ResearchConfig())
        self.assertFalse(service._is_relevant(
            "NVDA",
            "Tech, Media & Telecom Roundup: Market Talk",
            ["NVDA", "AMD", "TSLA", "SPCX", "META"],
        ))


if __name__ == "__main__":
    unittest.main()
