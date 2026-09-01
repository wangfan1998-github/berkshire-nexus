"""Value Investing & Intrinsic Valuation Engine (Graham, Buffett Owner Earnings, DCF)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Sequence
from ..data.fetcher import CompanyFinancials


@dataclass
class MoatDimensions:
    brand_intangibles: float  # 0 to 10
    cost_advantage: float     # 0 to 10
    network_effects: float    # 0 to 10
    switching_costs: float    # 0 to 10
    economies_of_scale: float # 0 to 10
    composite_moat_score: float # 0 to 10
    moat_rating: str  # Wide Moat / Narrow Moat / No Moat


@dataclass
class ValuationResult:
    ticker: str
    current_price: float
    intrinsic_value_dcf: float
    graham_number: float
    graham_growth_value: float
    margin_of_safety_pct: float
    valuation_status: str  # Significantly Undervalued / Fairly Valued / Overvalued
    moat_analysis: MoatDimensions
    dcf_assumptions: Dict[str, Any] = field(default_factory=dict)
    # Whether intrinsic value came from normalised absolute cash flows
    # (trustworthy) or a single distorted year (not usable as a cheapness signal).
    basis: str = "normalized-owner-earnings"
    is_reliable: bool = True
    notes: List[str] = field(default_factory=list)
    # Normalisation detail, surfaced so a valuation is auditable rather than a
    # bare number: how many years fed the average and what they produced.
    normalization_years: int = 0
    normalized_owner_earnings: float = 0.0


class ValuationEngine:
    """Intrinsic value from Graham formulas, a 2-stage DCF, and moat analysis.

    Two properties this engine must preserve, both learned from failures:

    **1. Intrinsic value never derives from price.** An earlier version started
    the DCF from ``price * fcf_yield``, so intrinsic value scaled linearly with
    the quote and margin-of-safety was a constant per company. Verified: prices
    100/150/300 all returned MoS -18.29%.

    **2. The cash-flow base is normalised across the cycle.** Using a single
    trailing year replaced one bug with another. Micron's FY2025 capex ($15.9B)
    nearly cancelled operating cash flow ($17.5B), leaving FCF of $1.7B and an
    intrinsic value of $69 against a $959 quote — a -1289% margin of safety that
    described an accounting artefact, not an expensive stock. Measured across 8
    AI-chain names, 6 produced margins beyond -100% and saturated the score.

    Owner earnings (operating cash flow minus *maintenance* capex, approximated
    by depreciation) is the Buffett construction and is far stabler than FCF for
    any company in a build-out: growth capex is an investment, not a cost of
    keeping the current earnings stream alive.
    """

    def __init__(
        self,
        equity_risk_premium: float = 0.045,
        terminal_growth: float = 0.025,
        risk_free_rate: float = 0.045,
    ):
        self.equity_risk_premium = equity_risk_premium
        self.terminal_growth = terminal_growth
        self.risk_free_rate = risk_free_rate

    # ------------------------------------------------------------------
    # Discount rate
    # ------------------------------------------------------------------

    def _discount_rate(self, d: CompanyFinancials) -> float:
        """CAPM cost of equity on a Blume-adjusted beta, bounded to a sane band.

        A single fixed WACC charged a utility the same rate as a 2.5-beta
        semiconductor. Beta is already fetched, so the risk premium can vary with
        the risk actually being taken.

        Raw beta is a noisy estimate of *future* beta and mean-reverts toward 1.0,
        so the standard Blume adjustment (2/3 raw + 1/3 market) is applied. Without
        it, measured live, MU/LRCX/TER/LITE all pinned against the 15% ceiling —
        replacing a saturated valuation with a saturated discount rate.
        """

        raw = min(max(float(d.beta or 1.0), 0.4), 3.0)
        adjusted = raw * (2.0 / 3.0) + (1.0 / 3.0)
        rate = self.risk_free_rate + adjusted * self.equity_risk_premium
        # Below terminal growth the Gordon denominator flips negative. The upper
        # bound sits just above what a beta-3.0 name produces (15.0%), so the cap
        # is a guard against bad beta data rather than something the ordinary
        # high-beta semiconductor cohort pins against — MU (3.38) and LRCX (3.29)
        # both cleared a 13% ceiling, which flattened them onto one rate.
        return min(max(rate, self.terminal_growth + 0.03), 0.155)

    # ------------------------------------------------------------------
    # Normalised owner earnings
    # ------------------------------------------------------------------

    @staticmethod
    def _owner_earnings_series(d: CompanyFinancials) -> List[float]:
        """Owner earnings per fiscal year, newest first.

        Owner earnings = operating cash flow - maintenance capex. Depreciation is
        the standard proxy for maintenance capex; when a company spends far above
        depreciation it is buying growth, and charging that against current
        earnings understates the business.

        Maintenance capex is capped at actual capex: a company cannot be spending
        more to stand still than it spent in total.
        """

        ocf = list(d.operating_cash_flow_history or [])
        capex = list(d.capex_history or [])
        depreciation = list(d.depreciation_history or [])
        series: List[float] = []
        for index, operating in enumerate(ocf):
            # Capex is reported negative; compare magnitudes.
            spent = abs(capex[index]) if index < len(capex) else 0.0
            wear = abs(depreciation[index]) if index < len(depreciation) else spent
            maintenance = min(wear, spent) if spent > 0.0 else wear
            series.append(operating - maintenance)
        return series

    @staticmethod
    def _weighted_average(values: Sequence[float]) -> float:
        """Recency-weighted mean, newest first.

        A flat average treats a business as if it never changed; pure trailing
        treats one year as destiny. Weights decay 1.0/0.7/0.5/0.35 so the current
        regime dominates without one distorted year deciding the valuation.
        """

        weights = [1.0, 0.7, 0.5, 0.35]
        pairs = list(zip(values, weights))
        if not pairs:
            return 0.0
        total = sum(weight for _, weight in pairs)
        return sum(value * weight for value, weight in pairs) / total

    def _normalized_base(self, d: CompanyFinancials) -> tuple:
        """Return ``(per_share_base, basis, years, notes)``.

        Normalises the owner-earnings **margin** across reported years and applies
        it to *current* revenue, rather than averaging absolute dollars.

        Averaging absolute earnings silently penalises any company that grew: four
        years of NVDA includes a year at 1/8th today's revenue, and folding that
        into the base understates present earning power by ~30%. Averaging the
        margin instead separates the two questions it was conflating — "how
        profitable is this business through a cycle" (stable, worth normalising)
        and "how big is it now" (known exactly, no need to average). A cyclical
        still gets normalised, because its margin is what swings.

        Preference order, every rung strictly price-independent:
          1. normalised owner-earnings margin x current revenue
          2. normalised free-cash-flow margin x current revenue
          3. normalised net margin x current revenue
          4. single trailing year (flagged unreliable)
          5. EPS proxy (flagged unreliable)
        """

        notes: List[str] = []
        shares = float(d.shares_outstanding or 0.0)
        if shares <= 0.0:
            return 0.0, "unavailable", 0, notes

        revenue_history = list(d.revenue_history or [])
        current_revenue = float(d.revenue or 0.0)
        if current_revenue <= 0.0 and revenue_history:
            current_revenue = revenue_history[0]

        def from_margins(series: List[float], label: str) -> Optional[tuple]:
            """Weighted-average margin over paired years, applied to today's revenue."""

            span = min(len(series), len(revenue_history))
            if span < 2 or current_revenue <= 0.0:
                return None
            margins = [
                series[index] / revenue_history[index]
                for index in range(span)
                if revenue_history[index] > 0.0
            ]
            if len(margins) < 2:
                return None
            margin = self._weighted_average(margins)
            if margin <= 0.0:
                return None
            return (margin * current_revenue) / shares, label, len(margins)

        owner = self._owner_earnings_series(d)
        result = from_margins(owner, "normalized-owner-earnings")
        if result is not None:
            base, label, years = result
            if any(value <= 0.0 for value in owner[:years]):
                notes.append("归一化区间包含亏损年度，已计入平均")
            return base, label, years, notes

        ocf = list(d.operating_cash_flow_history or [])
        capex = list(d.capex_history or [])
        fcf_series = [
            operating - (abs(capex[index]) if index < len(capex) else 0.0)
            for index, operating in enumerate(ocf)
        ]
        result = from_margins(fcf_series, "normalized-fcf")
        if result is not None:
            notes.append("所有者收益不可用，改用多年自由现金流利润率归一")
            base, label, years = result
            return base, label, years, notes

        result = from_margins(list(d.net_income_history or []), "normalized-net-income")
        if result is not None:
            notes.append("现金流历史不足，改用多年净利润率归一")
            base, label, years = result
            return base, label, years, notes

        # Single-year fallbacks. Flagged unreliable because one year of a
        # cyclical is exactly the failure this engine exists to avoid.
        if float(d.free_cash_flow or 0.0) > 0.0:
            notes.append("仅有单年现金流，估值可信度下降")
            return float(d.free_cash_flow) / shares, "trailing-fcf", 1, notes

        if float(d.net_income or 0.0) > 0.0:
            notes.append("仅有单年净利润，估值可信度下降")
            return float(d.net_income) / shares, "trailing-net-income", 1, notes

        if d.eps > 0.0:
            notes.append("缺少现金流与净利润，改用 EPS 近似")
            return d.eps * 0.9, "eps-proxy", 1, notes

        return 0.0, "unavailable", 0, notes

    @staticmethod
    def _growth_estimate(d: CompanyFinancials) -> float:
        """Forward growth, damped and bounded.

        Trailing revenue growth alone is a poor forecast: NVDA's +65% year cannot
        persist for five, and extrapolating it manufactures an intrinsic value
        several times the quote. This blends the trailing rate with the multi-year
        revenue CAGR, then damps the result — growth is mean-reverting and the
        valuation must not become a bet on momentum.
        """

        trailing = float(d.revenue_growth_yoy or 0.0)
        revenue = [value for value in (d.revenue_history or []) if value > 0.0]
        cagr: Optional[float] = None
        if len(revenue) >= 2:
            newest, oldest = revenue[0], revenue[-1]
            years = len(revenue) - 1
            if oldest > 0.0 and years > 0:
                cagr = (newest / oldest) ** (1.0 / years) - 1.0

        estimate = trailing if cagr is None else (trailing * 0.4 + cagr * 0.6)
        # 25% sustained for five years is already an extraordinary underwrite.
        return min(max(estimate * 0.65, -0.05), 0.25)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, d: CompanyFinancials) -> ValuationResult:
        sym = d.ticker.upper()
        moat = self._analyze_moat(d)

        # 1. Graham Number & Growth Valuation (both already price-independent)
        est_bvps = self._book_value_per_share(d)
        graham_num = math.sqrt(max(22.5 * max(d.eps, 0.1) * est_bvps, 0.0))
        growth_g = min(max(d.revenue_growth_yoy * 100, 2.0), 30.0)
        # Graham growth formula: V = EPS * (8.5 + 2g) * (4.4 / Y)
        graham_growth = max(d.eps, 0.1) * (8.5 + 2 * min(growth_g, 20.0)) * (
            4.4 / max(self.risk_free_rate * 100, 3.5)
        )

        base_per_share, basis, years, notes = self._normalized_base(d)
        if basis == "unavailable" or base_per_share <= 0.0:
            # Nothing price-independent is available (typical for an ETF, which
            # has no issuer fundamentals). Report unreliable rather than
            # manufacturing a number from the price.
            return ValuationResult(
                ticker=sym,
                current_price=d.price,
                intrinsic_value_dcf=0.0,
                graham_number=round(graham_num, 2),
                graham_growth_value=round(graham_growth, 2),
                margin_of_safety_pct=0.0,
                valuation_status="Not Valuable (insufficient fundamentals)",
                moat_analysis=moat,
                dcf_assumptions={"reason": "no price-independent cash-flow input"},
                basis="unavailable",
                is_reliable=False,
                notes=["无法在不依赖股价的前提下估值（ETF 或缺失财报）"],
            )

        discount_rate = self._discount_rate(d)
        growth = self._growth_estimate(d)

        # 2. Two-stage DCF on normalised owner earnings, per share.
        horizon = 5
        projected: List[float] = []
        current = base_per_share
        fade = 0.80
        for index in range(1, horizon + 1):
            current *= 1.0 + growth * (fade ** (index - 1))
            projected.append(current / ((1.0 + discount_rate) ** index))

        terminal_cash = current * (1.0 + self.terminal_growth)
        terminal_value = terminal_cash / (discount_rate - self.terminal_growth)
        pv_terminal = terminal_value / ((1.0 + discount_rate) ** horizon)
        intrinsic_dcf = round(sum(projected) + pv_terminal, 2)

        # 3. Margin of safety, normalised by PRICE rather than intrinsic value.
        #
        # Dividing by intrinsic value is unbounded below: as intrinsic tends to
        # zero the ratio tends to -infinity, which is how a data artefact became
        # a -1289% reading and saturated the score for 6 of 8 names. Price
        # normalisation is bounded at -100% ("worth nothing") and is the
        # conventional discount-to-fair-value quote anyway.
        price = float(d.price or 0.0)
        mos = round(((intrinsic_dcf - price) / price) * 100, 2) if price > 0.0 else 0.0

        # Single-year bases are reported but not trusted as a cheapness signal.
        reliable = basis in {
            "normalized-owner-earnings", "normalized-fcf", "normalized-net-income",
        }

        if mos >= 20.0:
            status = "Significantly Undervalued (High Margin of Safety)"
        elif mos >= 0.0:
            status = "Fairly Valued (Reasonable Entry Zone)"
        elif mos >= -20.0:
            status = "Modestly Overvalued"
        else:
            status = "Significantly Overvalued"

        return ValuationResult(
            ticker=sym,
            current_price=price,
            intrinsic_value_dcf=intrinsic_dcf,
            graham_number=round(graham_num, 2),
            graham_growth_value=round(graham_growth, 2),
            margin_of_safety_pct=mos,
            valuation_status=status,
            moat_analysis=moat,
            dcf_assumptions={
                "discount_rate": f"{discount_rate*100:.1f}%",
                "beta": f"{d.beta:.2f}",
                "terminal_growth": f"{self.terminal_growth*100:.1f}%",
                "growth_estimate": f"{growth*100:.1f}%",
                "normalized_owner_earnings_per_share": f"${base_per_share:.2f}",
                "normalization_years": years,
                "shares_outstanding": f"{d.shares_outstanding:,.0f}",
                "forecast_period": f"{horizon} Years",
            },
            basis=basis,
            is_reliable=reliable,
            notes=notes,
            normalization_years=years,
            normalized_owner_earnings=round(base_per_share, 4),
        )

    @staticmethod
    def _book_value_per_share(d: CompanyFinancials) -> float:
        """Book value per share, preferring reported equity over an ROE proxy."""

        equity = float(d.shareholders_equity or 0.0)
        shares = float(d.shares_outstanding or 0.0)
        if equity > 0.0 and shares > 0.0:
            return max(equity / shares, 1.0)
        return max(d.eps / max(d.roe, 0.05), 1.0)

    def _analyze_moat(self, d: CompanyFinancials) -> MoatDimensions:
        """Derive moat dimensions from observable financials.

        Previously a 7-ticker lookup table decided this and everything else fell
        through to a heuristic, so the two paths were not comparable. A moat is an
        economic claim, and its evidence — durable pricing power, efficiency,
        scale, earnings stability — is measurable for any issuer.
        """

        gross = float(d.gross_margin or 0.0)
        operating = float(d.operating_margin or 0.0)
        roe = float(d.roe or 0.0)
        market_cap = max(float(d.market_cap or 0.0), 1e8)

        # Brand / intangibles: what customers pay above cost of goods.
        brand = min(max(gross * 12.0, 2.0), 9.5)
        # Cost advantage: converting revenue into operating profit.
        cost = min(max(operating * 18.0, 2.0), 9.5)
        # Network effects cannot be read off a statement. Returns persistently
        # above the cost of capital are the observable footprint of one.
        network = min(max(roe * 20.0, 2.0), 9.0)
        # Switching costs: margin stability across reported years. A vendor whose
        # customers cannot leave does not see its margin swing.
        revenue = [value for value in (d.revenue_history or []) if value > 0.0]
        income = list(d.net_income_history or [])
        span = min(len(revenue), len(income))
        if span >= 3:
            margins = [income[index] / revenue[index] for index in range(span)]
            mean = sum(margins) / len(margins)
            variance = sum((value - mean) ** 2 for value in margins) / len(margins)
            # Low dispersion around a healthy mean reads as entrenchment.
            stability = 1.0 / (1.0 + math.sqrt(variance) * 8.0)
            switching = min(max(stability * 10.0 * (1.0 if mean > 0 else 0.5), 2.0), 9.0)
        else:
            switching = min(max(operating * 15.0, 2.0), 7.0)
        # Economies of scale: absolute size, on a log scale.
        scale = min(max(math.log10(market_cap) * 0.85 - 3.0, 2.0), 9.5)

        comp = round(
            brand * 0.20 + cost * 0.20 + network * 0.25 + switching * 0.20 + scale * 0.15,
            2,
        )
        rating = (
            "Wide Moat (Super Fortress)" if comp >= 8.0
            else ("Narrow Moat (Defensible)" if comp >= 6.0 else "No Moat / Commodity")
        )

        return MoatDimensions(
            brand_intangibles=round(brand, 2),
            cost_advantage=round(cost, 2),
            network_effects=round(network, 2),
            switching_costs=round(switching, 2),
            economies_of_scale=round(scale, 2),
            composite_moat_score=comp,
            moat_rating=rating,
        )
