"""Value Investing & Intrinsic Valuation Engine (Graham, Buffett Owner Earnings, DCF)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Any, List
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
    # Whether intrinsic value came from absolute cash flows (trustworthy) or had
    # to fall back to a price-derived estimate (not usable as a cheapness signal).
    basis: str = "absolute-fcf"
    is_reliable: bool = True
    notes: List[str] = field(default_factory=list)


class ValuationEngine:
    """Intrinsic value from Graham formulas, a 2-stage DCF, and moat analysis.

    The DCF starts from **absolute** free cash flow and share count, never from
    ``price * fcf_yield``. Using the price-derived figure made intrinsic value
    scale linearly with the quote, so margin-of-safety was a constant for a given
    company and carried no information about whether it was cheap. Verified:
    at prices 100/150/300 the old model returned MoS -18.29% every time.
    """

    def __init__(self, wacc: float = 0.095, terminal_growth: float = 0.025, risk_free_rate: float = 0.045):
        self.wacc = wacc
        self.terminal_growth = terminal_growth
        self.risk_free_rate = risk_free_rate

    def evaluate(self, d: CompanyFinancials) -> ValuationResult:
        sym = d.ticker.upper()
        moat = self._analyze_moat(d)
        notes: List[str] = []

        # 1. Graham Number & Growth Valuation (both already price-independent)
        est_bvps = self._book_value_per_share(d)
        graham_num = math.sqrt(max(22.5 * max(d.eps, 0.1) * est_bvps, 0.0))

        growth_g = min(max(d.revenue_growth_yoy * 100, 2.0), 30.0)
        # Graham growth formula: V = EPS * (8.5 + 2g) * (4.4 / Y)
        graham_growth = max(d.eps, 0.1) * (8.5 + 2 * min(growth_g, 20.0)) * (4.4 / max(self.risk_free_rate * 100, 3.5))

        # 2. Two-stage DCF on owner earnings, per share, from ABSOLUTE inputs.
        shares = float(d.shares_outstanding or 0.0)
        absolute_fcf = float(d.free_cash_flow or 0.0)
        basis = "absolute-fcf"
        reliable = True

        if shares > 0.0 and absolute_fcf > 0.0:
            base_fcf_per_share = absolute_fcf / shares
        elif shares > 0.0 and d.net_income:
            # Owner earnings proxy: net income is still independent of price.
            base_fcf_per_share = float(d.net_income) / shares
            basis = "net-income-proxy"
            notes.append("缺少自由现金流，改用净利润近似所有者收益")
        elif d.eps > 0.0:
            # EPS is price-independent; a rough proxy but still not circular.
            base_fcf_per_share = d.eps * 0.9
            basis = "eps-proxy"
            notes.append("缺少现金流与股数，改用 EPS 近似")
        else:
            # Nothing price-independent is available (typical for an ETF, where
            # company fundamentals do not exist). Report unreliable rather than
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

        years = 5
        projected: List[float] = []
        current_fcf = base_fcf_per_share
        fade_rate = 0.85
        for index in range(1, years + 1):
            year_growth = d.revenue_growth_yoy * (fade_rate ** (index - 1))
            current_fcf *= (1.0 + min(max(year_growth, 0.0), 0.35))
            projected.append(current_fcf / ((1.0 + self.wacc) ** index))

        terminal_fcf = current_fcf * (1.0 + self.terminal_growth)
        terminal_value = terminal_fcf / (self.wacc - self.terminal_growth)
        pv_terminal = terminal_value / ((1.0 + self.wacc) ** years)
        intrinsic_dcf = round(sum(projected) + pv_terminal, 2)

        # Margin of safety against the intrinsic estimate. Now that intrinsic is
        # price-independent, this genuinely moves when the quote moves.
        mos = round(((intrinsic_dcf - d.price) / intrinsic_dcf) * 100, 2) if intrinsic_dcf > 0 else 0.0

        if basis != "absolute-fcf":
            reliable = False

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
            current_price=d.price,
            intrinsic_value_dcf=intrinsic_dcf,
            graham_number=round(graham_num, 2),
            graham_growth_value=round(graham_growth, 2),
            margin_of_safety_pct=mos,
            valuation_status=status,
            moat_analysis=moat,
            dcf_assumptions={
                "wacc": f"{self.wacc*100:.1f}%",
                "terminal_growth": f"{self.terminal_growth*100:.1f}%",
                "starting_fcf_per_share": f"${base_fcf_per_share:.2f}",
                "shares_outstanding": f"{shares:,.0f}",
                "absolute_fcf": f"${absolute_fcf:,.0f}",
                "forecast_period": "5 Years",
            },
            basis=basis,
            is_reliable=reliable,
            notes=notes,
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
        sym = d.ticker.upper()
        # Specific known moats
        profiles = {
            "TSM": (9.0, 9.8, 8.5, 9.5, 9.9),
            "UBER": (8.0, 8.8, 9.8, 8.5, 9.2),
            "AVGO": (8.5, 8.5, 8.0, 9.2, 8.8),
            "ADBE": (9.0, 7.5, 7.0, 9.0, 8.0),
            "APP": (6.5, 6.0, 7.5, 6.5, 7.0),
            "SOFI": (5.0, 4.5, 5.0, 4.5, 5.0),
            "GOOGL": (9.5, 9.0, 9.5, 8.5, 9.5)
        }

        if sym in profiles:
            b, c, n, s, e = profiles[sym]
        else:
            # Heuristic calculation
            b = min(max(d.gross_margin * 10, 3.0), 9.5)
            c = min(max(d.operating_margin * 15, 3.0), 9.0)
            n = 6.0
            s = 6.0
            e = min(max(math.log10(max(d.market_cap, 1e9)) * 0.8, 3.0), 9.5)

        comp = round(b * 0.2 + c * 0.2 + n * 0.25 + s * 0.2 + e * 0.15, 2)
        rating = "Wide Moat (Super Fortress)" if comp >= 8.0 else ("Narrow Moat (Defensible)" if comp >= 6.0 else "No Moat / Commodity")

        return MoatDimensions(
            brand_intangibles=b,
            cost_advantage=c,
            network_effects=n,
            switching_costs=s,
            economies_of_scale=e,
            composite_moat_score=comp,
            moat_rating=rating
        )
