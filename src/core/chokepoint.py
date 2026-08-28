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

    # Specific qualitative profiles for known companies
    _CHOKEPOINT_PROFILES = {
        "TSM": {
            "level": 5,
            "title": "Absolute Physical Manufacturing Chokepoint",
            "unreplaceability": 9.8,
            "capex_barrier": 9.9,
            "switching_cost": 9.5,
            "pricing_power": 9.2,
            "value_capture": 9.6,
            "diagnosis": "Monopoly on leading-edge 3nm/2nm and CoWoS advanced packaging (>90% market share). All AI GPU and ASIC routes must pass through TSMC's fabs.",
            "evidence": [
                ">90% global market share in sub-5nm advanced node manufacturing",
                "Annual CapEx of $30B+ creating an insurmountable capital and yield-rate barrier",
                "Full order backlog from Nvidia, Apple, AMD, Qualcomm, and Cloud ASICs"
            ],
            "threats": [
                "Geopolitical concentration risks in Taiwan Strait",
                "Margin dilution from overseas fab expansion (US, Japan, Europe)"
            ]
        },
        "AVGO": {
            "level": 4,
            "title": "Data Center Interconnect & ASIC Architecture Chokepoint",
            "unreplaceability": 8.8,
            "capex_barrier": 8.5,
            "switching_cost": 9.0,
            "pricing_power": 8.9,
            "value_capture": 8.7,
            "diagnosis": "Dominates high-speed Ethernet switching silicon (Tomahawk/Jericho) and custom AI ASIC co-design for hyperscalers (Google TPU, Meta, etc.).",
            "evidence": [
                ">70% market share in high-end data center Ethernet switching silicon",
                "Custom ASIC co-design partner of choice for top cloud providers",
                "Immense software recurring revenue (VMware) with 95%+ renewal rates"
            ],
            "threats": [
                "Nvidia's proprietary NVLink / InfiniBand ecosystem competition",
                "High revenue concentration in top 3 hyperscaler customers"
            ]
        },
        "UBER": {
            "level": 4,
            "title": "Global Physical Mobility & Dispatch Network Chokepoint",
            "unreplaceability": 8.6,
            "capex_barrier": 8.2,
            "switching_cost": 8.5,
            "pricing_power": 8.4,
            "value_capture": 8.8,
            "diagnosis": "Unbreachable two-sided network liquidity in urban transportation and delivery. The inevitable distribution layer for autonomous fleets (Waymo/Tesla).",
            "evidence": [
                "150M+ monthly active platform consumers across 70+ countries",
                "Cross-selling flywheel between Rides and Uber Eats lowers CAC by 40%",
                "Waymo and other AV operators partner with Uber for demand dispatch instead of building their own app networks"
            ],
            "threats": [
                "Tesla Robotaxi vertical integration risk if Tesla scales standalone app successfully",
                "Regulatory gig-worker classification and wage pressures"
            ]
        },
        "APP": {
            "level": 3,
            "title": "AI Algorithmic Ad-Attribution & In-App Monetization Engine",
            "unreplaceability": 6.8,
            "capex_barrier": 6.0,
            "switching_cost": 6.5,
            "pricing_power": 8.0,
            "value_capture": 8.2,
            "diagnosis": "AXON 2.0 AI recommendation engine delivers industry-leading ROI for mobile and e-commerce advertisers. High cash flow but upstream platform risk.",
            "evidence": [
                "AXON 2.0 expanded advertiser base from mobile games to multi-billion e-commerce campaigns",
                "EBITDA margins exceeding 55% with exceptional free cash flow conversion",
                "Aggressive share buyback program retiring >5% of share count annually"
            ],
            "threats": [
                "Vulnerable to Apple (iOS) and Google (Android) ad privacy policy disruptions (like ATT)",
                "Competitors (Meta Advantage+, Google PMax) narrowing algorithm conversion gap"
            ]
        },
        "ADBE": {
            "level": 3,
            "title": "Enterprise Creative Workflow & Digital Document Standard",
            "unreplaceability": 7.5,
            "capex_barrier": 6.5,
            "switching_cost": 8.8,
            "pricing_power": 7.8,
            "value_capture": 7.5,
            "diagnosis": "Decades of enterprise creative asset standards (PSD, PDF) and deep workflow integration. Defending against generative AI disruption.",
            "evidence": [
                "Deep integration with global agency, print, video, and design production pipelines",
                "Gross margin >88% with vast enterprise contract retention rates",
                "Firefly GenAI embedded directly into Photoshop/Premiere workflows"
            ],
            "threats": [
                "Generative AI native startups (Midjourney, Sora, Runway, Figma) lowering design barrier",
                "Canva eating casual and SMB graphic design demand"
            ]
        },
        "SOFI": {
            "level": 1,
            "title": "Digital Consumer Banking & Lending Platform",
            "unreplaceability": 4.0,
            "capex_barrier": 4.5,
            "switching_cost": 4.5,
            "pricing_power": 4.0,
            "value_capture": 4.2,
            "diagnosis": "High-growth neo-bank with national charter, but essentially sells commoditized money and consumer debt in a hyper-competitive market.",
            "evidence": [
                "Rapid growth in member base and Galileo/Technisys financial technology stack",
                "National bank charter lowers cost of deposits relative to non-bank fintechs"
            ],
            "threats": [
                "Zero true physical barrier: money and credit are fungible commodities",
                "Credit risk, interest rate spreads, and default cycles compress loan book value"
            ]
        }
    }

    def analyze(self, data: CompanyFinancials) -> ChokepointResult:
        sym = data.ticker.upper()
        if sym in self._CHOKEPOINT_PROFILES:
            p = self._CHOKEPOINT_PROFILES[sym]
            score = (p["unreplaceability"] * 0.3 +
                     p["capex_barrier"] * 0.2 +
                     p["switching_cost"] * 0.2 +
                     p["pricing_power"] * 0.15 +
                     p["value_capture"] * 0.15)
            return ChokepointResult(
                ticker=sym,
                chokepoint_level=p["level"],
                chokepoint_title=p["title"],
                physical_unreplaceability=p["unreplaceability"],
                capex_expansion_barrier=p["capex_barrier"],
                switching_cost=p["switching_cost"],
                pricing_power=p["pricing_power"],
                value_capture_ratio=p["value_capture"],
                overall_score=round(score, 2),
                bottleneck_diagnosis=p["diagnosis"],
                key_evidence=p["evidence"],
                threat_matrix=p["threats"]
            )

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

