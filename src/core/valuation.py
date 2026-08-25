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


class ValuationEngine:
    """Calculates intrinsic value using Graham formulas, 2-stage DCF, and 5-dimension moat analysis."""

    def __init__(self, wacc: float = 0.095, terminal_growth: float = 0.025, risk_free_rate: float = 0.045):
        self.wacc = wacc
        self.terminal_growth = terminal_growth
        self.risk_free_rate = risk_free_rate

    def evaluate(self, d: CompanyFinancials) -> ValuationResult:
        sym = d.ticker.upper()
        moat = self._analyze_moat(d)

        # 1. Graham Number & Growth Valuation
        # Approximate Book Value Per Share using ROE: BVPS = EPS / max(ROE, 0.05)
        est_bvps = max(d.eps / max(d.roe, 0.05), 1.0)
        graham_num = math.sqrt(max(22.5 * max(d.eps, 0.1) * est_bvps, 0.0))

        growth_g = min(max(d.revenue_growth_yoy * 100, 2.0), 30.0)
        # Graham growth formula: V = EPS * (8.5 + 2g) * (4.4 / Y)
        graham_growth = max(d.eps, 0.1) * (8.5 + 2 * min(growth_g, 20.0)) * (4.4 / max(self.risk_free_rate * 100, 3.5))

        # 2. Two-Stage DCF Model on Owner Earnings / FCF
        # Base FCF per share = Price * FCF Yield
        base_fcf_per_share = max(d.price * max(d.fcf_yield, 0.02), d.eps * 0.8)
        years = 5
        projected_fcf = []
        current_fcf = base_fcf_per_share
        fade_rate = 0.85

        for i in range(1, years + 1):
            year_growth = d.revenue_growth_yoy * (fade_rate ** (i - 1))
            current_fcf *= (1.0 + min(max(year_growth, 0.03), 0.35))
            pv = current_fcf / ((1.0 + self.wacc) ** i)
            projected_fcf.append(pv)

        sum_pv_fcf = sum(projected_fcf)
        # Terminal value at year 5
        terminal_fcf = current_fcf * (1.0 + self.terminal_growth)
        terminal_value = terminal_fcf / (self.wacc - self.terminal_growth)
        pv_terminal_value = terminal_value / ((1.0 + self.wacc) ** years)

        intrinsic_dcf = round(sum_pv_fcf + pv_terminal_value, 2)
        mos = round(((intrinsic_dcf - d.price) / intrinsic_dcf) * 100, 2)

        if mos >= 20.0:
            val_status = "Significantly Undervalued (High Margin of Safety)"
        elif mos >= 0.0:
            val_status = "Fairly Valued (Reasonable Entry Zone)"
        elif mos >= -20.0:
            val_status = "Modestly Overvalued"
        else:
            val_status = "Significantly Overvalued"

        return ValuationResult(
            ticker=sym,
            current_price=d.price,
            intrinsic_value_dcf=intrinsic_dcf,
            graham_number=round(graham_num, 2),
            graham_growth_value=round(graham_growth, 2),
            margin_of_safety_pct=mos,
            valuation_status=val_status,
            moat_analysis=moat,
            dcf_assumptions={
                "wacc": f"{self.wacc*100:.1f}%",
                "terminal_growth": f"{self.terminal_growth*100:.1f}%",
                "starting_fcf_per_share": f"${base_fcf_per_share:.2f}",
                "forecast_period": "5 Years"
            }
        )

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
