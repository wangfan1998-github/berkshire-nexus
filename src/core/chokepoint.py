"""Serenity-Style Supply Chain & Chokepoint (瓶颈) Analysis Engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Any, List
from ..data.fetcher import CompanyFinancials


@dataclass
class ChokepointResult:
    ticker: str
    chokepoint_level: int  # 1 (Commodity) to 5 (Absolute Physical Monopoly)
    chokepoint_title: str
    physical_unreplaceability: float  # 0 to 10
    capex_expansion_barrier: float    # 0 to 10
    switching_cost: float             # 0 to 10
    pricing_power: float              # 0 to 10
    value_capture_ratio: float        # 0 to 10
    overall_score: float              # 0 to 10
    bottleneck_diagnosis: str
    key_evidence: List[str] = field(default_factory=list)
    threat_matrix: List[str] = field(default_factory=list)


class ChokepointAnalyzer:
    """Evaluates where a company sits on the supply chain bottleneck ladder."""

    def analyze(self, data: CompanyFinancials) -> ChokepointResult:
        """Derive the chokepoint profile from observable data, for every issuer.

        A 6-ticker table of hand-written qualitative profiles used to short-circuit
        this. It was removed: those six got prose grounded in nothing the model
        could verify, every other symbol took a different code path, and the two
        were not comparable — so the 45%-weight quality layer was measuring
        different things depending on whether a name happened to be in the table.
        """

        return self._derive(data)

    # Industry -> (capital intensity, physical substitution difficulty).
    # A chokepoint is about how hard the position is to replicate physically, so
    # industry is the strongest available proxy: a foundry or a utility cannot be
    # duplicated on a software timescale, an app can.
    _INDUSTRY_TRAITS = {
        "semiconductors": (9.0, 8.5),
        "semiconductor equipment": (9.2, 9.0),
        "industrial machinery/components": (7.5, 7.0),
        "biotechnology: laboratory analytical instruments": (7.0, 7.0),
        "electric utilities: central": (9.5, 9.0),
        "power generation": (9.3, 8.8),
        "oil & gas production": (8.5, 8.0),
        "natural gas distribution": (8.8, 8.5),
        "computer manufacturing": (6.0, 5.0),
        "computer peripheral equipment": (5.5, 4.5),
        "electronic components": (6.5, 6.0),
        "electrical products": (6.5, 6.0),
        "telecommunications equipment": (6.0, 5.5),
        "computer communications equipment": (6.0, 5.5),
        "radio and television broadcasting and communications equipment": (5.5, 5.0),
        "computer software: prepackaged software": (2.5, 3.0),
        "computer software: programming data processing": (2.5, 3.0),
        "advertising": (2.0, 2.5),
        "retail: computer software & peripheral equipment": (3.0, 3.0),
    }

    def _derive(self, data: CompanyFinancials) -> ChokepointResult:
        """Compute a chokepoint profile from observable financials.

        Replaces a constant. Previously every ticker outside a 6-entry lookup
        table received an identical L2 / 5.52, which meant 25% of the final score
        carried no information for ~7,900 of ~7,900 tradable symbols.

        Each dimension is tied to something measurable:

        * unreplaceability  — gross margin (pricing power that survives
          competition) blended with how physically hard the industry is to copy
        * capex barrier     — industry capital intensity, scaled by absolute size,
          since replicating an incumbent means matching its installed base
        * switching cost    — operating margin durability plus scale; customers
          rarely leave a vendor that is both entrenched and efficient
        * pricing power     — operating margin, the clearest evidence of it
        * value capture     — how much of revenue reaches owners as cash
        """

        sym = data.ticker.upper()
        industry = (data.industry or "").strip().lower()
        capital_intensity, substitution_difficulty = self._INDUSTRY_TRAITS.get(
            industry, (5.0, 5.0)
        )

        # Scale premium: a $1T incumbent is materially harder to displace than a
        # $2B one in the same industry.
        market_cap = max(float(data.market_cap or 0.0), 1.0)
        scale = min(max((math.log10(market_cap) - 9.0) / 3.0, 0.0), 1.0)  # 1B..1T

        gross = min(max(data.gross_margin, 0.0), 1.0)
        operating = min(max(data.operating_margin, 0.0), 1.0)

        unrep = min(max(gross * 6.0 + substitution_difficulty * 0.45, 1.0), 9.8)
        capex = min(max(capital_intensity * 0.75 + scale * 2.5, 1.0), 9.9)
        switching = min(max(operating * 8.0 + scale * 3.0 + substitution_difficulty * 0.2, 1.0), 9.5)
        pricing = min(max(operating * 14.0 + gross * 3.0, 1.0), 9.5)
        # Cash actually reaching owners, relative to sales.
        fcf_margin = (
            float(data.free_cash_flow or 0.0) / float(data.revenue)
            if data.revenue else 0.0
        )
        value_capture = min(max(fcf_margin * 18.0 + operating * 5.0, 1.0), 9.6)

        overall = round(
            unrep * 0.30 + capex * 0.20 + switching * 0.20
            + pricing * 0.15 + value_capture * 0.15,
            2,
        )
        if overall >= 8.8:
            level, title = 5, "Physical Monopoly Chokepoint"
        elif overall >= 7.5:
            level, title = 4, "Strong Structural Chokepoint"
        elif overall >= 6.2:
            level, title = 3, "Defensible Position"
        elif overall >= 4.8:
            level, title = 2, "Competitive Position"
        else:
            level, title = 1, "Commodity / Price-Taker"

        evidence = [
            f"行业: {data.industry or '未知'}（资本密集度 {capital_intensity:.1f}/10，物理替代难度 {substitution_difficulty:.1f}/10）",
            f"毛利率 {gross*100:.1f}% · 营业利润率 {operating*100:.1f}%",
            f"市值 {market_cap/1e9:.1f}B（规模系数 {scale:.2f}）",
        ]
        if data.revenue:
            evidence.append(f"自由现金流/收入 {fcf_margin*100:.1f}%")

        threats: List[str] = []
        if capital_intensity < 4.0:
            threats.append("低资本门槛：新进入者可快速复制")
        if operating < 0.12:
            threats.append("薄利：缺乏定价权证据")
        if gross < 0.35:
            threats.append("低毛利：产品接近同质化")
        if not threats:
            threats.append("主要风险来自技术替代与需求周期")

        return ChokepointResult(
            ticker=sym,
            chokepoint_level=level,
            chokepoint_title=title,
            physical_unreplaceability=round(unrep, 1),
            capex_expansion_barrier=round(capex, 1),
            switching_cost=round(switching, 1),
            pricing_power=round(pricing, 1),
            value_capture_ratio=round(value_capture, 1),
            overall_score=overall,
            bottleneck_diagnosis=(
                f"由行业资本密集度、利润率结构与规模推导：Level {level}。"
                f"{'该位置难以被短期复制。' if level >= 4 else '该位置存在可替代性。' }"
            ),
            key_evidence=evidence,
            threat_matrix=threats,
        )

